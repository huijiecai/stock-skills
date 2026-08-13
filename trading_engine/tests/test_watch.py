"""Tests for the watch command group (open / heartbeat / probe rendering)."""

from __future__ import annotations

from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from trading_engine.market.context_models import ContextQuote, PricePathContext
from trading_engine.store.storage import ReplayStore
from trading_engine.engine.watch import (
    WEAK_POOL_FRACTION,
    _heartbeat_signals,
    _render_heartbeat_index,
    _render_heartbeat_limits,
    format_open,
    format_probe_code,
    format_probe_pool,
)

SHANGHAI = ZoneInfo("Asia/Shanghai")
AS_OF = datetime(2026, 7, 28, 10, 30, tzinfo=SHANGHAI)


def _path() -> PricePathContext:
    return PricePathContext(
        source="minute_bars", bar_count=10,
        dipped_below_pre_close=False, recovered_above_pre_close=True,
        limit_up_like=False, one_word_limit_like=False,
    )


def _quote(code: str, name: str, price: float, pre_close: float) -> ContextQuote:
    from trading_engine.market.context import _empty_path  # reuse the builder's empty path
    return ContextQuote(
        code=code, name=name, observed_at=AS_OF,
        price=Decimal(str(price)), pre_close=Decimal(str(pre_close)),
        change_pct=Decimal(str(round((price - pre_close) / pre_close * 100, 4))),
        volume=1000, amount=Decimal("100000000"),
        open=Decimal(str(pre_close)), high=Decimal(str(max(price, pre_close))),
        low=Decimal(str(min(price, pre_close))),
        path=_path(),
    )


def _seed_store(tmp_path: Path) -> ReplayStore:
    """Build a store with one account, one position+thesis+risk, one pool."""
    database = tmp_path / "trader.db"
    store = ReplayStore(database)
    store.create_account("paper", Decimal("100000"), Decimal("50000"))
    store.upsert_position(
        "paper", "603127", "昭衍新药", 300, 300, Decimal("50.00"),
        AS_OF.date() - timedelta(days=1),
    )
    store.upsert_thesis(
        key="innovation_medicine", title="创新药", status="active",
        summary="CRO景气", realization_condition="兑现期",
        invalidation_condition="被否定",
    )
    store.link_position_thesis("paper", "603127", "innovation_medicine")
    store.upsert_risk_factor("innovation_risk", "创新药主题风险", Decimal("30"))
    store.link_position_risk_factor("paper", "603127", "innovation_risk")
    store.upsert_watch_pool(
        "pool_innovation", "创新药池", thesis_key="innovation_medicine",
        monitoring_status="active",
    )
    for code in ["603127", "002821"]:
        store.set_watch_pool_member(
            "pool_innovation", code, role="direct",
            tradable=True, relationship="direct",
        )
    return store


# ---------- format_open ----------

def test_format_open_includes_position_thesis_and_risk(tmp_path):
    store = _seed_store(tmp_path)
    text = format_open(store, "paper")
    assert "看盘会话上下文" in text
    assert "603127 昭衍新药 300股" in text
    assert "[预期:创新药]" in text
    assert "[风险:创新药主题风险]" in text
    # rules section present
    assert "§4.1双出口" in text
    assert "T+1" in text


def test_format_open_lists_pool_without_thesis_fallback(tmp_path):
    store = _seed_store(tmp_path)
    text = format_open(store, "paper")
    # pool line shows key + name + member count, no stale "[?:?]" from None thesis
    assert "pool_innovation 创新药池" in text
    assert "成员2" in text
    assert "[?]" not in text


# ---------- heartbeat index / limits rendering ----------

def test_render_heartbeat_index_formats_core_four():
    discovery = {
        "indices": [
            {"name": "上证指数", "change_pct": -0.19},
            {"name": "深证成指", "change_pct": 0.56},
            {"name": "科创50", "change_pct": -0.11},
            {"name": "创业板指", "change_pct": 0.97},
        ],
        "breadth": {"limit_up_count": 6, "total_amount": 48_000_000_000},
    }
    lines: list[str] = []
    _render_heartbeat_index(lines, discovery)
    joined = "\n".join(lines)
    assert "上证-0.19%" in joined
    assert "深证+0.56%" in joined
    assert "涨停6只" in joined
    assert "成交480亿" in joined


