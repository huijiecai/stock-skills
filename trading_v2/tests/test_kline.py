"""get_kline 测试:真实调 astock 查 K 线序列(指数/个股 × 日线/分钟线)。

策略:
- 序列数据走 query(历史库),值固定 → 锁结构 + 部分固定值
- ktype=auto:指数代码自动判 index,个股自动 stock

docstring 统一格式:<场景>:<验证点>
"""
import textwrap

from trader import market

TOOL = "get_kline"


def _show(label: str, out: str):
    """打印工具输出:标签一行,多行表格内容缩进 4 空格对齐。"""
    print("  → " + label + ":")
    print(textwrap.indent(out, "    "))


# ── 底层 _fetch_kline ──────────────────────────────────

def test_fetch_kline_index_daily():
    """指数日线:auto 判 000001 为 index,返回多日 OHLC(含 trade_date)。"""
    data = market._fetch_kline("000001", freq="daily", limit=3)
    _show("astock(上证日线)", market._format_kline(data))
    assert len(data) >= 2
    assert "trade_date" in data[0]
    assert "close" in data[0]


def test_fetch_kline_stock_daily():
    """个股日线:000021 默认 stock,返回多日 OHLC。"""
    data = market._fetch_kline("000021", freq="daily", limit=3)
    _show("astock(深科技日线)", market._format_kline(data))
    assert len(data) >= 2
    assert "trade_date" in data[0]


def test_fetch_kline_stock_minute():
    """个股分钟线:000021 1m 指定日期,返回分钟 OHLC(有 time 无 trade_date)。"""
    data = market._fetch_kline("000021", freq="1m", date="20260812", limit=3)
    _show("astock(深科技 8/12 分钟)", market._format_kline(data))
    assert len(data) >= 1
    assert "time" in data[0]
    assert "trade_date" not in data[0]


def test_fetch_kline_block_daily():
    """板块日线:auto 判 880812 为 block(88 前缀)。"""
    data = market._fetch_kline("880812", freq="daily", limit=2)
    _show("astock(昨日连板板块日线)", market._format_kline(data))
    assert len(data) >= 1
    assert "trade_date" in data[0]


# ── 纯函数 _format_kline(不调 astock)──────────────────

def test_format_kline_daily_pure():
    """_format_kline 日线:假数据 → 中文表头表格(日期/开/高/低/收/涨跌)。"""
    fake = [{"trade_date": "2026-08-12", "open": 40.27, "high": 40.9, "low": 39.75, "close": 40.35, "pre_close": 39.81}]
    out = market._format_kline(fake)
    _show("输出", out)
    assert "08-12" in out
    assert "40.35" in out
    assert "%" in out


def test_format_kline_minute_pure():
    """_format_kline 分钟线:假数据 → 中文表头表格(时间/开/高/低/收,无涨跌)。"""
    fake = [{"time": "08-12 14:59", "open": 40.34, "high": 40.34, "low": 40.34, "close": 40.34}]
    out = market._format_kline(fake)
    _show("输出", out)
    assert "14:59" in out
    assert "40.34" in out


# ── 工具层 get_kline(参数 → 底层 → 格式化)────────────

def test_get_kline_tool_index_daily():
    """get_kline 工具:查上证日线,验证完整链路 + 表头/价格格式。"""
    out = market.get_kline(ctx=None, code="000001", freq="daily", limit=2)
    _show("astock(上证日线)", out)
    assert "日期" in out and "开" in out
    assert "." in out
