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
from trader.core.context import (ContextAssembler, RuntimeEnvelope, set_context,
                                 set_execution_mode)
from trader.core.events import emit, instrument, set_current_round
from trader.core.ledger import default_wallet
from trader.core.llm import build_model
from trader.core.log import get_logger
from trader.core.registry import TOOLS, WRITE_TOOLS, capability_enabled, capability_tools
from trader.core.runs import default_runs
from trader.core.stageio import (
    inject_stage_context,
    loop_output_type,
    publish_stage_outputs,
    stage_contract,
)
from trader.core.valuation import compute_metrics
from trader.prompts import load

# 进程内存里只留最近 N 轮对话,防止全天看盘把上下文撑爆;
# 跨重启的记忆不靠对话,靠 documents 里的轮日志
KEEP_ROUNDS = 8

log = get_logger(__name__)   # 诊断日志;AI 轮输出与分隔横幅是 CLI 界面,保持 print(ADR-0013)

MORNING_START = time(9, 35)   # 回放起点:开盘后 5 分钟
LUNCH_BREAK = (time(11, 30), time(13, 0))
CLOSE = time(15, 0)


# ── agent 装配 ──────────────────────────────────────────

def build_agent(system_name: str, user_id: int = 0,
                stage_name: str | None = None,
                execution_mode: str | None = None) -> tuple[Agent, dict, int]:
    """按系统策略和运行时钟装配 agent，返回 agent、manifest、system id。"""
    from trader.core.systems import default_systems

    row = default_systems().get(system_name, user_id)
    if row is None:
        raise RuntimeError(f"系统 {system_name} 未注册(systems 表无此行)")
    manifest = row["manifest"]
    caps = [NativeTool(WebSearchTool(max_uses=3))] \
        if capability_enabled(manifest, stage_name, "research.web_search") else None
    agent = Agent(
        build_model(),
        capabilities=caps,
        system_prompt=load(manifest["system_prompt"], system_id=row["id"], user_id=user_id),
        model_settings=ModelSettings({"anthropic_thinking": {"type": "disabled"}},
                                     max_tokens=4000),
    )
    for name in capability_tools(manifest, stage_name, execution_mode):
        fn = TOOLS.get(name)
        if fn is None:
            log.warning(f"工具 {name} 不在注册表,已跳过(manifest 与代码不一致)")
            continue
        fn = instrument(fn)   # 调用前后落事件 → 前端实时看思考过程
        agent.tool(fn, retries=3) if name in WRITE_TOOLS else agent.tool(fn)
    return agent, manifest, row["id"]


# ── 阶段变量提供器(engine 内置通用提供器,见 docs/adr/0004)──

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


def _derive_date_vars(date: str, prev: str = "") -> tuple[str, str, int]:
    """由 date 推派生变量(上一交易日/星期/间隔天数)——运行时与契约同源。"""
    prev = prev or prev_trading_day(date)
    wd = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][
        datetime.strptime(date, "%Y%m%d").weekday()]
    gap = (datetime.strptime(date, "%Y%m%d") - datetime.strptime(prev, "%Y%m%d")).days
    return prev, wd, gap


def _stage_vars(stage: dict, **cli: str) -> dict:
    """按调用参数组装变量;date/now/rounds/clock 由调用方/循环注入。
    派生三件套(prev/weekday/gap)只要有 date 就推算,不看 manifest 声明,
    多余变量对 format 无害(8/24 盘前事故与决策见 ADR-0003)。"""
    out = {k: v for k, v in cli.items() if v}
    date = cli.get("date", "")
    if date:
        prev, wd, gap = _derive_date_vars(date, cli.get("prev", ""))
        out.update({"prev": prev, "weekday": wd, "gap": gap})
    return out


