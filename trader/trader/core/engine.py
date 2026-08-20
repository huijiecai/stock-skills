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

from trader.core.portfolios import default_portfolios, open_experiment, open_live
from trader.core.context import set_context
from trader.core.events import emit, instrument, set_current_round
from trader.core.ledger import default_wallet
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

def build_agent(system_name: str, user_id: int = 0) -> tuple[Agent, dict, int]:
    """按 systems 行装配 agent(工具白名单 + system prompt + 联网开关,按用户命名空间)。
    返回 (agent, manifest, system_id);白名单里不存在的工具名跳过并告警。"""
    from trader.core.systems import default_systems

    row = default_systems().get(system_name, user_id)
    if row is None:
        raise RuntimeError(f"系统 {system_name} 未注册(systems 表无此行)")
    manifest = row["manifest"]
    caps = [NativeTool(WebSearchTool(max_uses=3))] if manifest.get("web_search") else None
    agent = Agent(
        build_model(),
        capabilities=caps,
        system_prompt=load(manifest["system_prompt"], system_id=row["id"], user_id=user_id),
        model_settings=ModelSettings({"anthropic_thinking": {"type": "disabled"}},
                                     max_tokens=4000),
    )
    for name in manifest["tools"]:
        fn = TOOLS.get(name)
        if fn is None:
            print(f"  ⚠ 工具 {name} 不在注册表,已跳过(manifest 与代码不一致)")
            continue
        fn = instrument(fn)   # 调用前后落事件 → 前端实时看思考过程
        agent.tool(fn, retries=3) if name in WRITE_TOOLS else agent.tool(fn)
    return agent, manifest, row["id"]


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

def run_single(system_name: str, stage_name: str, user_id: int = 0, **cli: str) -> None:
    """单次阶段:建 run 登记 → 装配 → 跑一次 → 思考流落库 → 封场。
    产物写用户的 live 账本袋;场次页可见。"""
    agent, manifest, system_id = build_agent(system_name, user_id)
    stage = manifest["stages"][stage_name]
    prow = default_portfolios().main_of(user_id, system_id)
    if prow is None:
        raise RuntimeError(f"用户 {user_id} 在系统 {system_name} 没有实盘组合(先在 web 创建)")
    portfolio_id = prow["id"]
    set_context(portfolio_id, None, user_id)
    vars_ = _stage_vars(stage, **cli)
    date = cli.get("date", "")

    # 建场次登记(让场次页可见)
    runs = default_runs()
    slug = f"{system_name}-{stage_name}-{date}-{datetime.now():%H%M%S}"
    try:
        run = runs.create(slug, "single", date,
                          _prompt_cover(manifest, system_id, user_id, stage_name),
                          system_id=system_id, user_id=user_id, stage=stage_name,
                          portfolio_id=portfolio_id)
    except ValueError:
        run = runs.get(slug, user_id)  # 同名重跑 → 接续
    from trader.core.context import set_context as _sc
    _sc(portfolio_id, run["id"], user_id)

    print(f"\n{'=' * 60}\n{system_name} · {stage_name} {date or vars_.get('topic', '')}\n{'=' * 60}")
    set_current_round(1)
    emit("round_start", body=f"单次分析 {date or vars_.get('topic', '')}")
    try:
        prompt = load(stage["prompt"], system_id=system_id, user_id=user_id, **vars_)
        result = _run_round(agent, prompt, [],
                            UsageLimits(request_limit=stage.get("request_limit", 200)))
        _save_transcript(stage_name, date, 0, datetime.now().strftime("%H:%M"),
                         result.all_messages(), result.usage)
        print(result.output)
    finally:
        emit("round_end", body="完成")
        runs.seal(run["id"])
        print(f"📦 已封存:{name}")


# ── loop 阶段(live/replay)────────────────────────────

