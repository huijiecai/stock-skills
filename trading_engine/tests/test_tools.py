"""Unit tests for trader tool functions."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from trading_engine.errors import LiveDataError, StorageError
from trading_engine.live import MARKET_INDICES
from trading_engine.paper_store import PaperStore
from trading_engine.storage import ReplayStore
from trading_engine.tools import (
    BriefGenerator,
    MarketDataTools,
)


# ---------------------------------------------------------------------------
# FakeAstockClient — mock for astock CLI
# ---------------------------------------------------------------------------

def _quote(code: str, price: float = 42.28, pre_close: float = 41.99) -> dict:
    return {
        "code": code,
        "price": price,
        "pre_close": pre_close,
        "change_pct": (price - pre_close) / pre_close * 100,
        "volume": 1_570_365,
        "amount": 6_546_608_640,
        "open": 41.16,
        "high": 43.10,
        "low": 38.95,
    }


class FakeAstockClient:
    """Mock astock client that routes commands to canned responses."""

    def __init__(
        self,
        index_rows: list | None = None,
        block_rows: list | None = None,
        quote_rows: list | None = None,
        member_rows: list | None = None,
        market_data: dict | None = None,
        limit_rows: list | None = None,
        ladder_rows: list | None = None,
    ) -> None:
        self.index_rows = index_rows
        self.block_rows = block_rows
        self.quote_rows = quote_rows
        self.member_rows = member_rows
        self.market_data = market_data
        self.limit_rows = limit_rows
        self.ladder_rows = ladder_rows

    def run_json(self, *arguments: str):
        if arguments[:2] == ("live", "index"):
            if self.index_rows is None:
                raise AssertionError("unexpected index call")
            return self.index_rows
        if arguments[:3] == ("live", "block", "rank"):
            if self.block_rows is None:
                raise AssertionError("unexpected block rank call")
            return self.block_rows
        if arguments[:3] == ("live", "block", "members"):
            if self.member_rows is None:
                raise AssertionError("unexpected live block members call")
            return self.member_rows
        if arguments[:2] == ("live", "quote"):
            if self.quote_rows is None:
                raise AssertionError("unexpected quote call")
            return self.quote_rows
        if arguments[:3] == ("query", "block", "members"):
            if self.member_rows is None:
                raise AssertionError("unexpected members call")
            return self.member_rows
        if arguments[:3] == ("query", "limit", "ladder"):
            if self.ladder_rows is None:
                raise AssertionError("unexpected ladder call")
            return self.ladder_rows
        if arguments[:2] == ("query", "limit"):
            if self.limit_rows is None:
                raise AssertionError("unexpected limit call")
            return self.limit_rows
        if arguments[:2] == ("live", "market"):
            if self.market_data is None:
                raise AssertionError("unexpected market call")
            return self.market_data
        raise AssertionError(f"unexpected call: {arguments}")


def _index_rows():
    return [
        {
            "code": code,
            "price": 1000 + i,
            "pre_close": 990 + i,
            "change_pct": 1.01,
            "volume": 1_000_000,
            "amount": 10_000_000_000,
            "open": 995,
            "high": 1010,
            "low": 985,
        }
        for i, code in enumerate(MARKET_INDICES)
    ]


def _market_data():
    candidate = {
        "code": "000636",
        "name": "风华高科",
        "industry": "电子元件",
        "price": 44.24,
        "pre_close": 40.22,
        "change_pct": 10.0,
        "amount": 6_500_000_000,
        "low": 40.01,
        "limit_up": True,
    }
    return {
        "coverage_mode": "all_main_board_snapshot",
        "universe": 3200,
        "scanned": 3195,
        "missing_quotes": 5,
        "failed_batches": 1,
        "top_amount": [candidate],
        "candidates": [candidate],
    }


# ---------------------------------------------------------------------------
# MarketDataTools tests
# ---------------------------------------------------------------------------

def test_fetch_index_returns_all_indices_with_names() -> None:
    tools = MarketDataTools(FakeAstockClient(index_rows=_index_rows()))  # type: ignore[arg-type]
    result = tools.fetch_index()
    assert len(result) == len(MARKET_INDICES)
    names = {row["name"] for row in result}
    assert names == set(MARKET_INDICES.values())
    codes = {row["code"] for row in result}
    assert codes == set(MARKET_INDICES)


def test_fetch_index_rejects_incomplete_set() -> None:
    rows = _index_rows()[:3]  # only 3 of 6
    tools = MarketDataTools(FakeAstockClient(index_rows=rows))  # type: ignore[arg-type]
    with pytest.raises(LiveDataError, match="missing"):
        tools.fetch_index()


def test_fetch_block_rank_passes_limit() -> None:
    block_rows = [
        {
            "code": "880958",
            "name": "AI营销",
            "block_type": "concept",
            "price": 763.03,
            "pre_close": 702.23,
            "change_pct": 8.66,
            "amount": 45_035_692_032,
            "limit_up_count": 13,
        }
    ]
    tools = MarketDataTools(FakeAstockClient(block_rows=block_rows))  # type: ignore[arg-type]
    result = tools.fetch_block_rank(limit=10)
    assert len(result) == 1
    assert result[0]["name"] == "AI营销"
    assert result[0]["code"] == "880958"


def test_fetch_stock_quote_validates_and_returns_quotes() -> None:
    quote_rows = [_quote("000021", 37.23, 36.42), _quote("603127", 41.54, 40.05)]
    tools = MarketDataTools(FakeAstockClient(quote_rows=quote_rows))  # type: ignore[arg-type]
    result = tools.fetch_stock_quote(("000021", "603127"))
    assert len(result) == 2
    assert result[0]["code"] == "000021"
    assert result[1]["code"] == "603127"


def test_fetch_stock_quote_rejects_code_mismatch() -> None:
    quote_rows = [_quote("600839")]
    tools = MarketDataTools(FakeAstockClient(quote_rows=quote_rows))  # type: ignore[arg-type]
    with pytest.raises(LiveDataError, match="code mismatch"):
        tools.fetch_stock_quote(("000636",))


def test_fetch_stock_quote_rejects_empty_codes() -> None:
    tools = MarketDataTools(FakeAstockClient())  # type: ignore[arg-type]
    with pytest.raises(LiveDataError, match="at least one"):
        tools.fetch_stock_quote(())


def test_fetch_stock_quote_rejects_change_pct_mismatch() -> None:
    bad_quote = _quote("000021", 37.23, 36.42)
    bad_quote["change_pct"] = 99.0  # wrong value
    tools = MarketDataTools(FakeAstockClient(quote_rows=[bad_quote]))  # type: ignore[arg-type]
    with pytest.raises(LiveDataError, match="change_pct does not match"):
        tools.fetch_stock_quote(("000021",))


def test_fetch_block_members_returns_list() -> None:
    member_rows = [
        {"code": "300290", "name": "ST荣科", "close": 4.88, "change_pct": 19.9},
        {"code": "002212", "name": "天融信", "close": 6.0, "change_pct": 10.09},
    ]
    tools = MarketDataTools(FakeAstockClient(member_rows=member_rows))  # type: ignore[arg-type]
    result = tools.fetch_block_members("880904")
    assert len(result) == 2
    assert result[0]["code"] == "300290"


def _limit_rows():
    return [
        {
            "code": "000533",
            "name": "顺纳股份",
            "board": "main",
            "pct_limit": 0.1,
            "close": 11.56,
            "limit_price": 11.56,
            "change_pct": 9.99,
            "amount": 2148432128,
            "consecutive_days": 4,
            "concepts": ["临界发电", "可控核变", "百度概念"],
        },
        {
            "code": "002195",
            "name": "岩山科技",
            "board": "main",
            "pct_limit": 0.1,
            "close": 6.83,
            "limit_price": 6.83,
            "change_pct": 9.98,
            "amount": 1570675584,
            "consecutive_days": 1,
            "concepts": ["云游戏", "AI手机PC", "短剧游戏"],
        },
    ]


def test_fetch_limit_list_returns_complete_list() -> None:
    tools = MarketDataTools(FakeAstockClient(limit_rows=_limit_rows()))  # type: ignore[arg-type]
    result = tools.fetch_limit_list()
    assert len(result) == 2
    assert result[0]["code"] == "000533"
    assert result[0]["consecutive_days"] == 4
    assert "临界发电" in result[0]["concepts"]


def test_fetch_limit_list_passes_side_and_exclude_st() -> None:
    """Verify --side and --exclude-st are passed to astock."""
    captured: list[tuple] = []

    class CapturingClient:
        def run_json(self, *arguments: str):
            captured.append(arguments)
            return _limit_rows()

    tools = MarketDataTools(CapturingClient())  # type: ignore[arg-type]
    tools.fetch_limit_list(side="down", exclude_st=True)
    assert "--side" in captured[0]
    assert "down" in captured[0]
    assert "--exclude-st" in captured[0]


def test_fetch_limit_list_accepts_date() -> None:
    captured: list[tuple] = []

    class CapturingClient:
        def run_json(self, *arguments: str):
            captured.append(arguments)
            return _limit_rows()

    tools = MarketDataTools(CapturingClient())  # type: ignore[arg-type]
    tools.fetch_limit_list(date="20260731")
    assert "20260731" in captured[0]


def test_fetch_limit_list_returns_empty() -> None:
    tools = MarketDataTools(FakeAstockClient(limit_rows=[]))  # type: ignore[arg-type]
    result = tools.fetch_limit_list()
    assert result == []


def test_fetch_limit_ladder_returns_sorted_by_consecutive() -> None:
    ladder_rows = [
        {
            "code": "603221",
            "name": "爱丽家居",
            "consecutive_days": 5,
            "close": 16.94,
        },
        {
            "code": "000533",
            "name": "顺纳股份",
            "consecutive_days": 4,
            "concepts": ["临界发电"],
        },
    ]
    tools = MarketDataTools(FakeAstockClient(ladder_rows=ladder_rows))  # type: ignore[arg-type]
    result = tools.fetch_limit_ladder()
    assert len(result) == 2
    assert result[0]["consecutive_days"] == 5


def test_fetch_market_scan_returns_full_structure() -> None:
    market = _market_data()
    tools = MarketDataTools(FakeAstockClient(market_data=market))  # type: ignore[arg-type]
    result = tools.fetch_market_scan()
    assert result["coverage_mode"] == "full_market"
    assert result["universe_count"] == 3200
    assert result["scanned_count"] == 3195
    assert "000636" in result["limit_up_codes"]
    assert len(result["candidates"]) == 1
    assert len(result["top_amount"]) == 1


# ---------------------------------------------------------------------------
# BriefGenerator tests
# ---------------------------------------------------------------------------

def _seed_brief_database(tmp_path: Path) -> ReplayStore:
    store = ReplayStore(tmp_path / "trader.db")
    store.create_account("paper", Decimal("100000"), Decimal("20229.40"))
    store.upsert_position(
        "paper", "603127", "昭衍新药", 300, 300,
        Decimal("55.68"), date(2026, 7, 16),
    )
    store.upsert_thesis(
        key="innovation_medicine",
        title="创新药",
        status="active",
        summary="创新药周期",
        realization_condition="管线获批",
        invalidation_condition="管线失败",
    )
    store.upsert_thesis(
        key="archived_thesis",
        title="已归档",
        status="archived",
        summary="旧方向",
        realization_condition="x",
        invalidation_condition="y",
    )
    store.upsert_watch_pool(
        key="innovation_pool",
        name="创新药池",
        thesis_key="innovation_medicine",
        monitoring_status="active",
    )
    store.upsert_risk_factor(
        key="innovation_risk",
        name="创新药风险",
        max_exposure_pct=Decimal("30"),
    )
    return store


def test_brief_contains_account_and_positions(tmp_path: Path) -> None:
    store = _seed_brief_database(tmp_path)
    paper_store = PaperStore(tmp_path / "trader.db")
    brief = BriefGenerator(store, paper_store).generate("paper")

    assert brief["account"]["name"] == "paper"
    assert brief["account"]["cash"] == "20229.4"
    assert brief["account"]["cooldown"] is False

    positions = brief["positions"]
    assert len(positions) == 1
    assert positions[0]["code"] == "603127"
    assert positions[0]["quantity"] == 300


def test_brief_filters_active_theses(tmp_path: Path) -> None:
    store = _seed_brief_database(tmp_path)
    paper_store = PaperStore(tmp_path / "trader.db")
    brief = BriefGenerator(store, paper_store).generate("paper")

    theses = brief["active_theses"]
    assert len(theses) == 1
    assert theses[0]["key"] == "innovation_medicine"
    assert theses[0]["status"] == "active"


def test_brief_includes_pools_and_plans(tmp_path: Path) -> None:
    store = _seed_brief_database(tmp_path)
    paper_store = PaperStore(tmp_path / "trader.db")

    store.upsert_trade_plan(
        key="test_plan",
        trading_date=date.today(),
        thesis_key="innovation_medicine",
        action="BUY",
        target_code="603127",
        target_name="昭衍新药",
        quantity=100,
        priority=1,
        trigger_conditions=("三维齐",),
        ranking_notes="优先级1",
        rationale="测试",
        buy_point_type="confirmation",
    )

    brief = BriefGenerator(store, paper_store).generate("paper")
    pools = brief["active_pools"]
    assert len(pools) == 1
    assert pools[0]["key"] == "innovation_pool"

    plans = brief["today_plans"]
    assert len(plans) == 1
    assert plans[0]["action"] == "BUY"
    assert plans[0]["target_code"] == "603127"


def test_brief_market_phase_is_valid(tmp_path: Path) -> None:
    store = _seed_brief_database(tmp_path)
    paper_store = PaperStore(tmp_path / "trader.db")
    brief = BriefGenerator(store, paper_store).generate("paper")

    assert brief["market_phase"] in {
        "pre_market", "intraday_morning", "midday_break",
        "intraday_afternoon", "post_close",
    }


def test_brief_handles_nonexistent_account(tmp_path: Path) -> None:
    store = ReplayStore(tmp_path / "trader.db")
    paper_store = PaperStore(tmp_path / "trader.db")
    brief = BriefGenerator(store, paper_store).generate("nonexistent")

    assert brief["account"]["error"] == "account does not exist"
    assert brief["positions"] == []
    assert brief["active_theses"] == []
    assert brief["recent_trades"] == []


def test_brief_recent_trades_empty_when_no_paper_history(tmp_path: Path) -> None:
    store = _seed_brief_database(tmp_path)
    paper_store = PaperStore(tmp_path / "trader.db")
    brief = BriefGenerator(store, paper_store).generate("paper")

    assert brief["recent_trades"] == []


# ---------------------------------------------------------------------------
# Replay mode tests
# ---------------------------------------------------------------------------

class ReplayAstockClient:
    """Mock astock client for replay-mode queries (replay + query commands)."""

    def __init__(
        self,
        index_rows: list | None = None,
        block_rows: list | None = None,
        quote_rows: list | None = None,
        market_data: dict | None = None,
        top_amount_rows: list | None = None,
        top_pct_rows: list | None = None,
        limit_rows: list | None = None,
        ladder_rows: list | None = None,
        member_rows: list | None = None,
    ) -> None:
        self.index_rows = index_rows
        self.block_rows = block_rows
        self.quote_rows = quote_rows
        self.market_data = market_data
        self.top_amount_rows = top_amount_rows
        self.top_pct_rows = top_pct_rows
        self.limit_rows = limit_rows
        self.ladder_rows = ladder_rows
        self.member_rows = member_rows

    def run_json(self, *arguments: str):
        # replay index <date> [time]
        if arguments[:2] == ("replay", "index"):
            if self.index_rows is None:
                raise AssertionError("unexpected replay index call")
            return self.index_rows
        # replay block rank <date> [time] --limit N
        if arguments[:3] == ("replay", "block", "rank"):
            if self.block_rows is None:
                raise AssertionError("unexpected replay block rank call")
            return self.block_rows
        # replay quote <codes> <date> [time]
        if arguments[:2] == ("replay", "quote"):
            if self.quote_rows is None:
                raise AssertionError("unexpected replay quote call")
            return self.quote_rows
        # replay market <date> [time]
        if arguments[:2] == ("replay", "market"):
            if self.market_data is None:
                raise AssertionError("unexpected replay market call")
            return self.market_data
        # replay limit list <date> [time]
        if arguments[:3] == ("replay", "limit", "list"):
            if self.limit_rows is None:
                raise AssertionError("unexpected replay limit list call")
            return self.limit_rows
        # replay limit ladder <date> [time]
        if arguments[:3] == ("replay", "limit", "ladder"):
            if self.ladder_rows is None:
                raise AssertionError("unexpected replay limit ladder call")
            return self.ladder_rows
        # replay block members CODE DATE [time]
        if arguments[:3] == ("replay", "block", "members"):
            if self.member_rows is None:
                raise AssertionError("unexpected replay block members call")
            return self.member_rows
        # query block members CODE [date]
        if arguments[:3] == ("query", "block", "members"):
            if self.member_rows is None:
                raise AssertionError("unexpected query block members call")
            return self.member_rows
        # query stock --sort-by amount/pct --date YYYYMMDD --limit N
        if arguments[:2] == ("query", "stock"):
            if "--sort-by" in arguments:
                idx = arguments.index("--sort-by")
                sort_key = arguments[idx + 1]
                if sort_key == "amount":
                    if self.top_amount_rows is None:
                        raise AssertionError("unexpected top amount call")
                    return self.top_amount_rows
                if sort_key == "pct":
                    if self.top_pct_rows is None:
                        raise AssertionError("unexpected top pct call")
                    return self.top_pct_rows
            raise AssertionError(f"unexpected query stock: {arguments}")
        # query limit ladder [date] (no replay_time mode)
        if arguments[:3] == ("query", "limit", "ladder"):
            if self.ladder_rows is None:
                raise AssertionError("unexpected query ladder call")
            return self.ladder_rows
        # query limit [date] (no replay_time mode)
        if arguments[:2] == ("query", "limit"):
            if self.limit_rows is None:
                raise AssertionError("unexpected query limit call")
            return self.limit_rows
        raise AssertionError(f"unexpected call: {arguments}")


def _replay_index_rows() -> list:
    """Mock replay index output (from astock replay index)."""
    return [
        {"code": code, "name": name, "price": 3850.0, "pre_close": 3800.0,
         "change_pct": 1.32, "amount": 50_000_000_000.0}
        for code, name in MARKET_INDICES.items()
    ]


def _replay_index_at_time() -> list:
    """Mock replay index output at 10:30 (lower price than close)."""
    return [
        {"code": code, "name": name, "price": 3820.0, "pre_close": 3800.0,
         "change_pct": 0.53, "amount": 30_000_000_000.0}
        for code, name in MARKET_INDICES.items()
    ]


def test_replay_fetch_index_uses_replay_command() -> None:
    """Replay mode calls astock replay index <date>."""
    client = ReplayAstockClient(index_rows=_replay_index_rows())
    tools = MarketDataTools(client, replay_date="20260727")  # type: ignore[arg-type]
    result = tools.fetch_index()
    assert len(result) == len(MARKET_INDICES)
    for entry in result:
        assert entry["code"] in MARKET_INDICES
        assert entry["price"] == 3850.0
        assert entry["change_pct"] != 0


def test_replay_fetch_index_with_replay_time() -> None:
    """Replay mode with replay_time calls astock replay index <date> <time>."""
    client = ReplayAstockClient(index_rows=_replay_index_at_time())
    tools = MarketDataTools(
        client, replay_date="20260727", replay_time="10:30"  # type: ignore[arg-type]
    )
    result = tools.fetch_index()
    assert len(result) == len(MARKET_INDICES)
    # At 10:30, price should be lower than close
    assert result[0]["price"] == 3820.0


def test_replay_fetch_block_rank_uses_replay_command() -> None:
    """Replay mode calls astock replay block rank <date> [time] --limit N."""
    block_rows = [{"code": "880958", "name": "AI营销", "change_pct": 8.66, "limit_up_count": 13}]
    client = ReplayAstockClient(block_rows=block_rows)
    tools = MarketDataTools(client, replay_date="20260727")  # type: ignore[arg-type]
    result = tools.fetch_block_rank(limit=10)
    assert len(result) == 1
    assert result[0]["name"] == "AI营销"


def test_replay_fetch_stock_quote_uses_replay_command() -> None:
    """Replay mode calls astock replay quote <codes> <date> [time]."""
    client = ReplayAstockClient(
        quote_rows=[{"code": "000021", "name": "深科技", "price": 36.96,
                     "pre_close": 40.15, "change_pct": -7.95, "amount": 2865995415}],
    )
    tools = MarketDataTools(client, replay_date="20260727", replay_time="10:30")  # type: ignore[arg-type]
    result = tools.fetch_stock_quote(("000021",))
    assert len(result) == 1
    assert result[0]["code"] == "000021"
    assert result[0]["price"] == 36.96
    assert result[0]["pre_close"] == 40.15


def test_replay_fetch_stock_quote_no_time() -> None:
    """Replay mode without replay_time calls astock replay quote <codes> <date>."""
    client = ReplayAstockClient(
        quote_rows=[{"code": "000021", "name": "深科技", "price": 37.23,
                     "pre_close": 40.15, "change_pct": -7.27, "amount": 5000000000}],
    )
    tools = MarketDataTools(client, replay_date="20260727")  # type: ignore[arg-type]
    result = tools.fetch_stock_quote(("000021",))
    assert len(result) == 1
    assert result[0]["price"] == 37.23


def test_replay_fetch_limit_list_no_time_uses_query() -> None:
    """Replay mode without replay_time uses query limit (daily terminal)."""
    limit_rows = _limit_rows()
    client = ReplayAstockClient(limit_rows=limit_rows)
    tools = MarketDataTools(client, replay_date="20260727")  # type: ignore[arg-type]
    result = tools.fetch_limit_list()
    assert len(result) == 2
    assert result[0]["code"] == "000533"


def test_replay_fetch_limit_list_with_time_uses_replay() -> None:
    """Replay mode with replay_time uses replay limit list (minute-level status)."""
    limit_rows = [
        {"code": "000533", "name": "顺纳股份", "status": "sealed",
         "consecutive_days": 4, "replay_price": 11.56, "limit_price": 11.56},
        {"code": "002195", "name": "岩山科技", "status": "broken",
         "consecutive_days": 1, "replay_price": 6.70, "limit_price": 6.83},
    ]
    client = ReplayAstockClient(limit_rows=limit_rows)
    tools = MarketDataTools(client, replay_date="20260727", replay_time="10:30")  # type: ignore[arg-type]
    result = tools.fetch_limit_list()
    assert len(result) == 2
    assert result[0]["code"] == "000533"
    assert result[0]["status"] == "sealed"


def test_replay_fetch_limit_ladder_no_time_uses_query() -> None:
    """Replay mode without replay_time uses query limit ladder (daily terminal)."""
    ladder_rows = [
        {"code": "603221", "name": "爱丽家居", "consecutive_days": 5},
        {"code": "000533", "name": "顺纳股份", "consecutive_days": 4},
    ]
    client = ReplayAstockClient(ladder_rows=ladder_rows)
    tools = MarketDataTools(client, replay_date="20260727")  # type: ignore[arg-type]
    result = tools.fetch_limit_ladder()
    assert len(result) == 2
    assert result[0]["consecutive_days"] == 5


def test_replay_fetch_limit_ladder_with_time_uses_replay() -> None:
    """Replay mode with replay_time uses replay limit ladder (only sealed stocks)."""
    ladder_rows = [
        {"code": "603221", "name": "爱丽家居", "consecutive_days": 5, "status": "sealed"},
        {"code": "000533", "name": "顺纳股份", "consecutive_days": 4, "status": "sealed"},
    ]
    client = ReplayAstockClient(ladder_rows=ladder_rows)
    tools = MarketDataTools(client, replay_date="20260727", replay_time="10:30")  # type: ignore[arg-type]
    result = tools.fetch_limit_ladder()
    assert len(result) == 2
    assert result[0]["consecutive_days"] == 5


def test_replay_fetch_market_scan_returns_daily_overview() -> None:
    """Replay market scan uses replay market + query stock for top stocks."""
    client = ReplayAstockClient(
        market_data={
            "date": "2026-07-27", "total_stocks": 5526, "up_count": 5184,
            "down_count": 290, "flat_count": 52, "limit_up_count": 113,
            "total_amount": 1945693556974.5,
        },
        top_amount_rows=[{"code": "002384", "name": "东山精密", "close": 171.48, "amount": 21468493824}],
        top_pct_rows=[{"code": "000533", "name": "顺纳股份", "close": 11.56, "pct": 9.99}],
        limit_rows=[{"code": "000533", "name": "顺纳股份"}],
    )
    tools = MarketDataTools(client, replay_date="20260727")  # type: ignore[arg-type]
    result = tools.fetch_market_scan()
    assert result["coverage_mode"] == "replay_daily"
    assert result["universe_count"] == 5526
    assert result["limit_up_count"] == 113
    assert len(result["top_amount"]) == 1
    assert result["top_amount"][0]["code"] == "002384"
    assert "000533" in result["limit_up_codes"]


def test_replay_fetch_market_scan_with_time_returns_minute() -> None:
    """Replay market scan with time uses replay market <date> <time>."""
    client = ReplayAstockClient(
        market_data={
            "date": "2026-07-27", "time": "10:30", "total_stocks": 626,
            "up_count": 578, "down_count": 48, "flat_count": 0,
            "limit_up_count": 0, "total_amount": 2292796332000.0,
            "index_price": 3812.53, "index_change_pct": -0.42,
        },
        top_amount_rows=[{"code": "002384", "name": "东山精密", "close": 171.48, "amount": 21468493824}],
        top_pct_rows=[{"code": "000533", "name": "顺纳股份", "close": 11.56, "pct": 9.99}],
        limit_rows=[{"code": "000533", "name": "顺纳股份"}],
    )
    tools = MarketDataTools(client, replay_date="20260727", replay_time="10:30")  # type: ignore[arg-type]
    result = tools.fetch_market_scan()
    assert result["coverage_mode"] == "replay_minute"
    assert result["universe_count"] == 626
    assert result["index_price"] == 3812.53


def test_replay_block_members_no_time_uses_query() -> None:
    """Replay mode without replay_time uses query block members (daily close)."""
    member_rows = [{"code": "300290", "name": "ST荣科", "close": 4.88, "change_pct": 19.9}]
    client = ReplayAstockClient(member_rows=member_rows)
    tools = MarketDataTools(client, replay_date="20260727")  # type: ignore[arg-type]
    result = tools.fetch_block_members("880904")
    assert len(result) == 1
    assert result[0]["code"] == "300290"
    assert result[0]["change_pct"] == 19.9


def test_replay_block_members_with_time_uses_replay() -> None:
    """Replay mode with replay_time uses replay block members (minute-level)."""
    member_rows = [
        {"code": "300290", "name": "ST荣科", "close": 4.50, "change_pct": 10.0,
         "data_source": "minute"},
        {"code": "002212", "name": "天融信", "close": 6.0, "change_pct": 5.0,
         "data_source": "daily"},
    ]
    client = ReplayAstockClient(member_rows=member_rows)
    tools = MarketDataTools(client, replay_date="20260727", replay_time="10:30")  # type: ignore[arg-type]
    result = tools.fetch_block_members("880904")
    assert len(result) == 2
    assert result[0]["code"] == "300290"
    assert result[0]["data_source"] == "minute"
    assert result[1]["data_source"] == "daily"


def test_live_mode_ignores_replay_time() -> None:
    """replay_time without replay_date should not affect live mode."""
    quote_rows = [_quote("000021", 37.23, 36.42)]
    # Use FakeAstockClient for live mode
    client = FakeAstockClient(quote_rows=quote_rows)
    tools = MarketDataTools(client)  # type: ignore[arg-type]
    result = tools.fetch_stock_quote(("000021",))
    assert result[0]["price"] == 37.23