def stage_var_schema(stage: dict, date: str = "") -> dict:
    """阶段变量契约:该阶段 prompt 可用的占位符(编辑器变量面板/占位符 lint/
    替换预览共用,与 _stage_vars 运行时同源)。date 给定时派生变量算真值。

    kind 推导:single(含声明变量);loop+interval=replay(rounds/date/clock);
    loop 无 interval=live(rounds/now/date)。"""
    def v(name: str, desc: str, example: str, source: str, value=None) -> dict:
        return {"name": name, "desc": desc, "example": example,
                "source": source, "value": value}

    declared = stage.get("vars", [])
    if stage.get("kind") != "loop":                     # single(单次阶段)
        # 派生三件套随 date 自动可用(与 _stage_vars 同规则,不依赖声明);
        # date 本身与调用方变量(research 的 topic 等)由发起时传入
        vars_ = [
            v("date", "目标交易日 YYYYMMDD(发起时填,填了才有派生三件套)", "20260824", "caller"),
            v("prev", "上一交易日(自动推算,跳过节假日)", "20260821", "auto"),
            v("weekday", "星期几(中文,由 date 推)", "周一", "auto"),
            v("gap", "距上一交易日的自然日天数", "3", "auto"),
        ]
        for extra in declared:
            if extra in ("date", "prev", "weekday", "gap"):
                continue
            vars_.append(v(extra, "调用发起时传入", "", "caller"))
        if date:
            prev, wd, gap = _derive_date_vars(date)
            for item in vars_:
                item["value"] = {"date": date, "prev": prev,
                                 "weekday": wd, "gap": gap}.get(item["name"])
        return {"kind": "single", "vars": vars_}
    if stage.get("interval"):                           # loop + interval = 重演
        return {"kind": "replay", "vars": [
            v("rounds", "当前轮次号(从 1 起,每轮 +1)", "12", "auto"),
            v("date", "回放的交易日 YYYYMMDD", "20260819", "auto"),
            v("clock", "模拟时钟 HH:MM(按 interval 每轮前进)", "10:35", "auto"),
        ]}
    return {"kind": "live", "vars": [                   # loop 实时
        v("rounds", "当前轮次号(从 1 起,每轮 +1)", "12", "auto"),
        v("now", "实时时刻 HH:MM:SS(每轮取当下)", "10:35:02", "auto"),
        v("date", "当天交易日 YYYYMMDD", "20260821", "auto"),
    ]}


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
            log.warning(f"本轮第 {attempt}/{retries} 次失败:{type(e).__name__}: {str(e)[:120]}")
            time_mod.sleep(2)
    raise RuntimeError(f"连续 {retries} 次失败,停止看盘:{last_err}")


def _assemble_context(manifest: dict, system_name: str, stage_name: str,
                      run_id: int | None, user_id: int, portfolio_id: int,
                      mode: str, variables: dict, docs=None,
                      run_inputs: dict | None = None) -> str:
    """Build the platform-owned context envelope and declared stage inputs."""
    envelope = RuntimeEnvelope(
        system=system_name,
        stage=stage_name,
        run_id=run_id,
        user_id=user_id,
        portfolio_id=portfolio_id,
        mode=mode,
        date=str(variables.get("date", "")),
        clock=str(variables.get("clock", variables.get("now", ""))),
        round_no=int(variables.get("rounds", 0) or 0),
        variables=dict(variables),
    )
    set_execution_mode(mode, envelope.date, envelope.clock)
    assembled = ContextAssembler().assemble(
        manifest, stage_name, variables, envelope, docs=docs,
        run_inputs=run_inputs,
    )
    # Context assembly is part of the run evidence.  Keep event payloads
    # bounded; documents and snapshots remain available through their normal
    # stores and document/run links.
    evidence = assembled.evidence()
    for item in evidence["inputs"]:
        if isinstance(item.get("content"), str) and len(item["content"]) > 1000:
            item["content"] = item["content"][:1000] + "...(truncated)"
    emit("context", body=json.dumps(evidence, ensure_ascii=False, default=str)[:8000])
    return assembled.render()


def _resume_run_inputs(runs, run: dict, requested_inputs: dict) -> dict:
    """Keep a resumed Run bound to the request frozen when it was created."""
    frozen_inputs = run.get("run_inputs") or {}
    if requested_inputs and frozen_inputs and requested_inputs != frozen_inputs:
        raise RuntimeError("接续场次的本次任务与原场次不一致，请新建场次")
    runs.set_run_inputs_if_empty(run["id"], requested_inputs)
    return frozen_inputs or requested_inputs


