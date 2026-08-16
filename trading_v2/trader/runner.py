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
import time as time_mod
from datetime import datetime, time

from pydantic_ai.messages import ModelMessage
from pydantic_ai.usage import UsageLimits

from trader.agent import agent
from trader.prompts import load

# 盘前/研究这类长任务(八维搜索+多轮工具)放宽请求上限;默认 50 不够用
LONG_TASK_LIMITS = UsageLimits(request_limit=200)

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


def run_replay(date: str, interval: int = 5, max_rounds: int | None = None) -> None:
    """模拟看盘:回放某日,每轮步进 interval 分钟,午休自动跳过。"""
    history: list[ModelMessage] = []
    hhmm = MORNING_START
    rounds = 0
    while hhmm <= CLOSE:
        if LUNCH_BREAK[0] < hhmm < LUNCH_BREAK[1]:  # 跳过午休
            hhmm = LUNCH_BREAK[1]
        rounds += 1
        clock = hhmm.strftime("%H:%M")
        print(f"\n{'=' * 60}\n第 {rounds} 轮 · 模拟看盘 {date} {clock}\n{'=' * 60}")
        prompt = load("round_replay", rounds=rounds, date=date, clock=clock)
        result = _run_round(prompt, history)
        history = result.all_messages()
        print(result.output)
        if max_rounds and rounds >= max_rounds:
            print(f"\n(达到 max_rounds={max_rounds},停止)")
            return
        minutes = hhmm.hour * 60 + hhmm.minute + interval
        hhmm = time(minutes // 60, minutes % 60)


def run_live(sleep_seconds: int = 0, max_rounds: int | None = None) -> None:
    """实时看盘:一轮结束马上下一轮(sleep=0 默认不等待),Ctrl+C 停止。"""
    history: list[ModelMessage] = []
    rounds = 0
    while True:
        rounds += 1
        now = datetime.now().strftime("%H:%M:%S")
        print(f"\n{'=' * 60}\n第 {rounds} 轮 · 实时看盘 {now}\n{'=' * 60}")
        prompt = load("round_live", rounds=rounds, now=now)
        result = _run_round(prompt, history)
        history = result.all_messages()
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


def run_premarket(date: str, prev_date: str) -> None:
    """盘前分析:启动序列→八维催化扫描→预期更新→场景推演→预案,报告落库。"""
    print(f"\n{'=' * 60}\n盘前分析 · 目标日 {date}(上一交易日 {prev_date})\n{'=' * 60}")
    result = _run_round(load("premarket", date=date, prev=prev_date), [],
                        usage_limits=LONG_TASK_LIMITS)
    print(result.output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="看盘循环运行器")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("replay", help="模拟看盘(回放历史日)")
    p.add_argument("date", help="回放日期 YYYYMMDD(需已 replay prepare)")
    p.add_argument("--interval", type=int, default=5, help="每轮步进分钟(默认 5)")
    p.add_argument("--max-rounds", type=int, default=None, help="最多轮数(调试)")

    p = sub.add_parser("premarket", help="盘前分析(八维催化→场景推演→预案,报告落库)")
    p.add_argument("date", help="目标交易日 YYYYMMDD(如 20260812)")
    p.add_argument("prev_date", help="上一交易日 YYYYMMDD(如 20260811)")

    p = sub.add_parser("research", help="预期研究(联网归因→写入预期库)")
    p.add_argument("topic", help="研究主题,如 '光纤供给紧缺涨价'")

    p = sub.add_parser("live", help="实时看盘")
    p.add_argument("--sleep", type=int, default=0, help="轮间等待秒(默认 0:立即下一轮)")
    p.add_argument("--max-rounds", type=int, default=None, help="最多轮数(调试)")

    args = parser.parse_args()
    if args.cmd == "replay":
        run_replay(args.date, args.interval, args.max_rounds)
    elif args.cmd == "premarket":
        run_premarket(args.date, args.prev_date)
    elif args.cmd == "research":
        run_research(args.topic)
    else:
        run_live(args.sleep, args.max_rounds)
