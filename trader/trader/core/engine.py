"""core·引擎(平台通用件):读 systems manifest → 装配 agent → 驱动 single/loop 阶段。

一切看盘循环的通用机制(轮次计数/断点接续/上下文裁剪/重试/思考流落库/
午休跳过/收盘收工/T+1 结算/封场指标)都在这里,任何系统共用(实现设计 §3)。
"""
import json
import time as time_mod
from datetime import datetime, time, timedelta

from pydantic_ai import Agent
from pydantic_ai.capabilities import NativeTool
from pydantic_ai.messages import ModelMessage, ModelMessagesTypeAdapter
from pydantic_ai.native_tools import WebSearchTool
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from trader.core.bag import open_live, open_replay
from trader.core.context import set_context
from trader.core.ledger import Account, default_account
from trader.core.llm import build_model
from trader.core.registry import TOOLS, WRITE_TOOLS
from trader.core.runs import default_runs
from trader.prompts import load, sync_prompts

# 进程内存里只留最近 N 轮对话,防止全天看盘把上下文撑爆;
# 跨重启的记忆不靠对话,靠 documents 里的轮日志
KEEP_ROUNDS = 8

MORNING_START = time(9, 35)   # 回放起点:开盘后 5 分钟
LUNCH_BREAK = (time(11, 30), time(13, 0))
CLOSE = time(15, 0)


# ── agent 装配 ──────────────────────────────────────────

def build_agent(system_name: str) -> tuple[Agent, dict]:
    """按 systems 行装配 agent(工具白名单 + system prompt + 联网开关)。
    返回 (agent, manifest);白名单里不存在的工具名跳过并告警。"""
    from trader.core.systems import default_systems

    row = default_systems().get(system_name)
    if row is None:
        raise RuntimeError(f"系统 {system_name} 未注册(systems 表无此行)")
    manifest = row["manifest"]
    caps = [NativeTool(WebSearchTool(max_uses=3))] if manifest.get("web_search") else None
    agent = Agent(
        build_model(),
        capabilities=caps,
        system_prompt=load(manifest["system_prompt"]),
        model_settings=ModelSettings({"anthropic_thinking": {"type": "disabled"}},
                                     max_tokens=4000),
    )
    for name in manifest["tools"]:
        fn = TOOLS.get(name)
        if fn is None:
            print(f"  ⚠ 工具 {name} 不在注册表,已跳过(manifest 与代码不一致)")
            continue
        agent.tool(fn, retries=3) if name in WRITE_TOOLS else agent.tool(fn)
    return agent, manifest


# ── 阶段变量提供器(附录 14 已定:engine 内置通用提供器)──

def prev_trading_day(target: str) -> str:
    """上一交易日:目标日在最新数据之后→最新交易日;否则往前试探(节假日跳过)。"""
    from trader.core.market import _fetch_market_summary

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


def _stage_vars(stage: dict, **cli: str) -> dict:
    """按 manifest 声明的 vars 组装变量;date/now/rounds/clock 由调用方/循环注入。"""
    out = {k: v for k, v in cli.items() if v}
    date = cli.get("date", "")
    need = stage.get("vars", [])
    if date and any(v in need for v in ("prev", "weekday", "gap")):
        prev = cli.get("prev") or prev_trading_day(date)
        wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
            datetime.strptime(date, "%Y%m%d").weekday()]
        gap = (datetime.strptime(date, "%Y%m%d") - datetime.strptime(prev, "%Y%m%d")).days
        out.update({"prev": prev, "weekday": wd, "gap": gap})
    return out


# ── 通用轮次执行 ────────────────────────────────────────

def _run_round(agent: Agent, prompt: str, history: list[ModelMessage],
               usage_limits: UsageLimits | None = None, retries: int = 3):
    """跑一轮,失败重试(偶发 API 错误不崩整个看盘循环)。"""
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return agent.run_sync(prompt, message_history=history,
                                  usage_limits=usage_limits)
        except Exception as e:  # noqa: BLE001 —— API 网络抖动/限流等各种偶发
            last_err = e
            print(f"  ⚠ 本轮第 {attempt}/{retries} 次失败:{type(e).__name__}: {str(e)[:120]}")
            time_mod.sleep(2)
    raise RuntimeError(f"连续 {retries} 次失败,停止看盘:{last_err}")


