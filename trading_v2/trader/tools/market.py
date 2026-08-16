"""看盘能力:取行情 + 看盘工具。

分层:
- 底层(_ 前缀):纯函数,接收原始参数,不绑 RunContext/Deps,任何场景能复用
- 工具(无 _):AI 调用,RunContext[None] + 参数,通用,任何 agent 能用
- deps 是交易系统阶段才加的"运行环境层",现在不引入
"""
import functools
import json
import os
import subprocess
from datetime import datetime, time as dt_time
from typing import Any

from pydantic_ai import RunContext
from tabulate import tabulate

ASTOCK = os.path.join(os.path.dirname(__file__), "../../../astock/astock")

# 主流指数(replay 固定重建这批,live 也查这批,保持两边一致)
INDICES = ["000001", "399001", "399006", "000688", "399300"]
INDICES_NAME = {
    "000001": "上证指数", "399001": "深证成指",
    "399006": "创业板指", "000688": "科创50", "399300": "沪深300",
}


# ── 底层取数(纯函数,不绑 RunContext,任何场景复用)──────

def _astock(*args: str) -> Any:
    """调 astock 命令(自动加 --json),返回解析后的 JSON。
    astock 输出非 JSON(拒绝/报错,如"盘中专用"命令在盘后调用)时,
    抛 RuntimeError 带上 astock 的原始错误信息(让 AI 看到原因并换方式)。
    """
    result = subprocess.run(
        [ASTOCK, *args, "--json"], capture_output=True, text=True
    )
    out = result.stdout.strip()
    if out.startswith("[") or out.startswith("{"):
        return json.loads(out)
    err = result.stderr.strip() or out or "(无输出)"
    raise RuntimeError(f"astock 失败({args[0] if args else ''}): {err[:200]}")


def _fetch_indices(mode: str, date: str = "", time: str | None = None) -> list[dict]:
    """底层:查主流指数,返回归一化列表。不依赖 Deps/RunContext。
    - live:   astock live index <codes>,输出 {indices:[...]} 含盘口 → 砍盘口、补 name
    - replay: astock replay index <date> [time],输出已是简洁数组 → 过滤对齐 INDICES
    统一成 [{code, name, price, change_pct, amount}, ...]
    """
    fields = lambda it: {
        "code": it["code"],
        "name": it.get("name") or INDICES_NAME.get(it["code"], it["code"]),
        "price": it["price"],
        "pre_close": it.get("pre_close", 0),
        "change_pct": it["change_pct"],
        "amount": it.get("amount", 0),
    }

    if mode == "live":
        raw = _astock("live", "index", *INDICES)
        items = raw["indices"] if isinstance(raw, dict) else raw
        return [fields(it) for it in items]

    # replay(固定重建一批主流指数,可能比 INDICES 多 → 过滤 + 按 INDICES 顺序,与 live 对齐)
    cmd = ["replay", "index", date]
    if time:
        cmd.append(time)
    by_code = {it["code"]: it for it in _astock(*cmd)}
    return [fields(by_code[c]) for c in INDICES if c in by_code]


def _format_indices(data: list[dict]) -> str:
    """指数格式化:已统一到 _format_quotes(全字段表格),保留为别名。"""
    return _format_quotes(data)


def _fetch_quotes(mode: str, codes: list[str], date: str = "", time: str | None = None) -> list[dict]:
    """底层:查多只股票报价。不依赖 Deps/RunContext。
    - live:   astock live quote <code1> <code2> ...        (空格分隔)
    - replay: astock replay quote <逗号分隔codes> <date> [time]
    返回 [{code, name, price, change_pct, amount}, ...]
    """
    fields = lambda it: {
        "code": it["code"],
        "name": it.get("name", ""),
        "price": it["price"],
        "pre_close": it.get("pre_close", 0),
        "change_pct": it["change_pct"],
        "amount": it.get("amount", 0),
    }
    if mode == "live":
        data = _astock("live", "quote", *codes)
        items = data if isinstance(data, list) else []
        return [fields(it) for it in items]
    # replay(逗号分隔 codes)
    cmd = ["replay", "quote", ",".join(codes), date]
    if time:
        cmd.append(time)
    return [fields(it) for it in _astock(*cmd)]


def _fmt_amount(a: float) -> str:
    """成交额(元)格式化:≥1亿显亿,≥1万显万。"""
    if a >= 1e8:
        return f"{a / 1e8:.1f}亿"
    if a >= 1e4:
        return f"{a / 1e4:.0f}万"
    return f"{a:.0f}"