def _trim_rounds(messages: list[ModelMessage], keep: int = KEEP_ROUNDS) -> list[ModelMessage]:
    """按轮切分(每轮以一个 user 提示开头),只留最近 keep 轮。"""
    starts = [i for i, m in enumerate(messages)
              if m.parts and getattr(m.parts[0], "part_kind", "") == "user-prompt"]
    if len(starts) <= keep:
        return messages
    return messages[starts[-keep]:]


def _save_transcript(stage: str, trade_date: str, round_no: int, clock: str,
                     messages: list[ModelMessage], usage) -> None:
    """思考流落库(轮次= rN;single 阶段 name='';统一落库,见 ADR-0005)。"""
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
        log.warning(f"思考流落盘失败:{type(e).__name__}: {str(e)[:80]}")


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

def run_single(system_name: str, stage_name: str, user_id: int = 0,
               clock: str = "real", prompt_version: int | None = None,
               opening: str = "fresh", portfolio_type: str = "main",
               instruction: str = "", **cli: str) -> None:
    """单次阶段:建 run 登记 → 装配 → 跑一次 → 思考流落库 → 封场。
    产物写用户的 live 账本袋;场次页可见。"""
    execution_mode = (
        "replay" if clock == "simulated"
        else "paper" if portfolio_type == "paper" else "real"
    )
    agent, manifest, system_id = build_agent(
        system_name, user_id, stage_name, execution_mode
    )
    stage = manifest["stages"][stage_name]
    main = default_portfolios().main_of(user_id, system_id)
    if main is None:
        raise RuntimeError(f"用户 {user_id} 在系统 {system_name} 没有实盘组合(先在 web 创建)")
    vars_ = _stage_vars(stage, **cli)
    run_inputs = ({"instruction": instruction.strip()} if instruction.strip() else {})
    date = cli.get("date", "")
    if clock == "simulated":
        portfolio_id = default_portfolios().create(user_id, "experiment", system_id,
                                                   name=f"{date} {stage_name}")
    elif portfolio_type == "paper":
        portfolio_id = default_portfolios().ensure_paper(user_id, system_id)
        set_context(portfolio_id, None, user_id)
    else:
        portfolio_id = main["id"]
        set_context(portfolio_id, None, user_id)

    # 建场次登记(让场次页可见)
    runs = default_runs()
    slug = f"{system_name}-{stage_name}-{date}-{datetime.now():%H%M%S}"
    try:
        run = runs.create(slug, "single", date,
                          _prompt_cover(manifest, system_id, user_id, stage_name, prompt_version),
                          system_id=system_id, user_id=user_id, stage=stage_name,
                          portfolio_id=portfolio_id, clock=clock,
                          clock_date=date if clock == "simulated" else None,
                          stage_contract=stage_contract(stage_name, stage),
                          run_inputs=run_inputs)
    except ValueError:
        run = runs.get(slug, user_id)  # 同名重跑 → 接续
        run_inputs = _resume_run_inputs(runs, run, run_inputs)
    from trader.core.context import set_context as _sc
    if clock == "simulated":
        fingerprint = open_experiment(portfolio_id, date, opening, user_id=user_id,
                                      source_portfolio=main["id"], run_id=run["id"])
        runs.set_fingerprint(run["id"], fingerprint)
    else:
        _sc(portfolio_id, run["id"], user_id)

    print(f"\n{'=' * 60}\n{system_name} · {stage_name} {date or vars_.get('topic', '')}\n{'=' * 60}")
    set_current_round(1)
    emit("round_start", body=f"单次分析 {date or vars_.get('topic', '')}")
    try:
        runs.touch(run["id"])   # 单次阶段可能跑很久,开跑先刷心跳
        set_execution_mode(execution_mode)
        context = _assemble_context(
            manifest, system_name, stage_name, run["id"], user_id,
            portfolio_id, execution_mode, vars_, run_inputs=run_inputs
        )
        prompt = load(stage["prompt"], system_id=system_id, user_id=user_id,
                      prompt_version=prompt_version, **vars_)
        result = _run_round(agent, inject_stage_context(prompt, context), [],
                            UsageLimits(request_limit=stage.get("request_limit", 200)))
        publish_stage_outputs(stage_name, stage, vars_, result.output)
        _save_transcript(stage_name, date, 0, datetime.now().strftime("%H:%M"),
                         result.all_messages(), result.usage)
        print(result.output)
        emit("round_end", body="完成")
        runs.seal(run["id"])
        log.info(f"📦 已封存:{slug}")
    except Exception as e:  # noqa: BLE001 —— 失败不伪装成完成:留错误事件+指标,页面上看得见
        emit("round_end", body=f"✗ 失败:{type(e).__name__}: {str(e)[:300]}")
        runs.seal(run["id"], metrics={"error": f"{type(e).__name__}: {str(e)[:500]}",
                                      "status": "failed"})
        log.error(f"✗ {slug} 失败:{type(e).__name__}: {e}")
        raise