def test_render_heartbeat_limits_orders_mainboard_first():
    discovery = {
        "limit_up_detail": [
            {"code": "300408", "name": "三环集团", "change_pct": 10.0,
             "concepts": ["MLCC"], "consecutive_days": 1},
            {"code": "002281", "name": "光迅科技", "change_pct": 10.0,
             "concepts": ["6G概念", "光通信"], "consecutive_days": 2},
            {"code": "603986", "name": "兆易创新", "change_pct": 10.0,
             "concepts": ["存储芯片"], "consecutive_days": 1},
        ]
    }
    lines: list[str] = []
    _render_heartbeat_limits(lines, discovery)
    out = "\n".join(lines)
    # mainboard 002281 and 603986 should appear before 300408 (growth board)
    assert out.index("002281") < out.index("300408")
    assert out.index("603986") < out.index("300408")
    # consecutive-days tag rendered
    assert "2连板" in out
    assert "首板" in out


def test_render_heartbeat_limits_empty_when_no_data():
    lines: list[str] = []
    _render_heartbeat_limits(lines, {})
    assert lines == []


# ---------- heartbeat signal detection ----------

def test_heartbeat_signals_flags_position_crossing_eval_line(tmp_path):
    store = _seed_store(tmp_path)
    pools = [p for p in store.list_watch_pools() if p.key != "current_holdings"]
    quotes = {
        "603127": _quote("603127", "昭衍新药", 46.0, 50.0),   # -8%
        "002821": _quote("002821", "凯莱英", 100.0, 100.0),   # flat
    }
    positions = store.list_positions("paper")
    signals = _heartbeat_signals(positions, quotes, pools, store, "paper")
    # 603127 -8% crosses the ±2% line
    assert any("昭衍新药" in s and "-8.00%" in s for s in signals)


def test_heartbeat_signals_flags_weak_pool(tmp_path):
    store = _seed_store(tmp_path)
    pools = [p for p in store.list_watch_pools() if p.key != "current_holdings"]
    # both pool members down -> 0/2 up, weak
    quotes = {
        "603127": _quote("603127", "昭衍新药", 46.0, 50.0),
        "002821": _quote("002821", "凯莱英", 98.0, 100.0),
    }
    positions = store.list_positions("paper")
    signals = _heartbeat_signals(positions, quotes, pools, store, "paper")
    assert any("创新药池" in s and "连续走弱" in s for s in signals)


def test_heartbeat_signals_empty_when_all_calm(tmp_path):
    store = _seed_store(tmp_path)
    pools = [p for p in store.list_watch_pools() if p.key != "current_holdings"]
    quotes = {
        "603127": _quote("603127", "昭衍新药", 50.5, 50.0),
        "002821": _quote("002821", "凯莱英", 101.0, 100.0),
    }
    positions = store.list_positions("paper")
    signals = _heartbeat_signals(positions, quotes, pools, store, "paper")
    assert signals == []


# ---------- probe rendering ----------

def test_format_probe_pool_sorts_by_change_desc(tmp_path):
    store = _seed_store(tmp_path)
    quotes = {
        "603127": _quote("603127", "昭衍新药", 52.0, 50.0),   # +4%
        "002821": _quote("002821", "凯莱英", 98.0, 100.0),    # -2%
    }
    text = format_probe_pool(store, "pool_innovation", quotes)
    # header shows X/Y
    assert "1涨1跌" in text
    # stronger stock first
    assert text.index("昭衍新药") < text.index("凯莱英")
    assert "+4.00%" in text
    assert "-2.00%" in text


def test_format_probe_pool_unknown_key(tmp_path):
    store = _seed_store(tmp_path)
    text = format_probe_pool(store, "no_such_pool", {})
    assert "not found" in text


def test_format_probe_code_renders_path_context():
    quote = ContextQuote(
        code="000636", name="风华高科", observed_at=AS_OF,
        price=Decimal("57.73"), pre_close=Decimal("58.28"),
        change_pct=Decimal("-0.94"), volume=1000, amount=Decimal("1.01e9"),
        open=Decimal("57.18"), high=Decimal("58.20"), low=Decimal("56.70"),
        path=PricePathContext(
            source="minute_bars", bar_count=10,
            rebound_from_low_pct=Decimal("1.82"),
            drawdown_from_high_pct=Decimal("-0.81"),
            dipped_below_pre_close=True, recovered_above_pre_close=False,
            limit_up_like=False, one_word_limit_like=False,
        ),
    )
    text = format_probe_code("000636", quote)
    assert "000636 风华高科" in text
    assert "-0.94%" in text
    assert "破前收" in text
    assert "反弹+1.82%" in text
