"""Tests for the brief command and BriefGenerator."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from trading_engine.brief import BriefGenerator
from trading_engine.paper_store import PaperStore
from trading_engine.storage import ReplayStore


def _seed_brief_database(tmp_path: Path) -> ReplayStore:
    store = ReplayStore(tmp_path / "trader.db")
    store.create_account("paper", Decimal("100000"), Decimal("20229.40"))
    store.upsert_position(
        "paper",
        "603127",
        "昭衍新药",
        300,
        300,
        Decimal("55.68"),
        date(2026, 7, 16),
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
    brief = BriefGenerator(store, PaperStore(tmp_path / "trader.db")).generate(
        "paper"
    )

    assert brief["account"]["name"] == "paper"
    assert brief["account"]["cash"] == "20229.4"
    assert brief["account"]["cooldown"] is False
    assert brief["positions"][0]["code"] == "603127"
    assert brief["positions"][0]["quantity"] == 300


def test_brief_filters_active_theses(tmp_path: Path) -> None:
    store = _seed_brief_database(tmp_path)
    brief = BriefGenerator(store).generate("paper")

    assert [item["key"] for item in brief["active_theses"]] == [
        "innovation_medicine"
    ]


def test_brief_includes_pools_and_plans(tmp_path: Path) -> None:
    store = _seed_brief_database(tmp_path)
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

    brief = BriefGenerator(store).generate("paper")

    assert brief["active_pools"][0]["key"] == "innovation_pool"
    assert brief["today_plans"][0]["target_code"] == "603127"


def test_brief_market_phase_is_valid(tmp_path: Path) -> None:
    store = _seed_brief_database(tmp_path)
    brief = BriefGenerator(store).generate("paper")

    assert brief["market_phase"] in {
        "pre_market",
        "intraday_morning",
        "midday_break",
        "intraday_afternoon",
        "post_close",
    }


def test_brief_handles_nonexistent_account(tmp_path: Path) -> None:
    brief = BriefGenerator(ReplayStore(tmp_path / "trader.db")).generate(
        "nonexistent"
    )

    assert brief["account"]["error"] == "account does not exist"
    assert brief["positions"] == []
    assert brief["active_theses"] == []
    assert brief["recent_trades"] == []


def test_brief_recent_trades_empty_without_paper_history(tmp_path: Path) -> None:
    store = _seed_brief_database(tmp_path)
    brief = BriefGenerator(store, PaperStore(tmp_path / "trader.db")).generate(
        "paper"
    )

    assert brief["recent_trades"] == []
