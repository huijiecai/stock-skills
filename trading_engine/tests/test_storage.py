from datetime import date
from decimal import Decimal
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


def test_independent_account_and_positions_round_trip(tmp_path: Path) -> None:
    store = ReplayStore(tmp_path / "trader.db")

    account = store.create_account(
        "default", Decimal("100000.00"), Decimal("20229.40")
    )
    position = store.upsert_position(
        "default",
        "603127",
        "昭衍新药",
        300,
        300,
        Decimal("55.68"),
        date(2026, 7, 16),
    )

    assert account.initial_cash == Decimal("100000")
    assert account.cash == Decimal("20229.4")
    assert position.account_id == account.id
    assert position.average_cost == Decimal("55.68")
    assert store.list_positions("default") == (position,)

    account = store.update_account(
        "default", cash=Decimal("20000.00"), cooldown=True
    )
    assert account.cash == Decimal("20000")
    assert account.cooldown is True

    updated = store.upsert_position(
        "default",
        "603127",
        "昭衍新药",
        400,
        100,
        Decimal("54.00"),
        date(2026, 7, 27),
    )
    assert updated.quantity == 400
    assert updated.sellable_quantity == 100
    assert len(store.list_positions("default")) == 1


def test_account_and_position_validation_fails_closed(tmp_path: Path) -> None:
    store = ReplayStore(tmp_path / "trader.db")
    store.create_account("default", Decimal("100000"))

    with pytest.raises(StorageError, match="already exists"):
        store.create_account("default", Decimal("100000"))
    with pytest.raises(StorageError, match="two decimal places"):
        store.update_account("default", cash=Decimal("1.001"))
    with pytest.raises(StorageError, match="between zero and total"):
        store.upsert_position(
            "default",
            "603127",
            "昭衍新药",
            300,
            301,
            Decimal("55.68"),
            date(2026, 7, 16),
        )
