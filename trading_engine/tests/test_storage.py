from datetime import date, time
from decimal import Decimal
from pathlib import Path

import pytest

from trading_engine.errors import StorageError
from trading_engine.replay import replay_timeline
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


def test_independent_research_context_round_trip(tmp_path: Path) -> None:
    store = ReplayStore(tmp_path / "trader.db")
    store.create_account("default", Decimal("100000"))
    store.upsert_position(
        "default",
        "603127",
        "昭衍新药",
        300,
        300,
        Decimal("55.68"),
        date(2026, 7, 16),
    )

    thesis = store.upsert_thesis(
        "innovation_medicine",
        "创新药",
        "active",
        "海外授权与研发需求改善",
        "订单和板块表现完成定价",
        "需求被否定且直接受益池持续转弱",
        "continuous",
        "confirmed",
        "海外授权和研发订单",
        "研发需求改善 -> CXO订单 -> 昭衍新药",
        "sub_industry",
        "固定池多数上涨且昭衍保持前二",
    )
    thesis_link = store.link_position_thesis(
        "default", "603127", "innovation_medicine"
    )
    pool = store.upsert_watch_pool(
        "innovation_pool",
        "创新药直接受益池",
        thesis.key,
        monitoring_status="dormant",
    )
    direct = store.set_watch_pool_member(
        pool.key, "603127", "direct", True, "volume"
    )
    research = store.set_watch_pool_member(
        pool.key, "300255", "research", False
    )
    factor = store.upsert_risk_factor(
        "growth", "成长风格", Decimal("60.00")
    )
    risk_link = store.link_position_risk_factor(
        "default", "603127", factor.key
    )

    assert thesis_link.thesis_id == thesis.id
    assert thesis.stage == "confirmed"
    assert thesis.transmission_chain.endswith("昭衍新药")
    assert store.list_position_theses("default", "603127") == (thesis_link,)
    assert store.get_watch_pool(pool.key).thesis_id == thesis.id
    assert store.get_watch_pool(pool.key).monitoring_status == "dormant"
    assert store.list_watch_pool_members(pool.key) == (research, direct)
    assert direct.relationship == "volume"
    assert factor.max_exposure_pct == Decimal("60")
    assert store.list_position_risk_factors("default", "603127") == (risk_link,)


def test_structured_trade_plan_round_trip(tmp_path: Path) -> None:
    store = ReplayStore(tmp_path / "trader.db")
    thesis = store.upsert_thesis(
        "defense_restructuring",
        "兵装集团重组",
        "active",
        "旧事件重新定价",
        "方案披露并完成定价",
        "重组终止或固定池与领导同时断裂",
        "event",
        "confirmed",
        "兵装集团分立重组",
        "集团关系调整 -> 上市平台重估 -> 长城军工",
        "company",
        "关系池至少4/6且领导分歧后重新主动",
    )
    store.upsert_risk_factor("defense", "兵装主题", Decimal("30"))

    plan = store.upsert_trade_plan(
        key="buy_great_wall_20260727",
        trading_date=date(2026, 7, 27),
        thesis_key=thesis.key,
        action="BUY",
        target_code="601606",
        target_name="长城军工",
        quantity=500,
        priority=1,
        trigger_conditions=(
            "兵装关系池至少4/6上涨",
            "长城军工可成交分歧后重新领先",
        ),
        ranking_notes="与同批机会排序，最多执行前两名",
        rationale="只交易旧重组关系重新定价，不假设资产注入",
        buy_point_type="confirmation",
        risk_factor_key="defense",
        observation_times=(time(9, 35), time(9, 50)),
        required_observations=1,
        guard_conditions=("不是一字板",),
        cancel_conditions=("关系池缩至2/6且领导断裂",),
    )

    loaded = store.get_trade_plan(plan.key)
    assert loaded == plan
    assert loaded.observation_times == (time(9, 35), time(9, 50))
    assert store.list_trade_plans(date(2026, 7, 27), ("active",)) == (plan,)


def test_research_context_relationships_fail_closed(tmp_path: Path) -> None:
    store = ReplayStore(tmp_path / "trader.db")
    store.upsert_thesis(
        "innovation_medicine",
        "创新药",
        "active",
        "summary",
        "realization",
        "invalidation",
    )
    store.upsert_watch_pool("innovation_pool", "创新药池")

    with pytest.raises(StorageError, match="position does not exist"):
        store.link_position_thesis(
            "default", "603127", "innovation_medicine"
        )
    with pytest.raises(StorageError, match="cannot be tradable"):
        store.set_watch_pool_member(
            "innovation_pool", "300255", "research", True
        )
    with pytest.raises(StorageError, match="between 0 and 100"):
        store.upsert_risk_factor("growth", "成长风格", Decimal("100.01"))
