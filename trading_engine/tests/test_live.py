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
