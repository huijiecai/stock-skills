"""运行器:看盘循环(agent 持续看盘,记忆延续)。

两种模式:
- replay(模拟看盘):回放某历史日,每轮步进 interval 分钟(默认 5),开盘→收盘(跳过午休)
- live(实时看盘):一轮结束马上下一轮(默认 sleep=0 不等待),可选轮间间隔

用法:
  uv run python -m trader.runner replay 20260812 --interval 5
  uv run python -m trader.runner replay 20260812 --max-rounds 2   # 调试:只跑2轮
  uv run python -m trader.runner live --sleep 0
"""
import argparse
import json
import re
import time as time_mod
from datetime import datetime, time, timedelta
from pathlib import Path

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.usage import UsageLimits

from trader.agent import agent
from trader.prompts import load
from trader.store import default_account, default_documents
from trader.tools.market import _fetch_market_summary

# 盘前/研究这类长任务(八维搜索+多轮工具)放宽请求上限;默认 50 不够用
LONG_TASK_LIMITS = UsageLimits(request_limit=200)

# 进程内存里只留最近 N 轮对话,防止全天看盘把上下文撑爆;
# 跨重启的记忆不靠对话,靠 documents 里的轮日志(watch_live/watch_replay)
KEEP_ROUNDS = 8


def _prev_trading_day(target: str) -> str:
    """上一交易日:
    - 目标日在最新数据之后(为未来/今日做盘前)→ 最新交易日即上一交易日
    - 目标日已有数据(回放/补跑)→ 从 target-1 起往前试探(节假日自动跳过)
    """
    latest = str(_fetch_market_summary("").get("date", "")).replace("-", "")
    if latest and target > latest:
        return latest
    d = datetime.strptime(target, "%Y%m%d") - timedelta(days=1)
    for _ in range(15):
        ds = d.strftime("%Y%m%d")
        try:
            if _fetch_market_summary(ds).get("date"):
                return ds
        except Exception:  # noqa: BLE001 —— 无数据(节假日)继续往前
            pass
        d -= timedelta(days=1)
    raise RuntimeError(f"15 天内找不到 {target} 的上一交易日")

MORNING_START = time(9, 35)   # 回放起点:开盘后 5 分钟
LUNCH_BREAK = (time(11, 30), time(13, 0))
CLOSE = time(15, 0)


def _run_round(prompt: str, history: list[ModelMessage], retries: int = 3,
               usage_limits: UsageLimits | None = None):
    """跑一轮,失败重试(偶发 API 错误不崩整个看盘循环)。"""
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return agent.run_sync(prompt, message_history=history, usage_limits=usage_limits)
        except Exception as e:  # noqa: BLE001 —— API 网络抖动/限流等各种偶发
            last_err = e
            print(f"  ⚠ 本轮第 {attempt}/{retries} 次失败:{type(e).__name__}: {str(e)[:120]}")
            time_mod.sleep(2)
    raise RuntimeError(f"连续 {retries} 次失败,停止看盘: {last_err}")