# ── loop 阶段(live/replay)────────────────────────────

def _stop_requested(run_id: int) -> bool:
    """优雅停止:web 置 status='stopping',循环每轮/等待分片轮询。
    poll 顺带刷心跳——前端可区分"真在跑"与"进程僵死(机器睡眠/被杀)";
    DB 短暂不可用(Docker 重启等)当作未请求,保住进程。"""
    from trader.core.runs import default_runs
    try:
        return default_runs().poll(run_id) == "stopping"
    except Exception:
        return False


def _interruptible_sleep(seconds: int, run_id: int, chunk: int = 10) -> bool:
    """分片等待:每 chunk 秒查停止标志;返回 True=已请求停止。
    看墙上时钟 deadline 而非累计——机器睡眠/进程冻结后唤醒,发现已过期立即返回,
    午休/轮间隔不会被拉长(monotonic/sleep 在 macOS 睡眠期间都不走表,只能看表)。"""
    deadline = time_mod.time() + seconds
    while (left := deadline - time_mod.time()) > 0:
        if _stop_requested(run_id):
            return True
        time_mod.sleep(min(chunk, left))
    return _stop_requested(run_id)


def run_live(system_name: str, stage_name: str = "live", sleep_seconds: int = 0,
             max_rounds: int | None = None, user_id: int = 0,
             prompt_version: int | None = None,
             portfolio_type: str = "main", instruction: str = "") -> None:
    """实盘循环:写该系统的实盘组合。跨重启按当日轮日志接续;午休跳过;15:05 收工。"""
    execution_mode = "paper" if portfolio_type == "paper" else "real"
    agent, manifest, system_id = build_agent(
        system_name, user_id, stage_name, execution_mode
    )
    stage = manifest["stages"][stage_name]
    log_type = loop_output_type(stage, "watch_live")
    today = datetime.now().strftime("%Y%m%d")
    runs = default_runs()
    if portfolio_type == "paper":
        portfolio_id = default_portfolios().ensure_paper(user_id, system_id)
    else:
        prow = default_portfolios().main_of(user_id, system_id)
        if prow is None:
            raise RuntimeError(f"用户 {user_id} 在系统 {system_name} 没有主组合")
        portfolio_id = prow["id"]
    run_kind = "paper" if portfolio_type == "paper" else "live"
    run_slug = f"{system_name}-{stage_name}-{portfolio_type}-{today}"
    requested_inputs = ({"instruction": instruction.strip()} if instruction.strip() else {})
    run = runs.get(run_slug, user_id)
    if run is None:
        run = runs.create(run_slug, run_kind, today,
                          _prompt_cover(manifest, system_id, user_id, stage_name, prompt_version),
                          system_id=system_id, user_id=user_id, stage=stage_name,
                          portfolio_id=portfolio_id,
                          stage_contract=stage_contract(stage_name, stage),
                          run_inputs=requested_inputs)
        log.info(f"📦 场次已建:{run_slug}(组合 {portfolio_id}=实盘,#run_{run['id']})")
    else:
        requested_inputs = _resume_run_inputs(runs, run, requested_inputs)
        log.info(f"📦 接续场次:{run_slug}(status={run['status']})")
        if run["status"] != "running":
            runs.set_status(run["id"], "running")   # 停止/封存后再续:复活状态
        runs.set_stage_contract_if_empty(run["id"], stage_contract(stage_name, stage))
    open_live(run["id"], portfolio_id, user_id)
    unlocked = default_wallet().settle(datetime.now().date().isoformat())
    if unlocked:
        log.info(f"↺ T+1 结算:解锁 {unlocked} 只昨日持仓的可卖状态")
    rounds = _last_round(log_type, today)
    if rounds:
        log.info(f"↺ 接续今日看盘:已有 {rounds} 轮日志,从第 {rounds + 1} 轮继续")
    history: list[ModelMessage] = []
    set_current_round(0)
    limits = UsageLimits(request_limit=stage.get("request_limit", 50))
    try:
        set_execution_mode(execution_mode)
        while True:
            if _stop_requested(run["id"]):
                log.info("⏹ 收到停止请求,完成收尾后退出(轮次与留痕完整,重新运行可接续)")
                break
            now_t = datetime.now().time()
            if now_t >= time(15, 5):
                log.info("已过 15:05 收盘,看盘自动结束。盘后总结:uv run python -m trader.runner close YYYYMMDD")
                break
            if LUNCH_BREAK[0] < now_t < LUNCH_BREAK[1]:
                wait_min = 13 * 60 - (now_t.hour * 60 + now_t.minute)
                log.info(f"午休中,睡 {wait_min} 分钟到 13:00 再继续")
                if _interruptible_sleep(max(60, wait_min * 60), run["id"]):
                    log.info("⏹ 午休中收到停止请求,退出")
                    break
                continue
            rounds += 1
            set_current_round(rounds)
            now = datetime.now().strftime("%H:%M:%S")
            print(f"\n{'=' * 60}\n第 {rounds} 轮 · 实时看盘 {now}\n{'=' * 60}")
            emit("round_start", body=f"第 {rounds} 轮 · 实时看盘 {now}")
            try:
                runs.touch(run["id"])   # 长轮次开跑前刷心跳,避免误报僵死
                prompt = load(stage["prompt"], system_id=system_id, user_id=user_id,
                              prompt_version=prompt_version,
                              rounds=rounds, now=now, date=today)
                round_context = _assemble_context(
                    manifest, system_name, stage_name, run["id"], user_id,
                    portfolio_id, execution_mode,
                    {"rounds": rounds, "now": now, "date": today},
                    run_inputs=requested_inputs,
                )
                result = _run_round(
                    agent,
                    inject_stage_context(prompt, round_context),
                    history,
                    limits,
                )
                publish_stage_outputs(stage_name, stage,
                                      {"rounds": rounds, "now": now, "date": today},
                                      result.output)
                history = _trim_rounds(result.all_messages())
                _save_transcript(stage_name, today, rounds, now,
                                 result.all_messages(), result.usage)
                print(result.output)
                if datetime.now().time() >= time(15, 0):
                    log.info("已过 15:00 收盘,收盘确认完成,看盘收工(收盘窗口只跑一轮,不再空转)")
                    break
            except Exception as e:  # 轮级容错:DB/LLM 瞬断不杀进程,重试本轮
                rounds -= 1
                # 事件带异常 message:前端红条只显示类型名(RuntimeError)时无法区分
                # DeepSeek 断连还是 DB 瞬断(8/25 事故复盘结论)
                detail = str(e)[:80]
                emit("round_end", body=f"中断重试: {type(e).__name__}"
                     + (f": {detail}" if detail else ""))
                log.warning(f"第 {rounds + 1} 轮中断({type(e).__name__}: {str(e)[:120]});"
                            f"60 秒后重试本轮,进程不退出")
                if _interruptible_sleep(60, run["id"]):
                    break
                continue
            emit("round_end", body="本轮完成")
            if max_rounds and rounds >= max_rounds:
                log.info(f"(达到 max_rounds={max_rounds},停止)")
                break
            if sleep_seconds > 0:
                if _interruptible_sleep(sleep_seconds, run["id"]):
                    log.info("⏹ 轮间隔中收到停止请求,退出")
                    break
    finally:
        try:
            runs.seal(run["id"], metrics=compute_metrics(
                portfolio_id, today, run_id=run["id"], mode="live"))
            log.info(f"📦 场次已封存:{run_slug}")
        except Exception as e:  # noqa: BLE001 —— 封场失败不崩,场留 running 可接续/强封
            log.warning(f"封场失败({type(e).__name__}),场留在 running——重新运行会接续,或 web 强制封存")