def _format_quotes(data: list[dict]) -> str:
    """多股报价表格:代码/名称/现价/昨收/涨跌/成交额(get_quotes + 成分股共用)。"""
    if not data:
        return "无数据"
    rows = []
    for d in data:
        rows.append([
            d.get("code", ""),
            d.get("name", "") or d.get("code", ""),
            d.get("price", 0),
            d.get("pre_close", 0),
            f"{d.get('change_pct', 0):+.2f}%",
            _fmt_amount(d.get("amount", 0)),
        ])
    return tabulate(rows, headers=["代码", "名称", "现价", "昨收", "涨跌", "成交额"],
                    tablefmt="plain", floatfmt=".2f")


def _fetch_kline(code: str, freq: str = "daily", date: str = "", limit: int = 30,
                 ktype: str = "auto", time: str | None = None) -> list[dict]:
    """底层:查 K 线序列。走 astock query kline(历史库),不依赖 mode/live/replay。
    ktype=auto 时:code 在 INDICES → index,88 开头 → block,否则 stock。
    time:回放时点(如 "10:30")——分钟线只返回到该时刻,防止未来数据泄漏;日线忽略。
    """
    if ktype == "auto":
        if code in INDICES:
            ktype = "index"
        elif code.startswith("88"):  # 板块(通达信 880 前缀)
            ktype = "block"
        else:
            ktype = "stock"
    args = ["query", "kline", code, "--type", ktype, "--freq", freq, "--limit", str(limit)]
    if date:
        args += ["--date", date]
    data = _astock(*args)
    if time and freq != "daily":
        hhmm = time[-5:]  # "10:30"
        data = [k for k in data if str(k.get("time", ""))[-5:] <= hhmm]
    return data


def _format_kline(data: list[dict]) -> str:
    """格式化 K 线为表格(tabulate 自动对齐中文表头)。
    日线含涨跌%(有 pre_close),分钟线只 OHLC。
    """
    if not data:
        return "无数据"
    is_daily = "trade_date" in data[0]
    rows = []
    for k in data:
        o, h, l, c = k["open"], k["high"], k["low"], k["close"]
        if is_daily:
            dt = k["trade_date"][5:]  # 08-12
            pre = k.get("pre_close", 0)
            chg = f"{(c - pre) / pre * 100:+.2f}%" if pre > 0 else ""
            rows.append([dt, o, h, l, c, chg])
        else:
            dt = k.get("time", "")[-5:]  # 14:59
            rows.append([dt, o, h, l, c])
    headers = ["日期", "开", "高", "低", "收", "涨跌"] if is_daily else ["时间", "开", "高", "低", "收"]
    return tabulate(rows, headers=headers, tablefmt="plain", floatfmt=".2f")


def _fetch_block_rank(mode: str, date: str = "", time: str | None = None,
                      block_type: str = "all", limit: int = 20, asc: bool = False) -> list[dict]:
    """底层:板块涨幅排名。live/replay。
    - live:   astock live block rank --type --limit [--asc]
    - replay: astock replay block rank <date> [time] --type --limit [--asc]
    注:replay 时涨跌家数/涨停数为日线终值(分钟级全市场数据量太大)。
    """
    if mode == "live":
        args = ["live", "block", "rank", "--type", block_type, "--limit", str(limit)]
    else:
        args = ["replay", "block", "rank", date]
        if time:
            args.append(time)
        args += ["--type", block_type, "--limit", str(limit)]
    if asc:
        args.append("--asc")
    return _astock(*args)


def _fetch_block_members(mode: str, block_code: str, date: str = "", time: str | None = None,
                         limit: int = 20) -> list[dict]:
    """底层:板块成分股涨幅榜。字段同 quotes(code/name/price/change_pct/amount)。"""
    if mode == "live":
        args = ["live", "block", "members", block_code, "--limit", str(limit)]
    else:
        args = ["replay", "block", "members", block_code, date]
        if time:
            args.append(time)
        args += ["--limit", str(limit)]
    return _astock(*args)


def _format_block_rank(data: list[dict]) -> str:
    """板块排名表格:去掉现价/昨收(板块点位无意义),保留板块强度全信息。
    涨跌/类型/成交额/涨停/涨跌平/中位涨跌。
    """
    if not data:
        return "无数据"
    rows = []
    for b in data:
        rows.append([
            b.get("name", ""),
            b.get("block_type", ""),
            b.get("change_pct", 0),
            _fmt_amount(b.get("amount", 0)),
            b.get("limit_up_count", 0),
            f"{b.get('up_count', 0)}/{b.get('down_count', 0)}/{b.get('flat_count', 0)}",
            f"{b.get('median_change_pct', 0):+.2f}%",
        ])
    return tabulate(rows, headers=["板块", "类型", "涨跌%", "成交额", "涨停", "涨/跌/平", "中位涨跌"],
                    tablefmt="plain", floatfmt="+.2f")