def _stop_requested(run_id: int) -> bool:
    """优雅停止:web 置 status='stopping',循环每轮/等待分片轮询。
    DB 短暂不可用(Docker 重启等)当作未请求,保住进程。"""
    from trader.core.runs import default_runs
    try:
        r = default_runs().get_by_id(run_id)
        return bool(r) and r["status"] == "stopping"
    except Exception:
        return False


def _interruptible_sleep(seconds: int, run_id: int, chunk: int = 10) -> bool:
    """分片等待:每 chunk 秒查停止标志;返回 True=已请求停止。"""
    waited = 0
    while waited < seconds:
        if _stop_requested(run_id):
            return True
        step = min(chunk, seconds - waited)
        time_mod.sleep(step)
        waited += step
    return _stop_requested(run_id)


def run_live(system_name: str, stage_name: str = "live", sleep_seconds: int = 0,
             max_rounds: int | None = None, user_id: int = 0) -> None:
    """实盘循环:写该系统的实盘组合。跨重启按当日轮日志接续;午休跳过;15:05 收工。"""
    agent, manifest, system_id = build_agent(system_name, user_id)
    stage = manifest["stages"][stage_name]
    log_type = stage.get("log_type", "watch_live")
    today = datetime.now().strftime("%Y%m%d")
    runs = default_runs()
    prow = default_portfolios().main_of(user_id, system_id)
    if prow is None:
        raise RuntimeError(f"用户 {user_id} 在系统 {system_name} 没有实盘组合(先在 web 创建)")
    portfolio_id = prow["id"]
    run = runs.get(f"live-{today}", user_id)
    if run is None:
        run = runs.create(f"live-{today}", "live", today,
                          _prompt_cover(manifest, system_id, user_id, stage_name),
                          system_id=system_id, user_id=user_id, stage=stage_name,
                          portfolio_id=portfolio_id)
        print(f"📦 场次已建:live-{today}(组合 {portfolio_id}=实盘,#run_{run['id']})")
    else:
        print(f"📦 接续场次:live-{today}(status={run['status']})")
        if run["status"] != "running":
            runs.set_status(run["id"], "running")   # 停止/封存后再续:复活状态
    open_live(run["id"], portfolio_id, user_id)
    unlocked = default_wallet().settle(datetime.now().date().isoformat())
    if unlocked:
        print(f"↺ T+1 结算:解锁 {unlocked} 只昨日持仓的可卖状态")
    rounds = _last_round(log_type, today)
    if rounds:
        print(f"↺ 接续今日看盘:已有 {rounds} 轮日志,从第 {rounds + 1} 轮继续")
    history: list[ModelMessage] = []
    limits = UsageLimits(request_limit=stage.get("request_limit", 50))
    try:
        while True:
            if _stop_requested(run["id"]):
                print("\n⏹ 收到停止请求,完成收尾后退出(轮次与留痕完整,重新运行可接续)")
                break
            now_t = datetime.now().time()
            if now_t >= time(15, 5):
                print("\n已过 15:05 收盘,看盘自动结束。盘后总结:uv run python -m trader.runner close YYYYMMDD")
                break
            if LUNCH_BREAK[0] < now_t < LUNCH_BREAK[1]:
                wait_min = 13 * 60 - (now_t.hour * 60 + now_t.minute)
                print(f"午休中,睡 {wait_min} 分钟到 13:00 再继续")
                if _interruptible_sleep(max(60, wait_min * 60), run["id"]):
                    print("\n⏹ 午休中收到停止请求,退出")
                    break
                continue
            rounds += 1
            set_current_round(rounds)
            now = datetime.now().strftime("%H:%M:%S")
            print(f"\n{'=' * 60}\n第 {rounds} 轮 · 实时看盘 {now}\n{'=' * 60}")
            emit("round_start", body=f"第 {rounds} 轮 · 实时看盘 {now}")
            try:
                result = _run_round(agent,
                                    load(stage["prompt"], system_id=system_id, user_id=user_id,
                                         rounds=rounds, now=now, date=today),
                                    history, limits)
                history = _trim_rounds(result.all_messages())
                _save_transcript(stage_name, today, rounds, now,
                                 result.all_messages(), result.usage)
                print(result.output)
                if datetime.now().time() >= time(15, 0):
                    print("\n已过 15:00 收盘,收盘确认完成,看盘收工(收盘窗口只跑一轮,不再空转)")
                    break
            except Exception as e:  # 轮级容错:DB/LLM 瞬断不杀进程,重试本轮
                rounds -= 1
                emit("round_end", body=f"中断重试: {type(e).__name__}")
                print(f"⚠ 第 {rounds + 1} 轮中断({type(e).__name__}: {str(e)[:120]});"
                      f"60 秒后重试本轮,进程不退出")
                if _interruptible_sleep(60, run["id"]):
                    break
                continue
            emit("round_end", body="本轮完成")
            if max_rounds and rounds >= max_rounds:
                print(f"\n(达到 max_rounds={max_rounds},停止)")
                break
            if sleep_seconds > 0:
                if _interruptible_sleep(sleep_seconds, run["id"]):
                    print("\n⏹ 轮间隔中收到停止请求,退出")
                    break
    finally:
        try:
            runs.seal(run["id"], metrics=compute_metrics(portfolio_id, today))
            print(f"📦 场次已封存:live-{today}")
        except Exception as e:  # noqa: BLE001 —— 封场失败不崩,场留 running 可接续/强封
            print(f"⚠ 封场失败({type(e).__name__}),场留在 running——重新运行会接续,或 web 强制封存")


