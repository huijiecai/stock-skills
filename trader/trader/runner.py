"""运行器:看盘循环入口(premarket / live / replay / close / research)。

档案袋模型(核心设计§2):每次看盘一场,一场一袋。
- live:public schema(钱包连续/知识库正本/预案连续),跨重启按当日轮日志接续
- replay:独立 schema 袋(钱包从零+预期快照+预案复制+轮日志/思考流全袋内),
  --tag 命名(同日同名拒绝),缺省时间戳名;--resume 接续该日最近一场;永不自动删除
"""

import argparse
import json
import re
import time as time_mod
from datetime import datetime, time, timedelta

from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.usage import UsageLimits

from trader.agent import agent
from trader.prompts import load, sync_prompts
from trader.store import default_account, default_documents
from trader.tools.market import _fetch_market_summary

# 盘前/研究这类长任务(八维搜索+多轮工具)放宽请求上限;默认 50 不够用
LONG_TASK_LIMITS = UsageLimits(request_limit=200)

# 进程内存里只留最近 N 轮对话,防止全天看盘把上下文撑爆;
# 跨重启的记忆不靠对话,靠 documents 里的轮日志(watch_live/watch_replay)
KEEP_ROUNDS = 8

MORNING_START = time(9, 35)   # 回放起点:开盘后 5 分钟
LUNCH_BREAK = (time(11, 30), time(13, 0))
CLOSE = time(15, 0)


def _prev_trading_day(target: str) -> str:
    """上一交易日:目标日在最新数据之后→最新交易日;否则往前试探(节假日跳过)。"""
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


def _trim_rounds(messages: list[ModelMessage], keep: int = KEEP_ROUNDS) -> list[ModelMessage]:
    """按轮切分(每轮以一个 user 提示开头),只留最近 keep 轮。"""
    starts = [i for i, m in enumerate(messages)
              if m.parts and getattr(m.parts[0], "part_kind", "") == "user-prompt"]
    if len(starts) <= keep:
        return messages
    return messages[starts[-keep]:]


def _last_round(doc_type: str, trade_date: str) -> int:
    """从当前上下文的文档库读当天轮日志的最大轮号(袋内=袋,实盘=public)。"""
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
    """每轮完整思考流落库(工具调用/返回/推理的原始消息流,JSON)。"""
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


def _sync_prompts() -> dict:
    """同步本地 prompt → PG 版本库,返回封面用的 {name: version}。有变更才提示。"""
    results = sync_prompts()
    changed = [r for r in results if r["changed"]]
    if changed:
        detail = ", ".join(f"{r['name']}→v{r['version']}" for r in changed)
        print(f"✎ prompt 版本入库:{detail}")
    return {r["name"]: r["version"] for r in results}


# ══════════════════════════════════════════════════════════
# 模拟看盘(档案袋)
# ══════════════════════════════════════════════════════════

def run_replay(date: str, interval: int = 5, max_rounds: int | None = None,
               resume: bool = False, tag: str = "") -> None:
    """模拟看盘:一场一袋,全袋隔离(钱包/预期快照/预案/思考流)。"""
    import trader.store as store

    pv = _sync_prompts()
    runs = store.default_runs()
    if resume:
        cands = runs.list(kind="replay", trade_date=date)
        if not cands:
            print(f"⚠ {date} 没有可接续的回放场,按全新实验开始")
        run = cands[0]  # list 倒序,第一个=最近
        store.bind_run_schema(run["schema_name"])
        done = _last_round("watch_replay", date)
        print(f"📦 接续档案袋:{run['name']}(已有 {done} 轮,从第 {done + 1} 轮继续)")
        rounds, hhmm = done, _resume_clock(date, done)
    else:
        name = f"{date}-{tag}" if tag else f"{date}-{datetime.now():%H%M%S}"
        run = runs.create(name, "replay", date, pv)
        schema = f"run_{run['id']}"
        runs.set_schema(run["id"], schema)
        store.bind_run_schema(schema)          # 三单例切进袋子(账户/预期/文档)
        fp = store.Runs.snapshot_expectations("public", schema)
        ndocs = store.Runs.copy_docs("public", schema, ("premarket", "close"), date)
        default_account().reset()               # 钱包从初始资金开始
        print(f"📦 档案袋已建:{name}(预期快照指纹 {fp},预案/收盘 {ndocs} 份,钱包 ¥100,000 从零)")
        rounds, hhmm = 0, MORNING_START
    history: list[ModelMessage] = []
    try:
        _replay_loop(date, interval, max_rounds, rounds, hhmm, history)
    finally:
        runs.seal(run["id"])
        print(f"📦 档案袋已封存:{run['name']}(viewer「场次」可查;replay-rm 删除)")