def _fetch_candidates(sort: str = "change", limit: int = 20, state: str = "all",
                      market: str = "all", order: str = "desc") -> list[dict]:
    """底层:全市场个股排序(异动候选)。走 astock live market(实时,无 replay)。"""
    args = ["live", "market", "--sort", sort, "--limit", str(limit),
            "--state", state, "--market", market, "--order", order]
    return _astock(*args).get("rows", [])


def _format_candidates(data: list[dict]) -> str:
    """异动候选表格:代码/名称/涨跌/振幅/涨速/成交额/状态。"""
    if not data:
        return "无数据"
    rows = []
    for c in data:
        rows.append([
            c.get("code", ""),
            c.get("name", ""),
            c.get("change_pct", 0),
            c.get("amplitude_pct", 0),
            c.get("rise_speed", 0),
            _fmt_amount(c.get("amount", 0)),
            c.get("state", ""),
        ])
    return tabulate(rows, headers=["代码", "名称", "涨跌%", "振幅%", "涨速", "成交额", "状态"],
                    tablefmt="plain", floatfmt="+.2f")


def _fetch_limit_up(date: str, time: str | None = None, exclude_st: bool = True) -> list[dict]:
    """底层:涨停清单(模拟看盘/replay)。replay limit list,分钟级封板状态。
    status: sealed(封住)/broken(炸板)/pending(未封,仅触涨停)。
    """
    args = ["replay", "limit", "list", date]
    if time:
        args.append(time)
    if exclude_st:
        args.append("--exclude-st")
    return _astock(*args)


def _format_limit_up(data: list[dict]) -> str:
    """涨停清单表格:代码/名称/连板/涨跌/封板/首封/成交额/概念。"""
    if not data:
        return "无数据"
    rows = []
    for r in data:
        rows.append([
            r.get("code", ""),
            r.get("name", ""),
            r.get("consecutive_days", 0),
            r.get("change_pct", 0),
            r.get("status", ""),
            r.get("first_seal_time", ""),
            _fmt_amount(r.get("replay_amount", r.get("daily_amount", 0))),
            "/".join(r.get("concepts", [])[:2]),
        ])
    return tabulate(rows, headers=["代码", "名称", "连板", "涨跌%", "封板", "首封", "成交额", "概念"],
                    tablefmt="plain", floatfmt="+.2f")


def _fetch_market_summary(date: str = "") -> dict:
    """底层:市场概览(涨跌家数/涨跌停数/成交额分板,历史收盘)。date 空取最新。"""
    args = ["query", "market"] + ([date] if date else [])
    return _astock(*args)


def _format_market_summary(d: dict) -> str:
    if not d:
        return "无数据"
    body = (f"{d.get('date', '')} 涨{d.get('up_count', 0)}/跌{d.get('down_count', 0)}/平{d.get('flat_count', 0)} "
            f"涨停{d.get('limit_up_count', 0)} 跌停{d.get('limit_down_count', 0)} "
            f"总成交{_fmt_amount(d.get('total_amount', 0))}"
            f"(主板{_fmt_amount(d.get('main_board_amount', 0))} "
            f"创业板{_fmt_amount(d.get('growth_board_amount', 0))} "
            f"科创{_fmt_amount(d.get('star_board_amount', 0))})")
    return "⚠ 该日收盘统计(全天)——回放盘中时点时这是未来数据,勿用于当时决策\n" + body


def _fetch_top_amount(date: str = "", limit: int = 20) -> list[dict]:
    """底层:成交额前 N(date 空=最新交易日)。"""
    args = ["query", "stock", "--sort-by", "amount", "--limit", str(limit)]
    if date:
        args += ["--date", date]
    return _astock(*args)


def _format_top_amount(data: list[dict]) -> str:
    if not data:
        return "无数据"
    rows = [[s["code"], s.get("name", ""), s.get("close", 0),
             f"{s.get('pct', 0):+.2f}%", _fmt_amount(s.get("amount", 0))] for s in data]
    table = tabulate(rows, headers=["代码", "名称", "收盘", "涨跌", "成交额"],
                     tablefmt="plain", floatfmt=".2f")
    return "⚠ 该日收盘统计(全天累计)——回放盘中时点时这是未来数据,勿用于当时决策\n" + table


# ── 工具(AI 调用,通用,RunContext[None] + 参数)─────────

def get_quotes(ctx: RunContext[None], codes: list[str], mode: str = "live", date: str = "", time: str = "") -> str:
    """查多只股票报价。codes 是6位代码列表(如 ["000021", "000636"])。
    mode=live(实时,默认)/replay。replay 时 date 必填(如 20260812),time 可选(如 10:30)。
    """
    return _format_quotes(_fetch_quotes(mode, codes, date, time or None))


def get_indices(ctx: RunContext[None], mode: str = "live", date: str = "", time: str = "") -> str:
    """查主流指数行情(上证/深证/科创50/创业板/沪深300)。
    mode=live(实时,默认)/replay(回放某日)。replay 时 date 必填(如 20260812),
    time 可选(如 10:30,默认当日收盘)。
    """
    return _format_indices(_fetch_indices(mode, date, time or None))


