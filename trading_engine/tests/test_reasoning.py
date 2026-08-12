from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from typer.testing import CliRunner

from trading_engine.cli import app
from trading_engine.config import TraderSettings
from trading_engine.context import DecisionContextBuilder
from trading_engine.context_store import ContextStore
from trading_engine.errors import ContextError, StorageError
from trading_engine.models import MarketSnapshot
from trading_engine.storage import ReplayStore


SHANGHAI = ZoneInfo("Asia/Shanghai")
AS_OF = datetime(2026, 7, 28, 10, 30, tzinfo=SHANGHAI)
runner = CliRunner()


def _quote(code: str, price: float, pre_close: float) -> dict:
    return {
        "code": code,
        "price": price,
        "pre_close": pre_close,
        "change_pct": (price - pre_close) / pre_close * 100,
        "volume": 1000,
        "amount": 1_000_000,
        "open": pre_close,
        "high": max(price, pre_close),
        "low": min(price, pre_close),
    }


def _seed_and_build(
    tmp_path: Path,
) -> tuple[ReplayStore, ContextStore, DecisionContextBuilder, "DecisionContextRecord"]:
    database = tmp_path / "trader.db"
    store = ReplayStore(database)
    context_store = ContextStore(database)
    store.create_account("paper", Decimal("100000"), Decimal("50000"))
    store.upsert_position(
        "paper",
        "603127",
        "昭衍新药",
        300,
        300,
        Decimal("50.00"),
        AS_OF.date() - timedelta(days=1),
    )
    thesis = store.upsert_thesis(
        "innovation_medicine",
        "创新药",
        "active",
        "研发需求改善",
        "需求完成定价",
        "需求被否定",
    )
    store.link_position_thesis("paper", "603127", thesis.key)
    pool = store.upsert_watch_pool(
        "innovation_pool", "创新药直接受益池", thesis.key
    )
    store.set_watch_pool_member(pool.key, "603127", "direct", True)
    store.set_watch_pool_member(pool.key, "300255", "research", False)
    factor = store.upsert_risk_factor("growth", "成长风格", Decimal("60"))
    store.link_position_risk_factor("paper", "603127", factor.key)
    context_store.add_evidence(
        thesis_key=thesis.key,
        kind="announcement",
        source_name="交易所公告",
        published_at=AS_OF.replace(hour=9, minute=0),
        observed_at=AS_OF.replace(hour=9, minute=1),
        summary="可观察的历史证据",
        stance="supports",
        reliability="high",
    )
    _backdate_core_state(database, AS_OF.replace(hour=9, minute=10))

    snapshot = MarketSnapshot(
        as_of=AS_OF,
        source="astock-live",
        payload={
            "mode": "shadow",
            "quotes": [
                _quote("603127", 52, 50),
                _quote("300255", 20, 19),
            ],
        },
    )
    builder = DecisionContextBuilder(store, context_store)
    record = builder.build(snapshot, "paper")
    return store, context_store, builder, record


def _backdate_core_state(database: Path, timestamp: datetime) -> None:
    value = timestamp.isoformat()
    with sqlite3.connect(database) as connection:
        for table in (
            "accounts",
            "positions",
            "theses",
            "watch_pools",
            "watch_pool_members",
            "risk_factors",
            "trade_plans",
        ):
            connection.execute(
                f"UPDATE {table} SET created_at = ?, updated_at = ?", (value, value)
            )
        for table in ("position_theses", "position_risk_factors"):
            connection.execute(f"UPDATE {table} SET created_at = ?", (value,))


def test_add_reasoning_returns_immutable_record(tmp_path: Path) -> None:
    _, context_store, _, record = _seed_and_build(tmp_path)

    reasoning = context_store.add_reasoning(
        context_id=record.id,
        observed="PCB板块排名第3，5只涨停",
        hypothesis="AI硬件需求拉动PCB放量",
        verified="沪电领涨8.5%，深南盘中跟进",
        conclusion="三维确认，BUY 沪电 100股",
    )

    assert reasoning.context_id == record.id
    assert reasoning.observed == "PCB板块排名第3，5只涨停"
    assert reasoning.hypothesis == "AI硬件需求拉动PCB放量"
    assert reasoning.verified == "沪电领涨8.5%，深南盘中跟进"
    assert reasoning.conclusion == "三维确认，BUY 沪电 100股"
    assert reasoning.created_at is not None


def test_list_reasoning_filters_by_context(tmp_path: Path) -> None:
    _, context_store, _, record = _seed_and_build(tmp_path)

    context_store.add_reasoning(
        context_id=record.id,
        observed="观察到A",
        hypothesis="假设A",
        verified="验证A",
        conclusion="结论A",
    )
    context_store.add_reasoning(
        context_id=record.id,
        observed="观察到B",
        hypothesis="假设B",
        verified="验证B",
        conclusion="结论B",
    )

    all_records = context_store.list_reasoning()
    assert len(all_records) == 2
    assert all_records[0].observed == "观察到A"
    assert all_records[1].observed == "观察到B"

    filtered = context_store.list_reasoning(record.id)
    assert len(filtered) == 2
    assert all(r.context_id == record.id for r in filtered)

    empty = context_store.list_reasoning("nonexistent-id")
    assert empty == ()


def test_add_reasoning_rejects_empty_fields(tmp_path: Path) -> None:
    _, context_store, _, record = _seed_and_build(tmp_path)

    with pytest.raises(ContextError, match="observed"):
        context_store.add_reasoning(
            context_id=record.id,
            observed="  ",
            hypothesis="假设",
            verified="验证",
            conclusion="结论",
        )


def test_add_reasoning_rejects_nonexistent_context(tmp_path: Path) -> None:
    _, context_store, _, _ = _seed_and_build(tmp_path)

    with pytest.raises(StorageError, match="does not exist"):
        context_store.add_reasoning(
            context_id="nonexistent",
            observed="观察到",
            hypothesis="假设",
            verified="验证",
            conclusion="结论",
        )


def _settings_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = TraderSettings(
        repo_root=tmp_path,
        astock_binary=tmp_path / "astock",
        data_dir=tmp_path,
    )
    monkeypatch.setattr(TraderSettings, "load", classmethod(lambda cls: settings))


def test_reasoning_add_cli_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, context_store, _, record = _seed_and_build(tmp_path)
    _settings_stub(tmp_path, monkeypatch)

    result = runner.invoke(
        app,
        [
            "context", "reasoning", "add",
            "--context", record.id,
            "--observed", "PCB板块排名第3",
            "--hypothesis", "AI硬件需求拉动PCB放量",
            "--verified", "沪电领涨8.5%",
            "--conclusion", "BUY 沪电 100股",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert data[0]["context_id"] == record.id
    assert data[0]["observed"] == "PCB板块排名第3"
    assert data[0]["conclusion"] == "BUY 沪电 100股"


def test_reasoning_list_cli_command(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, context_store, _, record = _seed_and_build(tmp_path)
    _settings_stub(tmp_path, monkeypatch)

    context_store.add_reasoning(
        context_id=record.id,
        observed="观察到A",
        hypothesis="假设A",
        verified="验证A",
        conclusion="结论A",
    )

    result = runner.invoke(
        app,
        ["context", "reasoning", "list", "--json"],
    )

    assert result.exit_code == 0, result.stdout
    data = json.loads(result.stdout)
    assert len(data) == 1
    assert data[0]["observed"] == "观察到A"