def run_replay(system_name: str, date: str, stage_name: str = "replay",
               interval: int = 5, max_rounds: int | None = None, resume: bool = False,
               tag: str = "", opening: str = "fresh", custom_file: str = "",
               as_of: str = "", user_id: int = 0) -> None:
    """重演循环:一场一个实验组合(发号登记),开局三模式,源=用户默认组合。"""
    agent, manifest, system_id = build_agent(system_name, user_id)
    stage = manifest["stages"][stage_name]
    log_type = stage.get("log_type", "watch_replay")
    runs = default_runs()
    interval = interval or stage.get("interval", 5)
    if resume:
        cands = runs.list(kind="replay", trade_date=date, user_id=user_id)
        if not cands:
            print(f"⚠ {date} 没有可接续的回放场,按全新实验开始")
        run = cands[0]
        from trader.core.context import set_context as _sc
        if run["status"] != "running":
            runs.set_status(run["id"], "running")   # 停止后再续:复活状态
        portfolio_id = run.get("portfolio_id") or run["id"]
        _sc(portfolio_id, run["id"], user_id)
        done = _last_round(log_type, date)
        print(f"📦 接续场次:{run['slug']}(组合 {portfolio_id},已有 {done} 轮,从第 {done + 1} 轮继续)")
        rounds, hhmm = done, _resume_clock(log_type, date, done)
        fingerprint = run.get("fingerprint") or ""
    else:
        slug = f"{date}-{tag}" if tag else f"{date}-{datetime.now():%H%M%S}"
        portfolio_id = default_portfolios().create(user_id, "experiment", system_id)
        run = runs.create(slug, "replay", date,
                          _prompt_cover(manifest, system_id, user_id, stage_name),
                          system_id=system_id, user_id=user_id, stage=stage_name,
                          clock="simulated", clock_date=date, portfolio_id=portfolio_id)
        custom = _load_custom(custom_file)
        fingerprint = open_experiment(portfolio_id, date, opening, custom, as_of,
                                      user_id=user_id,
                                      source_portfolio=default_portfolios().default_for(user_id),
                                      run_id=run["id"])
        runs.set_fingerprint(run["id"], fingerprint)
        warn = ("(⚠ fork 现状回放历史日=带未来持仓)" if opening == "fork" else "")
        print(f"📦 场次已建:{slug}(实验组合 {portfolio_id},开局 {opening},指纹 {fingerprint}){warn}")
        rounds, hhmm = 0, MORNING_START
    history: list[ModelMessage] = []
    limits = UsageLimits(request_limit=stage.get("request_limit", 50))
    try:
        while hhmm <= CLOSE:
            if _stop_requested(run["id"]):
                print("\n⏹ 收到停止请求,完成收尾后退出(重新运行 --resume 可接续)")
                break
            if LUNCH_BREAK[0] < hhmm < LUNCH_BREAK[1]:
                hhmm = LUNCH_BREAK[1]
            rounds += 1
            set_current_round(rounds)
            clock = hhmm.strftime("%H:%M")
            print(f"\n{'=' * 60}\n第 {rounds} 轮 · 模拟看盘 {date} {clock}\n{'=' * 60}")
            emit("round_start", body=f"第 {rounds} 轮 · 模拟看盘 {date} {clock}")
            try:
                result = _run_round(agent,
                                    load(stage["prompt"], system_id=system_id, user_id=user_id,
                                         rounds=rounds, date=date, clock=clock),
                                    history, limits)
                history = _trim_rounds(result.all_messages())
                _save_transcript(stage_name, date, rounds, clock,
                                 result.all_messages(), result.usage)
                print(result.output)
            except Exception as e:  # 轮级容错:DB/LLM 瞬断不杀进程,重试本轮
                rounds -= 1
                emit("round_end", body=f"中断重试: {type(e).__name__}")
                print(f"⚠ 第 {rounds + 1} 轮中断({type(e).__name__}: {str(e)[:120]});"
                      f"60 秒后重试本轮,进程不退出")
                if _interruptible_sleep(60, run["id"]):
                    break
                continue
            emit("round_end", body="本轮完成")
            if max_rounds and rounds >= max_rounds:
                print(f"\n(达到 max_rounds={max_rounds},停止)")
                break
            minutes = hhmm.hour * 60 + hhmm.minute + interval
            hhmm = time(minutes // 60, minutes % 60)
    finally:
        try:
            runs.seal(run["id"], metrics=compute_metrics(portfolio_id, date))
            print(f"📦 场次已封存:{run['slug']}(viewer「场次」可查;replay-rm 删除)")
        except Exception as e:  # noqa: BLE001 —— 封场失败不崩,场留 running 可接续/强封
            print(f"⚠ 封场失败({type(e).__name__}),场留在 running——重新运行会接续,或 web 强制封存")


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


def _prompt_cover(manifest: dict, system_id: int, user_id: int = 0, stage: str = "") -> dict:
    """封面:本场实际用到的 prompt 版本(系统设定 + 当前阶段;跑过的场不因后续编辑变化)。
    只记用到的——别的系统/别的阶段的 prompt 变动不影响本场封面,对比归因才干净。
    md 编辑面只属于 user 0(平台所有者),其他用户只读 PG。"""
    from trader.core.promptver import default_prompt_versions
    from trader.prompts import sync_prompts

    if user_id == 0:
        results = sync_prompts()
        changed = [r for r in results if r["changed"]]
        if changed:
            print("✎ prompt 版本入库:" + ", ".join(f"{r['slug']}→v{r['version']}" for r in changed))
    pv = default_prompt_versions()
    sdef = (manifest.get("stages") or {}).get(stage) or {}
    names = [manifest.get("system_prompt"), sdef.get("prompt")]
    out = {}
    for n in filter(None, names):
        rows = pv.versions(system_id, n, user_id=user_id)
        if rows:
            out[n] = rows[0]["version"]
    return out


# ── 封场指标(§8:由流水推算,粒度=成交时点)────────────

def compute_metrics(portfolio_id: int, date: str) -> dict:
    """封场自动算:收益/净值曲线最大回撤/胜率盈亏比/计数。"""
    from trader.core.market import _fetch_quotes
    from trader.core.db import _connect

    acct = default_wallet()
    fills = acct.fills(portfolio_id)
    with _connect() as conn:
        wrow = conn.execute(
            "SELECT cash_cents, initial_cents FROM wallets WHERE portfolio_id=%s",
            (portfolio_id,)
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
    positions = acct.positions(portfolio_id)
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