def run_replay(system_name: str, date: str, stage_name: str = "replay",
               interval: int = 5, max_rounds: int | None = None, resume: bool = False,
               tag: str = "", opening: str = "fresh", custom_file: str = "",
               as_of: str = "", user_id: int = 0,
               prompt_version: int | None = None, instruction: str = "") -> None:
    """重演循环:一场一个实验组合(发号登记),开局三模式,源=用户默认组合。"""
    execution_mode = "replay"
    agent, manifest, system_id = build_agent(
        system_name, user_id, stage_name, execution_mode
    )
    stage = manifest["stages"][stage_name]
    log_type = loop_output_type(stage, "watch_replay")
    runs = default_runs()
    interval = interval or stage.get("interval", 5)
    requested_inputs = ({"instruction": instruction.strip()} if instruction.strip() else {})
    if resume:
        cands = runs.list(kind="replay", trade_date=date, user_id=user_id)
        if not cands:
            log.warning(f"{date} 没有可接续的回放场,按全新实验开始")
        run = cands[0]
        requested_inputs = _resume_run_inputs(runs, run, requested_inputs)
        from trader.core.context import set_context as _sc
        if run["status"] != "running":
            runs.set_status(run["id"], "running")   # 停止后再续:复活状态
        runs.set_stage_contract_if_empty(run["id"], stage_contract(stage_name, stage))
        portfolio_id = run.get("portfolio_id") or run["id"]
        _sc(portfolio_id, run["id"], user_id)
        done = _last_round(log_type, date)
        log.info(f"📦 接续场次:{run['slug']}(组合 {portfolio_id},已有 {done} 轮,从第 {done + 1} 轮继续)")
        rounds, hhmm = done, _resume_clock(log_type, date, done)
        fingerprint = run.get("fingerprint") or ""
    else:
        slug = f"{date}-{tag}" if tag else f"{date}-{datetime.now():%H%M%S}"
        portfolio_id = default_portfolios().create(user_id, "experiment", system_id)
        run = runs.create(slug, "replay", date,
                          _prompt_cover(manifest, system_id, user_id, stage_name, prompt_version),
                          system_id=system_id, user_id=user_id, stage=stage_name,
                          clock="simulated", clock_date=date, portfolio_id=portfolio_id,
                          stage_contract=stage_contract(stage_name, stage),
                          run_inputs=requested_inputs)
        custom = _load_custom(custom_file)
        main = default_portfolios().main_of(user_id, system_id)
        if main is None:
            raise RuntimeError(f"用户 {user_id} 在系统 {system_name} 没有主组合")
        fingerprint = open_experiment(portfolio_id, date, opening, custom, as_of,
                                      user_id=user_id,
                                      source_portfolio=main["id"],
                                      run_id=run["id"])
        runs.set_fingerprint(run["id"], fingerprint)
        warn = ("(⚠ fork 现状回放历史日=带未来持仓)" if opening == "fork" else "")
        log.info(f"📦 场次已建:{slug}(实验组合 {portfolio_id},开局 {opening},指纹 {fingerprint}){warn}")
        rounds, hhmm = 0, MORNING_START
    history: list[ModelMessage] = []
    set_current_round(0)
    limits = UsageLimits(request_limit=stage.get("request_limit", 50))
    try:
        set_execution_mode(execution_mode)
        while hhmm <= CLOSE:
            if _stop_requested(run["id"]):
                log.info("⏹ 收到停止请求,完成收尾后退出(重新运行 --resume 可接续)")
                break
            if LUNCH_BREAK[0] < hhmm < LUNCH_BREAK[1]:
                hhmm = LUNCH_BREAK[1]
            rounds += 1
            set_current_round(rounds)
            clock = hhmm.strftime("%H:%M")
            print(f"\n{'=' * 60}\n第 {rounds} 轮 · 模拟看盘 {date} {clock}\n{'=' * 60}")
            emit("round_start", body=f"第 {rounds} 轮 · 模拟看盘 {date} {clock}")
            try:
                runs.touch(run["id"])   # 长轮次开跑前刷心跳,避免误报僵死
                prompt = load(stage["prompt"], system_id=system_id, user_id=user_id,
                              prompt_version=prompt_version,
                              rounds=rounds, date=date, clock=clock)
                round_context = _assemble_context(
                    manifest, system_name, stage_name, run["id"], user_id,
                    portfolio_id, execution_mode,
                    {"rounds": rounds, "date": date, "clock": clock},
                    run_inputs=requested_inputs,
                )
                result = _run_round(
                    agent,
                    inject_stage_context(prompt, round_context),
                    history,
                    limits,
                )
                publish_stage_outputs(stage_name, stage,
                                      {"rounds": rounds, "date": date, "clock": clock},
                                      result.output)
                history = _trim_rounds(result.all_messages())
                _save_transcript(stage_name, date, rounds, clock,
                                 result.all_messages(), result.usage)
                print(result.output)
            except Exception as e:  # 轮级容错:DB/LLM 瞬断不杀进程,重试本轮
                rounds -= 1
                # 同上:事件带异常 message,红条可区分断连/DB 瞬断
                detail = str(e)[:80]
                emit("round_end", body=f"中断重试: {type(e).__name__}"
                     + (f": {detail}" if detail else ""))
                log.warning(f"第 {rounds + 1} 轮中断({type(e).__name__}: {str(e)[:120]});"
                            f"60 秒后重试本轮,进程不退出")
                if _interruptible_sleep(60, run["id"]):
                    break
                continue
            emit("round_end", body="本轮完成")
            if max_rounds and rounds >= max_rounds:
                log.info(f"(达到 max_rounds={max_rounds},停止)")
                break
            minutes = hhmm.hour * 60 + hhmm.minute + interval
            hhmm = time(minutes // 60, minutes % 60)
    finally:
        try:
            runs.seal(run["id"], metrics=compute_metrics(
                portfolio_id, date, run_id=run["id"], mode="replay"))
            log.info(f"📦 场次已封存:{run['slug']}(Web 工作台「场次」可查;replay-rm 删除)")
        except Exception as e:  # noqa: BLE001 —— 封场失败不崩,场留 running 可接续/强封
            log.warning(f"封场失败({type(e).__name__}),场留在 running——重新运行会接续,或 web 强制封存")


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


def _prompt_cover(manifest: dict, system_id: int, user_id: int = 0, stage: str = "",
                  prompt_version: int | None = None) -> dict:
    """封面:本场实际用到的 prompt 版本(系统设定 + 当前阶段;跑过的场不因后续编辑变化)。
    只记用到的——别的系统/别的阶段的 prompt 变动不影响本场封面,对比归因才干净。
    prompt 正本全在 PG(web 编辑器);md 自动同步已随 md 编辑面退役移除。"""
    from trader.core.promptver import default_prompt_versions

    pv = default_prompt_versions()
    sdef = (manifest.get("stages") or {}).get(stage) or {}
    names = [manifest.get("system_prompt"), sdef.get("prompt")]
    out = {}
    for n in filter(None, names):
        rows = pv.versions(system_id, n, user_id=user_id)
        if rows:
            out[n] = rows[0]["version"]
    stage_prompt = sdef.get("prompt")
    if prompt_version is not None and stage_prompt:
        if pv.get(system_id, stage_prompt, prompt_version, user_id=user_id) is None:
            raise ValueError(f"指令 {stage_prompt} v{prompt_version} 不存在")
        out[stage_prompt] = prompt_version
    return out


# ── 封场指标(§8:由流水推算,粒度=成交时点)────────────
# 实现已收拢到 core/valuation.py(估值口径唯一:API 资产页与封场共用);
# 顶部 re-export 维持 engine.compute_metrics 既有调用点与测试入口不变。