def _trim_rounds(messages: list[ModelMessage], keep: int = KEEP_ROUNDS) -> list[ModelMessage]:
    """按轮切分(每轮以一个 user 提示开头),只留最近 keep 轮。"""
    starts = [i for i, m in enumerate(messages)
              if m.parts and getattr(m.parts[0], "part_kind", "") == "user-prompt"]
    if len(starts) <= keep:
        return messages
    return messages[starts[-keep]:]


def _save_transcript(stage: str, trade_date: str, round_no: int, clock: str,
                     messages: list[ModelMessage], usage) -> None:
    """思考流落库(轮次= rN;single 阶段 name='',附录 12 已定:统一落)。"""
    from trader.core.documents import default_documents

    try:
        content = json.dumps({
            "round": round_no, "time": clock,
            "usage": {k: getattr(usage, k, None)
                      for k in ("requests", "input_tokens", "output_tokens")},
            "messages": json.loads(ModelMessagesTypeAdapter.dump_json(messages)),
        }, ensure_ascii=False)
        default_documents().save(f"transcript_{stage}", content,
                                 name=(f"r{round_no}" if round_no else ""),
                                 trade_date=trade_date or None)
    except Exception as e:  # noqa: BLE001 —— 观测数据,尽力而为
        print(f"  ⚠ 思考流落盘失败:{type(e).__name__}: {str(e)[:80]}")


def _last_round(doc_type: str, trade_date: str) -> int:
    """当天轮日志最大轮号(断点接续用)。"""
    from trader.core.documents import default_documents

    best = 0
    for d in default_documents().list(doc_type, trade_date):
        name = (d.get("name") or "").strip()
        if name.startswith("r") and name[1:].isdigit():
            best = max(best, int(name[1:]))
    return best


# ── single 阶段(premarket/close/research,跑正本袋)────

def run_single(system_name: str, stage_name: str, **cli: str) -> None:
    """单次阶段:装配 → 注入变量 → 跑一次 → 思考流落库。产物由 AI 经工具写正本。"""
    agent, manifest = build_agent(system_name)
    stage = manifest["stages"][stage_name]
    set_context(0, None)  # single 阶段一律正本袋
    vars_ = _stage_vars(stage, **cli)
    date = cli.get("date", "")
    print(f"\n{'=' * 60}\n{system_name} · {stage_name} {date or vars_.get('topic', '')}\n{'=' * 60}")
    prompt = load(stage["prompt"], **vars_)
    result = _run_round(agent, prompt, [],
                        UsageLimits(request_limit=stage.get("request_limit", 200)))
    _save_transcript(stage_name, date, 0, datetime.now().strftime("%H:%M"),
                     result.all_messages(), result.usage)
    print(result.output)


# ── loop 阶段(live/replay)────────────────────────────

def run_live(system_name: str, stage_name: str = "live", sleep_seconds: int = 0,
             max_rounds: int | None = None) -> None:
    """实盘循环:写正本袋(bag 0)。跨重启按当日轮日志接续;午休跳过;15:05 收工。"""
    agent, manifest = build_agent(system_name)
    stage = manifest["stages"][stage_name]
    log_type = stage.get("log_type", "watch_live")
    today = datetime.now().strftime("%Y%m%d")
    runs = default_runs()
    run = runs.get(f"live-{today}")
    if run is None:
        run = runs.create(f"live-{today}", "live", today, _prompt_cover(manifest),
                          system=system_name)
        print(f"📦 档案袋已建:live-{today}(bag 0=正本,#run_{run['id']})")
    else:
        print(f"📦 接续档案袋:live-{today}(status={run['status']})")
    open_live(run["id"])
    unlocked = default_account().settle(datetime.now().date().isoformat())
    if unlocked:
        print(f"↺ T+1 结算:解锁 {unlocked} 只昨日持仓的可卖状态")
    rounds = _last_round(log_type, today)
    if rounds:
        print(f"↺ 接续今日看盘:已有 {rounds} 轮日志,从第 {rounds + 1} 轮继续")
    history: list[ModelMessage] = []
    limits = UsageLimits(request_limit=stage.get("request_limit", 50))
    try:
        while True:
            now_t = datetime.now().time()
            if now_t >= time(15, 5):
                print("\n已过 15:05 收盘,看盘自动结束。盘后总结:uv run python -m trader.runner close YYYYMMDD")
                break
            if LUNCH_BREAK[0] < now_t < LUNCH_BREAK[1]:
                wait_min = 13 * 60 - (now_t.hour * 60 + now_t.minute)
                print(f"午休中,睡 {wait_min} 分钟到 13:00 再继续")
                time_mod.sleep(max(60, wait_min * 60))
                continue
            rounds += 1
            now = datetime.now().strftime("%H:%M:%S")
            print(f"\n{'=' * 60}\n第 {rounds} 轮 · 实时看盘 {now}\n{'=' * 60}")
            result = _run_round(agent, load(stage["prompt"], rounds=rounds, now=now, date=today),
                                history, limits)
            history = _trim_rounds(result.all_messages())
            _save_transcript(stage_name, today, rounds, now,
                             result.all_messages(), result.usage)
            print(result.output)
            if max_rounds and rounds >= max_rounds:
                print(f"\n(达到 max_rounds={max_rounds},停止)")
                break
            if sleep_seconds > 0:
                time_mod.sleep(sleep_seconds)
    finally:
        runs.seal(run["id"], metrics=compute_metrics(0, today))
        print(f"📦 档案袋已封存:live-{today}")


