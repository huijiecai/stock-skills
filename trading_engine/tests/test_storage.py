from datetime import date
from pathlib import Path

import pytest

from trading_engine.errors import StorageError
from trading_engine.models import MarketSnapshot
from trading_engine.replay import SHANGHAI_TZ, replay_timeline
from trading_engine.storage import ReplayStore


def test_checkpoint_and_run_update_are_idempotent(tmp_path: Path) -> None:
    trading_date = date(2026, 7, 23)
    timeline = replay_timeline(trading_date)
    store = ReplayStore(tmp_path / "trader.db")
    run = store.create_run(trading_date, ("603127",), timeline[0])

    updated = store.record_checkpoint(
        run.id,
        timeline[1],
        {"bar_counts": {"603127": 1}},
        "paused",
    )

    assert updated.current_time == timeline[1]
    assert updated.status == "paused"
    assert store.checkpoint_count(run.id) == 2

    with pytest.raises(StorageError, match="checkpoint already exists"):
        store.record_checkpoint(
            run.id,
            timeline[1],
            {"bar_counts": {"603127": 1}},
            "paused",
        )

    assert store.checkpoint_count(run.id) == 2


def test_live_snapshot_round_trips_through_sqlite(tmp_path: Path) -> None:
    store = ReplayStore(tmp_path / "trader.db")
    snapshot = MarketSnapshot(
        as_of=replay_timeline(date(2026, 7, 23))[1].astimezone(SHANGHAI_TZ),
        source="astock-live",
        payload={
            "mode": "shadow",
            "quotes": [{"code": "603127", "price": 49.79}],
        },
    )

    created = store.record_live_snapshot(snapshot)
    loaded = store.latest_live_snapshot()

    assert loaded is not None
    assert loaded.id == created.id
    assert loaded.snapshot == snapshot