def _replay_loop(date: str, interval: int, max_rounds: int | None,
                 rounds: int, hhmm, history: list[ModelMessage]) -> None:
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


# ══════════════════════════════════════════════════════════
# 单次任务
# ══════════════════════════════════════════════════════════

def run_research(topic: str) -> None:
    """预期研究:对某主题跑一次完整研究(联网归因 → 写入预期库)。"""
    _sync_prompts()
    print(f"\n{'=' * 60}\n预期研究 · {topic}\n{'=' * 60}")
    result = _run_round(load("research", topic=topic), [], usage_limits=LONG_TASK_LIMITS)
    print(result.output)


def run_premarket(date: str, prev_date: str | None = None) -> None:
    """盘前分析:启动序列→八维催化扫描→预期更新→场景推演→预案,报告落库。"""
    prev_date = prev_date or _prev_trading_day(date)
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    wd = weekdays[datetime.strptime(date, "%Y%m%d").weekday()]
    gap = (datetime.strptime(date, "%Y%m%d") - datetime.strptime(prev_date, "%Y%m%d")).days
    note = (f"目标日与上一交易日隔了 {gap - 1} 个自然日,必做不可跳过" if gap > 1
            else "本次不隔周末,直接跳过本节并标注'不适用'")
    _sync_prompts()
    print(f"\n{'=' * 60}\n盘前分析 · 目标日 {date} {wd}(上一交易日 {prev_date})\n{'=' * 60}")
    result = _run_round(load("premarket", date=date, prev=prev_date, weekday=wd, weekend_note=note),
                        [], usage_limits=LONG_TASK_LIMITS)
    print(result.output)


def run_close(date: str) -> None:
    """盘后总结:预期逐个更新 → 收盘逐股扫描(新方向兜底)→ 交易复盘 → 合规自检 → 报告落库。"""
    _sync_prompts()
    print(f"\n{'=' * 60}\n收盘评估与复盘 · {date}\n{'=' * 60}")
    result = _run_round(load("close", date=date), [], usage_limits=LONG_TASK_LIMITS)
    print(result.output)


# ══════════════════════════════════════════════════════════
# 实时看盘(档案袋:public schema,钱包连续)
# ══════════════════════════════════════════════════════════

def run_live(sleep_seconds: int = 0, max_rounds: int | None = None) -> None:
    """实时看盘:每轮间隔 sleep 秒,Ctrl+C/收盘停。跨重启按当日轮日志接续;
    午休自动跳过;15:05 自动收工;T+1 日结解锁昨日持仓。"""
    from trader.store import default_runs

    pv = _sync_prompts()
    today = datetime.now().strftime("%Y%m%d")
    runs = default_runs()
    run = runs.get(f"live-{today}")
    if run is None:
        run = runs.create(f"live-{today}", "live", today, pv)
        runs.set_schema(run["id"], "public")
        print(f"📦 档案袋已建:live-{today}(#run_{run['id']})")
    else:
        print(f"📦 接续档案袋:live-{today}(status={run['status']})")
    # T+1 日结:昨天买的今天解锁可卖(8/18 剑桥减仓曾被 sellable=0 拦住)
    unlocked = default_account().settle(datetime.now().date().isoformat())
    if unlocked:
        print(f"↺ T+1 结算:解锁 {unlocked} 只昨日持仓的可卖状态")
    rounds = _last_round("watch_live", today)
    if rounds:
        print(f"↺ 接续今日看盘:已有 {rounds} 轮日志,从第 {rounds + 1} 轮继续")
    history: list[ModelMessage] = []
    try:
        _live_loop(sleep_seconds, max_rounds, today, rounds, history)
    finally:
        default_runs().seal(run["id"])
        print(f"📦 档案袋已封存:live-{today}")