def run_replay(date: str, interval: int = 5, max_rounds: int | None = None,
               resume: bool = False) -> None:
    """模拟看盘:回放某日,每轮步进 interval 分钟,午休自动跳过。
    回放账户完全独立(data/replay_{date}.db,绝不碰 live 账户);
    默认全新实验(清该日旧 watch_replay/transcript_replay + 重置回放账户),
    --resume 接续:不清不重置,从该日最大轮号继续。预期库/其他文档始终共享。"""
    import trader.store as store

    replay_db = Path(__file__).resolve().parent.parent / "data" / f"replay_{date}.db"
    store._default = store.Account(db_path=replay_db)  # 本进程内所有工具改用回放账户
    if resume:
        done = _last_round("watch_replay", date)
        if not done:
            print("⚠ 没有该日的回放轮日志,无法接续,按全新实验开始")
        print(f"↺ 接续 {date} 回放:已有 {done} 轮,从第 {done + 1} 轮继续(回放账户保持原状)")
        rounds, hhmm = done, _resume_clock(date, done)
    else:
        default_documents().delete("watch_replay", date)
        default_documents().delete("transcript_replay", date)
        default_account().reset()
        print(f"↺ 全新回放实验:{replay_db.name} 已重置(空仓+初始现金,live 账户不受影响)")
        rounds, hhmm = 0, MORNING_START
    history: list[ModelMessage] = []
    while hhmm <= CLOSE:
        if LUNCH_BREAK[0] < hhmm < LUNCH_BREAK[1]:  # 跳过午休
            hhmm = LUNCH_BREAK[1]
        rounds += 1
        clock = hhmm.strftime("%H:%M")
        print(f"\n{'=' * 60}\n第 {rounds} 轮 · 模拟看盘 {date} {clock}\n{'=' * 60}")
        prompt = load("round_replay", rounds=rounds, date=date, clock=clock)
        result = _run_round(prompt, history)
        history = _trim_rounds(result.all_messages())
        _save_transcript("transcript_replay", date, rounds, clock,
                         result.all_messages(), result.usage)
        print(result.output)
        if max_rounds and rounds >= max_rounds:
            print(f"\n(达到 max_rounds={max_rounds},停止)")
            return
        minutes = hhmm.hour * 60 + hhmm.minute + interval
        hhmm = time(minutes // 60, minutes % 60)


def _trim_rounds(messages: list[ModelMessage], keep: int = KEEP_ROUNDS) -> list[ModelMessage]:
    """按轮切分(每轮以一个 user 提示开头),只留最近 keep 轮。
    一轮内部的 请求/工具调用/工具返回 天然成对,整轮丢弃不会产生孤立的工具返回。"""
    starts = [i for i, m in enumerate(messages)
              if m.parts and getattr(m.parts[0], "part_kind", "") == "user-prompt"]
    if len(starts) <= keep:
        return messages
    return messages[starts[-keep]:]


def _last_round(doc_type: str, trade_date: str) -> int:
    """从 documents 读当天 watch 轮日志的最大轮号(纯 Python 查表,不过 LLM)。"""
    best = 0
    for d in default_documents().list(doc_type, trade_date):
        name = (d.get("name") or "").strip()
        if name.startswith("r") and name[1:].isdigit():
            best = max(best, int(name[1:]))
    return best


def _resume_clock(date: str, last_round: int) -> time:
    """接续回放:从最后一轮轮日志标题(# rN HH:MM)解析时钟,接不回来就从开盘重来。"""
    doc = default_documents().get("watch_replay", name=f"r{last_round}", trade_date=date)
    if doc:
        m = re.search(r"(\d{1,2}):(\d{2})", doc[:60])
        if m:
            return time(int(m.group(1)), int(m.group(2)))
    return MORNING_START


def _save_transcript(doc_type: str, trade_date: str, round_no: int, clock: str,
                     messages: list[ModelMessage], usage) -> None:
    """每轮完整思考流落库(工具调用/返回/推理的原始消息流,JSON)。
    viewer 的数据源;落盘失败只警告,绝不影响看盘循环。"""
    try:
        content = json.dumps({
            "round": round_no, "time": clock,
            "usage": {k: getattr(usage, k, None)
                      for k in ("requests", "input_tokens", "output_tokens")},
            "messages": json.loads(ModelMessagesTypeAdapter.dump_json(messages)),
        }, ensure_ascii=False)
        default_documents().save(doc_type, content, name=f"r{round_no}", trade_date=trade_date)
    except Exception as e:  # noqa: BLE001 —— 观测数据,尽力而为
        print(f"  ⚠ 思考流落盘失败:{type(e).__name__}: {str(e)[:80]}")


def run_live(sleep_seconds: int = 0, max_rounds: int | None = None) -> None:
    """实时看盘:一轮结束马上下一轮(sleep=0 默认不等待),Ctrl+C 停止。
    跨重启接续靠 documents 的轮日志(watch_live/rN/日期):启动时从当天最大轮号接着编号,
    会话状态(盘感/自设条件/待办)由 prompt 指挥 AI 读最近几轮日志恢复。午休自动跳过。"""
    today = datetime.now().strftime("%Y%m%d")
    rounds = _last_round("watch_live", today)
    if rounds:
        print(f"↺ 接续今日看盘:documents 里已有 {rounds} 轮日志,从第 {rounds + 1} 轮继续")
    history: list[ModelMessage] = []
    while True:
        now_t = datetime.now().time()
        if now_t >= time(15, 5):  # 收盘后不再空转(8/17 曾跑到 15:10+ 浪费轮次)
            print("\n已过 15:05 收盘,看盘自动结束。盘后总结:uv run python -m trader.runner close YYYYMMDD")
            return
        if LUNCH_BREAK[0] < now_t < LUNCH_BREAK[1]:  # 午休数据静止,跑轮纯浪费
            wait_min = 13 * 60 - (now_t.hour * 60 + now_t.minute)
            print(f"午休中,睡 {wait_min} 分钟到 13:00 再继续")
            time_mod.sleep(max(60, wait_min * 60))
            continue
        rounds += 1
        now = datetime.now().strftime("%H:%M:%S")
        print(f"\n{'=' * 60}\n第 {rounds} 轮 · 实时看盘 {now}\n{'=' * 60}")
        prompt = load("round_live", rounds=rounds, now=now, date=today)
        result = _run_round(prompt, history)
        history = _trim_rounds(result.all_messages())
        _save_transcript("transcript_live", today, rounds, now,
                         result.all_messages(), result.usage)
        print(result.output)
        if max_rounds and rounds >= max_rounds:
            print(f"\n(达到 max_rounds={max_rounds},停止)")
            return
        if sleep_seconds > 0:
            time_mod.sleep(sleep_seconds)


def run_research(topic: str) -> None:
    """预期研究:对某主题跑一次完整研究(联网归因 → 写入预期库)。"""
    print(f"\n{'=' * 60}\n预期研究 · {topic}\n{'=' * 60}")
    result = _run_round(load("research", topic=topic), [], usage_limits=LONG_TASK_LIMITS)
    print(result.output)


def run_premarket(date: str, prev_date: str | None = None) -> None:
    """盘前分析:启动序列→八维催化扫描→预期更新→场景推演→预案,报告落库。
    prev_date 不传则自动推算上一交易日。"""
    prev_date = prev_date or _prev_trading_day(date)
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    wd = weekdays[datetime.strptime(date, "%Y%m%d").weekday()]
    # 周末专项只在隔周末(目标日是周一)时必做,平时明确写"跳过"防照搬框架
    gap = (datetime.strptime(date, "%Y%m%d") - datetime.strptime(prev_date, "%Y%m%d")).days
    note = f"目标日与上一交易日隔了 {gap - 1} 个自然日,必做不可跳过" if gap > 1 else "本次不隔周末,直接跳过本节并标注'不适用'"
    print(f"\n{'=' * 60}\n盘前分析 · 目标日 {date} {wd}(上一交易日 {prev_date})\n{'=' * 60}")
    result = _run_round(load("premarket", date=date, prev=prev_date, weekday=wd, weekend_note=note), [],
                        usage_limits=LONG_TASK_LIMITS)
    print(result.output)


def run_close(date: str) -> None:
    """盘后总结:预期逐个更新 → 收盘逐股扫描(新方向兜底)→ 交易复盘 → 合规自检 → 报告落库。"""
    print(f"\n{'=' * 60}\n收盘评估与复盘 · {date}\n{'=' * 60}")
    result = _run_round(load("close", date=date), [], usage_limits=LONG_TASK_LIMITS)
    print(result.output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="看盘循环运行器")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("replay", help="模拟看盘(回放历史日)")
    p.add_argument("date", help="回放日期 YYYYMMDD(需已 replay prepare)")
    p.add_argument("--interval", type=int, default=5, help="每轮步进分钟(默认 5)")
    p.add_argument("--max-rounds", type=int, default=None, help="最多轮数(调试)")
    p.add_argument("--resume", action="store_true",
                   help="接续该日上一次回放(不清日志/不重置账户,从最大轮号继续)")

    p = sub.add_parser("premarket", help="盘前分析(八维催化→场景推演→预案,报告落库)")
    p.add_argument("date", help="目标交易日 YYYYMMDD(如 20260817)")
    p.add_argument("prev_date", nargs="?", default=None,
                   help="上一交易日(不传则自动推算)")

    p = sub.add_parser("close", help="盘后总结(预期更新+逐股扫描+复盘+合规)")
    p.add_argument("date", help="交易日 YYYYMMDD(如 20260812)")

    p = sub.add_parser("research", help="预期研究(联网归因→写入预期库)")
    p.add_argument("topic", help="研究主题,如 '光纤供给紧缺涨价'")

    p = sub.add_parser("live", help="实时看盘")
    p.add_argument("--sleep", type=int, default=0, help="轮间等待秒(默认 0:立即下一轮)")
    p.add_argument("--max-rounds", type=int, default=None, help="最多轮数(调试)")

    args = parser.parse_args()
    if args.cmd == "replay":
        run_replay(args.date, args.interval, args.max_rounds, resume=args.resume)
    elif args.cmd == "premarket":
        run_premarket(args.date, args.prev_date)
    elif args.cmd == "close":
        run_close(args.date)
    elif args.cmd == "research":
        run_research(args.topic)
    else:
        run_live(args.sleep, args.max_rounds)
