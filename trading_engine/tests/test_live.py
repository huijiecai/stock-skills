from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from trading_engine.errors import LiveDataError
from trading_engine.live import LiveMarketData


OBSERVED_AT = datetime(2026, 7, 27, 11, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


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
    def __init__(self, rows) -> None:
        self.rows = rows

    def run_json(self, *arguments: str):
        assert arguments[:2] == ("live", "quote")
        return self.rows


class DiscoveryAstockClient:
    def run_json(self, *arguments: str):
        if arguments[:2] == ("live", "quote"):
            return [_quote("000636")]
        if arguments[:2] == ("live", "market"):
            candidate = {
                "code": "000636",
                "name": "风华高科",
                "industry": "电子元件",
                "sector": "MLCC",
                "business": "被动元件",
                "price": 44.24,
                "pre_close": 40.22,
                "change_pct": 10.0,
                "amount": 6_500_000_000,
                "low": 40.01,
                "rebound_pct": 10.52,
                "state": "limit_up",
                "reasons": ["limit_up", "strong_move"],
            }
            return {
                "as_of": "2026-07-27T11:30:00+08:00",
                "returned": 1,
                "rows": [candidate],
            }
        if arguments == ("live", "block", "rank", "--limit", "50"):
            return [
                {
                    "code": "sh880507",
                    "name": "MLCC",
                    "block_type": "concept",
                    "price": 1234.5,
                    "pre_close": 1200,
                    "change_pct": 4.4,
                    "amount": 12_000_000_000,
                    "limit_up_count": 2,
                }
            ]
        if arguments[:2] == ("live", "index"):
            return {
                "fetched_at": "2026-07-27T11:30:00+08:00",
                "source": "tdx",
                "requests": 3,
                "elapsed_ms": 200,
                "indices": [
                    {
                        "code": code,
                        "price": 1000 + index,
                        "pre_close": 990 + index,
                        "change_pct": 1.01,
                        "volume": 1_000_000,
                        "amount": 10_000_000_000,
                        "open": 995,
                        "high": 1010,
                        "low": 985,
                    }
                    for index, code in enumerate(arguments[2:])
                ],
                "breadth": {
                    "as_of": "2026-07-27T11:30:00+08:00",
                    "up_count": 3200,
                    "down_count": 1800,
                    "markets": [
                        {"scope": "sh", "up_count": 1400, "down_count": 900},
                        {"scope": "sz", "up_count": 1800, "down_count": 900},
                    ],
                },
            }
        raise AssertionError(arguments)


def test_live_snapshot_preserves_requested_order_and_validates_quotes() -> None:
    provider = LiveMarketData(
        FakeAstockClient([_quote("000636", 44.24, 40.22), _quote("000021")]),  # type: ignore[arg-type]
        ("000021", "000636"),
    )

    snapshot = provider.snapshot(OBSERVED_AT)

    assert snapshot.source == "astock-live"
    assert snapshot.payload["mode"] == "shadow"
    assert [row["code"] for row in snapshot.payload["quotes"]] == [
        "000021",
        "000636",
    ]


def test_live_snapshot_rejects_code_mismatch() -> None:
    provider = LiveMarketData(
        FakeAstockClient([_quote("600839")]),  # type: ignore[arg-type]
        ("000636",),
    )

    with pytest.raises(LiveDataError, match="code mismatch"):
        provider.snapshot(OBSERVED_AT)


def test_live_snapshot_rejects_zero_price() -> None:
    provider = LiveMarketData(
        FakeAstockClient([_quote("000636", 0, 40.22)]),  # type: ignore[arg-type]
        ("000636",),
    )

    with pytest.raises(LiveDataError, match="invalid live quote"):
        provider.snapshot(OBSERVED_AT)


def test_live_snapshot_can_capture_full_market_discovery() -> None:
    provider = LiveMarketData(
        DiscoveryAstockClient(),  # type: ignore[arg-type]
        ("000636",),
        include_discovery=True,
    )

    snapshot = provider.snapshot(OBSERVED_AT)

    discovery = snapshot.payload["market_discovery"]
    assert discovery["coverage_mode"] == "candidate_universe"
    assert discovery["universe_count"] == 1
    assert discovery["scanned_count"] == 1
    assert discovery["limit_up_codes"] == ("000636",)
    assert discovery["candidates"][0]["reasons"] == [
        "limit_up",
        "strong_move",
    ]
    assert discovery["sector_leaders"][0]["name"] == "MLCC"
    assert {row["name"] for row in discovery["indices"]} == {
        "上证指数",
        "深证成指",
        "创业板指",
        "上证50",
        "沪深300",
        "中证1000",
    }
    assert discovery["breadth"]["up_count"] == 3200
    assert discovery["breadth"]["down_count"] == 1800
    assert discovery["missing_capabilities"] == []