def get_kline(ctx: RunContext[None], code: str, freq: str = "daily", date: str = "",
              limit: int = 30, ktype: str = "auto", time: str = "") -> str:
    """查 K 线序列(看趋势/分时走势)。
    code:6位代码(指数或个股)。freq:daily(日K,默认)/1m/5m/15m/30m/60m。
    ktype:auto(默认,自动判断指数/股票)/index/stock/block。
    date:分钟线指定某日(YYYYMMDD)。日线用 limit 控制根数(默认30)。
    time:回放时点(如 10:30)——**分钟线只返回到该时刻**,防止未来数据泄漏;回放查分钟线路径必传。日线忽略。
    """
    return _format_kline(_fetch_kline(code, freq, date, limit, ktype, time or None))


def get_block_rank(ctx: RunContext[None], mode: str = "live", date: str = "", time: str = "",
                   block_type: str = "all", limit: int = 20, asc: bool = False) -> str:
    """板块涨幅排名(看哪些板块强/弱)。mode=live/replay。
    block_type=concept(概念)/style(风格)/all(默认)。asc=True 看跌幅榜。
    """
    return _format_block_rank(_fetch_block_rank(mode, date, time or None, block_type, limit, asc))


def get_block_members(ctx: RunContext[None], block_code: str, mode: str = "live",
                      date: str = "", time: str = "", limit: int = 20) -> str:
    """板块成分股涨幅榜。block_code 是板块代码(如 880812)。
    mode=live/replay。返回成分股报价(格式同 get_quotes)。
    """
    return _format_quotes(_fetch_block_members(mode, block_code, date, time or None, limit))


def get_candidates(ctx: RunContext[None], sort: str = "change", limit: int = 20, state: str = "all") -> str:
    """全市场异动候选(看哪些股在大涨/放量/加速,可能是新方向)。实时(live market,无 replay)。
    sort=change(涨幅,默认)/amount(成交额)/speed(涨速)/amplitude(振幅)。
    state=all(默认)/limit-up(涨停)/limit-down(跌停)。
    """
    return _format_candidates(_fetch_candidates(sort, limit, state))


def get_limit_up(ctx: RunContext[None], date: str, time: str = "", exclude_st: bool = True) -> str:
    """涨停清单(模拟看盘/回放)。date 必填(如 20260812),time 可选(如 10:30,分钟级封板状态)。
    返回涨停股 + 连板数 + 封板状态(sealed封住/broken炸板/pending未封)+ 首封时间 + 概念。
    实时涨停用 get_candidates(state='limit-up')。
    """
    return _format_limit_up(_fetch_limit_up(date, time or None, exclude_st))


def get_market_summary(ctx: RunContext[None], date: str = "") -> str:
    """查某日市场概览(涨跌家数/涨停跌停数/成交额分板)。date=YYYYMMDD,空=最近交易日。
    盘前查昨日情绪基线用。
    """
    return _format_market_summary(_fetch_market_summary(date))


def get_top_amount(ctx: RunContext[None], date: str = "", limit: int = 20) -> str:
    """查成交额前 N(资金在哪/异动归因)。date=YYYYMMDD,空=最近交易日。"""
    return _format_top_amount(_fetch_top_amount(date, limit))


def is_trading_hours() -> bool:
    """A 股交易时段(粗略:周一~五 09:15-15:05,不含节假日)。"""
    now = datetime.now()
    return now.weekday() < 5 and dt_time(9, 15) <= now.time() <= dt_time(15, 5)


def _tool_error_text(func):
    """工具包装:astock 失败(如盘后调 live 命令被拒)时返回错误文本,
    让 AI 看到原因并换方式(如改 replay),而不是崩掉整个 run。"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except RuntimeError as e:
            return f"工具执行失败:{e}"
    return wrapper


for _n in ("get_quotes", "get_indices", "get_kline", "get_block_rank",
           "get_block_members", "get_candidates", "get_limit_up",
           "get_market_summary", "get_top_amount"):
    globals()[_n] = _tool_error_text(globals()[_n])


def get_heartbeat(ctx: RunContext[None]) -> str:
    """看盘快照:指数 + 持仓价 + 池健康度 X/Y。每轮首先调用。"""
    # TODO 积木3
    pass


def probe_pool(ctx: RunContext[None], pool_key: str) -> str:
    """深析:查某主题池全部成员明细(谁领涨/谁掉队/成交额)。"""
    # TODO 积木4
    pass


def probe_stock(ctx: RunContext[None], code: str) -> str:
    """深析:查某只股票的详细数据(开高低现/反弹/回撤)。"""
    # TODO 积木4
    pass