def run_replay(system_name: str, date: str, stage_name: str = "replay",
               interval: int = 5, max_rounds: int | None = None, resume: bool = False,
               tag: str = "", opening: str = "fresh", custom_file: str = "",
               as_of: str = "") -> None:
    """模拟循环:一场一袋(行级 bag=run id),开局三模式(§6)。"""
    agent, manifest = build_agent(system_name)
    stage = manifest["stages"][stage_name]
    log_type = stage.get("log_type", "watch_replay")
    runs = default_runs()
    interval = interval or stage.get("interval", 5)
    if resume:
        cands = runs.list(kind="replay", trade_date=date)
        if not cands:
            print(f"⚠ {date} 没有可接续的回放场,按全新实验开始")
        run = cands[0]
        from trader.core.context import set_context as _sc
        bag = run.get("bag_id") or run["id"]
        _sc(bag, run["id"])
        done = _last_round(log_type, date)
        print(f"📦 接续档案袋:{run['name']}(bag {bag},已有 {done} 轮,从第 {done + 1} 轮继续)")
        rounds, hhmm = done, _resume_clock(log_type, date, done)
        fingerprint = run.get("fingerprint") or ""
    else:
        name = f"{date}-{tag}" if tag else f"{date}-{datetime.now():%H%M%S}"
        run = runs.create(name, "replay", date, _prompt_cover(manifest), system=system_name)
        bag = run["id"]
        runs.set_bag(run["id"], bag)
        custom = _load_custom(custom_file)
        fingerprint = open_replay(bag, date, opening, custom, as_of)
        runs.set_fingerprint(run["id"], fingerprint)
        warn = ("(⚠ fork 现状回放历史日=带未来持仓)" if opening == "fork" else "")
        print(f"📦 档案袋已建:{name}(bag {bag},开局 {opening},指纹 {fingerprint}){warn}")
        rounds, hhmm = 0, MORNING_START
    history: list[ModelMessage] = []
    limits = UsageLimits(request_limit=stage.get("request_limit", 50))
    try:
        while hhmm <= CLOSE:
            if LUNCH_BREAK[0] < hhmm < LUNCH_BREAK[1]:
                hhmm = LUNCH_BREAK[1]
            rounds += 1
            clock = hhmm.strftime("%H:%M")
            print(f"\n{'=' * 60}\n第 {rounds} 轮 · 模拟看盘 {date} {clock}\n{'=' * 60}")
            result = _run_round(agent, load(stage["prompt"], rounds=rounds, date=date, clock=clock),
                                history, limits)
            history = _trim_rounds(result.all_messages())
            _save_transcript(stage_name, date, rounds, clock,
                             result.all_messages(), result.usage)
            print(result.output)
            if max_rounds and rounds >= max_rounds:
                print(f"\n(达到 max_rounds={max_rounds},停止)")
                break
            minutes = hhmm.hour * 60 + hhmm.minute + interval
            hhmm = time(minutes // 60, minutes % 60)
    finally:
        runs.seal(run["id"], metrics=compute_metrics(bag, date))
        print(f"📦 档案袋已封存:{run['name']}(viewer「场次」可查;replay-rm 删除)")


def _resume_clock(doc_type: str, date: str, last_round: int) -> time:
    """接续回放:从最后一轮轮日志标题(# rN HH:MM)解析时钟,接不回来就从开盘重来。"""
    from trader.core.documents import default_documents
    import re

    doc = default_documents().get(doc_type, name=f"r{last_round}", trade_date=date)
    if doc:
        m = re.search(r"(\d{1,2}):(\d{2})", doc[:60])
        if m:
            return time(int(m.group(1)), int(m.group(2)))
    return MORNING_START


def _load_custom(path: str) -> dict | None:
    if not path:
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _prompt_cover(manifest: dict) -> dict:
    """封面:当次使用的各 prompt 版本(跑过的场不因后续编辑变化)。"""
    from trader.prompts import sync_prompts
    results = sync_prompts()
    changed = [r for r in results if r["changed"]]
    if changed:
        print("✎ prompt 版本入库:" + ", ".join(f"{r['name']}→v{r['version']}" for r in changed))
    return {r["name"]: r["version"] for r in results}


# ── 封场指标(§8:由流水推算,粒度=成交时点)────────────

def compute_metrics(bag: int, date: str) -> dict:
    """封场自动算:收益/净值曲线最大回撤/胜率盈亏比/计数。"""
    from trader.core.market import _fetch_quotes
    from trader.core.db import _connect

    acct = default_account()
    fills = acct.fills(bag)
    with _connect() as conn:
        wrow = conn.execute(
            "SELECT cash_cents, initial_cents FROM wallets WHERE bag_id=%s", (bag,)
        ).fetchone()
    initial = wrow["initial_cents"] if wrow else 100_000_00
    cash = wrow["cash_cents"] if wrow else 0
    # 净值曲线(fills 折叠,持仓按最近成交价估值)
    equity, curve = initial, []
    pos: dict[str, int] = {}
    last_px: dict[str, int] = {}
    for f in fills:
        code, qty, px = f["code"], f["quantity"], f["price_cents"]
        if f["side"] == "BUY":
            equity -= qty * px
            pos[code] = pos.get(code, 0) + qty
        else:
            equity += qty * px
            pos[code] = pos.get(code, 0) - qty
        last_px[code] = px
        mark = equity + sum(q * last_px[c] for c, q in pos.items() if q > 0)
        curve.append(mark)
    peak, max_dd = initial, 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            max_dd = max(max_dd, (peak - v) / peak)
    # 胜率/盈亏比(平仓回合)
    realized, avg_cost = [], {}
    for f in fills:
        code, qty, px = f["code"], f["quantity"], f["price_cents"]
        if f["side"] == "BUY":
            p = avg_cost.setdefault(code, {"qty": 0, "cost": 0})
            p["qty"] += qty
            p["cost"] += qty * px
        else:
            p = avg_cost.get(code)
            if p and p["qty"] > 0:
                unit = p["cost"] / p["qty"]
                realized.append((px - unit) * qty)
                p["qty"] -= qty
                p["cost"] -= unit * qty
    wins = [r for r in realized if r > 0]
    losses = [r for r in realized if r <= 0]
    positions = acct.positions(bag)
    cost_value = sum(p["quantity"] * round(p["avg_cost"] * 100) for p in positions)
    # 期末市值:优先回放收盘价,失败退成本
    market_value = cost_value
    try:
        if positions:
            qs = _fetch_quotes("replay", [p["code"] for p in positions], date)
            if qs:
                px_by = {q["code"]: round(q["price"] * 100) for q in qs}
                market_value = sum(p["quantity"] * px_by.get(p["code"], round(p["avg_cost"] * 100))
                                   for p in positions)
    except Exception:  # noqa: BLE001 —— 收盘价不可得时按成本
        pass
    asset = cash + market_value
    return {
        "initial": initial / 100, "cash": cash / 100, "asset": asset / 100,
        "pnl": (asset - initial) / 100, "return_pct": round((asset / initial - 1) * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "win_rate": round(len(wins) / len(realized) * 100, 1) if realized else None,
        "profit_factor": (round(sum(wins) / -sum(losses), 2)
                          if losses and sum(losses) < 0 else
                          (None if not wins else 999.0)),
        "n_fills": len(fills), "realized_trades": len(realized),
    }