def _live_loop(sleep_seconds: int, max_rounds: int | None, today: str,
               rounds: int, history: list[ModelMessage]) -> None:
    while True:
        now_t = datetime.now().time()
        if now_t >= time(15, 5):  # 收盘后不再空转
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


# ══════════════════════════════════════════════════════════
# CLI
# ══════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="看盘循环运行器")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("replay", help="模拟看盘(一场一袋,全袋隔离)")
    p.add_argument("date", help="回放日期 YYYYMMDD(需已同步行情)")
    p.add_argument("--interval", type=int, default=5, help="每轮步进分钟(默认 5)")
    p.add_argument("--max-rounds", type=int, default=None, help="最多轮数(调试)")
    p.add_argument("--resume", action="store_true", help="接续该日最近一场回放")
    p.add_argument("--tag", default="", help="场次命名(同日同名拒绝;缺省用时间戳)")

    p2 = sub.add_parser("replay-rm", help="删除某场回放(袋子整体销毁,显式操作)")
    p2.add_argument("name", help="场次名(replay-ls 查看)")

    p3 = sub.add_parser("replay-ls", help="列出回放场次")
    p3.add_argument("--date", default="", help="按日期过滤 YYYYMMDD")

    p = sub.add_parser("premarket", help="盘前分析(八维催化→场景推演→预案,报告落库)")
    p.add_argument("date", help="目标交易日 YYYYMMDD")
    p.add_argument("prev_date", nargs="?", default=None, help="上一交易日(自动推算)")

    p = sub.add_parser("close", help="盘后总结(预期更新+逐股扫描+复盘+合规)")
    p.add_argument("date", help="交易日 YYYYMMDD")

    p = sub.add_parser("research", help="预期研究(联网归因→写入预期库)")
    p.add_argument("topic", help="研究主题")

    p = sub.add_parser("live", help="实时看盘")
    p.add_argument("--sleep", type=int, default=0, help="轮间等待秒(默认 0)")
    p.add_argument("--max-rounds", type=int, default=None, help="最多轮数(调试)")

    args = parser.parse_args()
    if args.cmd == "replay":
        run_replay(args.date, args.interval, args.max_rounds, resume=args.resume, tag=args.tag)
    elif args.cmd == "replay-rm":
        from trader.store import default_runs
        n = default_runs().delete(args.name)
        print(f"已删除场次 {args.name}(袋子整体销毁)" if n else f"没有这个场次:{args.name}")
    elif args.cmd == "replay-ls":
        from tabulate import tabulate
        from trader.store import default_runs
        rows = default_runs().list(kind="replay", trade_date=args.date or None)
        print(tabulate([[r["id"], r["name"], r["status"],
                         (r["prompt_versions"] or "")[:40], r["created_at"][:16]] for r in rows],
                       headers=["#", "场次", "状态", "prompt版本", "建档"], tablefmt="plain")
              if rows else "(没有回放场次)")
    elif args.cmd == "premarket":
        run_premarket(args.date, args.prev_date)
    elif args.cmd == "close":
        run_close(args.date)
    elif args.cmd == "research":
        run_research(args.topic)
    else:
        run_live(args.sleep, args.max_rounds)
