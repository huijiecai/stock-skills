from datetime import date, time
from pathlib import Path

import pytest

from trading_engine.errors import ReplayError
from trading_engine.store.models import MarketSnapshot
from trading_engine.market.replay import (
    ReplayClock,
    ReplayEngine,
    ReplayMarketData,
    replay_timeline,
)
from trading_engine.store.storage import ReplayStore


TRADING_DATE = date(2026, 7, 23)


class FakeAstockClient:
    def run_json(self, *arguments: str):
        frequency = arguments[arguments.index("--freq") + 1]
        if frequency == "daily":
            return [{"pre_close": 48.06}]
        return [
            {
                "time": timestamp.strftime("%m-%d %H:%M"),
                "open": 48.0,
                "high": 49.0,
                "low": 47.5,
                "close": 48.5,
                "volume": 100,
                "amount": 4850.0,
            }
            for timestamp in replay_timeline(TRADING_DATE)[1:]
        ]


class FakeMarketData:
    def __init__(self, codes: tuple[str, ...]) -> None:
        self.codes = codes

    def snapshot(self, at):
        return MarketSnapshot(
            as_of=at,
            source="fake",
            payload={
                "instruments": {
                    code: {
                        "pre_close": 10.0,
                        "bars": [{"time": at.isoformat()}],
                    }
                    for code in self.codes
                }
            },
        )


def test_replay_clock_skips_lunch_break() -> None:
    timeline = replay_timeline(TRADING_DATE)
    clock = ReplayClock(TRADING_DATE, timeline[120])

    assert clock.now().strftime("%H:%M") == "11:30"
    assert clock.advance().strftime("%H:%M") == "13:01"
    assert len(timeline) == 241


def test_replay_clock_rejects_non_trading_checkpoint() -> None:
    invalid = replay_timeline(TRADING_DATE)[0].replace(hour=12, minute=0)

    with pytest.raises(ReplayError, match="invalid replay checkpoint"):
        ReplayClock(TRADING_DATE, invalid)


def test_market_snapshot_never_exposes_future_bars() -> None:
    provider = ReplayMarketData(
        FakeAstockClient(),  # type: ignore[arg-type]
        TRADING_DATE,
        ("603127",),
    )
    at = replay_timeline(TRADING_DATE)[60]

    snapshot = provider.snapshot(at)
    bars = snapshot.payload["instruments"]["603127"]["bars"]

    assert at.strftime("%H:%M") == "10:30"
    assert len(bars) == 60
    assert max(bar["time"] for bar in bars) == at.isoformat()


def test_engine_resumes_from_next_minute_without_duplicate_checkpoint(
    tmp_path: Path,
) -> None:
    store = ReplayStore(tmp_path / "trader.db")
    engine = ReplayEngine(
        store,
        lambda _date, codes: FakeMarketData(codes),
    )

    paused = engine.start(TRADING_DATE, ("603127",), time(9, 32))
    resumed = engine.resume(time(9, 33))

    assert paused.status == "paused"
    assert paused.current_time.strftime("%H:%M") == "09:32"
    assert resumed.status == "paused"
    assert resumed.current_time.strftime("%H:%M") == "09:33"
    assert store.checkpoint_count(resumed.id) == 4
