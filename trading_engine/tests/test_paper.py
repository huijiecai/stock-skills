from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from trading_engine.analysis import ReadOnlyAnalyzer
from trading_engine.cli import app
from trading_engine.config import TraderSettings
from trading_engine.context import DecisionContextBuilder
from trading_engine.context_store import ContextStore
from trading_engine.errors import PaperTradingError
from trading_engine.models import (
    JudgmentProposal,
    JudgmentReport,
    MarketSnapshot,
)
from trading_engine.paper import PaperBroker, is_main_board_code
from trading_engine.paper_reports import PaperReportGenerator
from trading_engine.paper_models import PaperPolicy
from trading_engine.paper_store import PaperStore
from trading_engine.storage import ReplayStore


SHANGHAI = ZoneInfo("Asia/Shanghai")
DAY_ONE = datetime(2026, 7, 28, 10, 30, tzinfo=SHANGHAI)
runner = CliRunner()


class StaticTradeProvider:
    name = "test-trade-provider"
    model = "test-trade-v1"

    def __init__(self, action: str, quantity: int | None = None) -> None:
        self.action = action
        self.quantity = quantity

    def judge(self, context):
        return JudgmentReport(
            snapshot_id=context.snapshot_id,
            as_of=context.as_of,
            provider=self.name,
            model=self.model,
            proposals=tuple(
                JudgmentProposal(
                    code=quote.code,
                    action=self.action,
                    quantity=self.quantity,
                    confidence=0.8,
                    reason="deterministic paper test proposal",
                    evidence=("fixture",),
                )
                for quote in context.quotes
            ),
        )


def _quote(code: str, price: float) -> dict:
    return {
        "code": code,
        "price": price,
        "pre_close": price,
        "change_pct": 0,
        "volume": 1000,
        "amount": 1_000_000,
        "open": price,
        "high": price,
        "low": price,
    }


def _seed_paper(
    tmp_path: Path,
    *,
    code: str = "603127",
    tradable: bool = True,
    cash: Decimal = Decimal("100000"),
) -> tuple[ReplayStore, ContextStore, PaperStore, PaperBroker]:
    database = tmp_path / "trader.db"
    store = ReplayStore(database)
    context_store = ContextStore(database)
    paper_store = PaperStore(database)
    store.create_account("paper", cash)
    thesis = store.upsert_thesis(
        "paper_thesis",
        "Paper thesis",
        "active",
        "A deterministic thesis",
        "Condition passes",
        "Condition fails",
    )
    pool = store.upsert_watch_pool("paper_pool", "Paper pool", thesis.key)
    store.set_watch_pool_member(pool.key, code, "direct", tradable)
    store.upsert_risk_factor("paper_risk", "Paper risk", Decimal("80"))
    context_store.add_evidence(
        thesis_key=thesis.key,
        kind="announcement",
        source_name="fixture",
        published_at=DAY_ONE - timedelta(hours=2),
        observed_at=DAY_ONE - timedelta(hours=1),
        summary="Known before the decision",
        stance="supports",
        reliability="high",
    )
    _backdate_core_state(database, DAY_ONE.replace(hour=9, minute=10))
    return (
        store,
        context_store,
        paper_store,
        PaperBroker(store, context_store, paper_store),
    )


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


def _judgment(
    store: ReplayStore,
    context_store: ContextStore,
    at: datetime,
    code: str,
    price: float,
    action: str,
    quantity: int | None,
):
    _backdate_core_state(store.database, at - timedelta(minutes=5))
    market = store.record_market_snapshot(
        MarketSnapshot(
            as_of=at,
            source="astock-live",
            payload={"mode": "shadow", "quotes": [_quote(code, price)]},
        )
    )
    context = DecisionContextBuilder(store, context_store).build(market, "paper")
    assert context.context.ready_for_judgment is True
    return ReadOnlyAnalyzer(
        store,
        provider=StaticTradeProvider(action, quantity),
        max_attempts=1,
    ).analyze(market, context)


def _link_bought_position(store: ReplayStore, code: str = "603127") -> None:
    store.link_position_thesis("paper", code, "paper_thesis")
    store.link_position_risk_factor("paper", code, "paper_risk")


def test_trade_proposals_require_quantity() -> None:
    with pytest.raises(ValidationError, match="require quantity"):
        JudgmentProposal(
            code="603127",
            action="BUY",
            confidence=1,
            reason="missing quantity",
        )
    with pytest.raises(ValidationError, match="cannot include quantity"):
        JudgmentProposal(
            code="603127",
            action="WAIT",
            quantity=100,
            confidence=1,
            reason="unexpected quantity",
        )


def test_paper_buy_is_atomic_idempotent_and_auditable(tmp_path: Path) -> None:
    store, context_store, paper_store, broker = _seed_paper(tmp_path)
    judgment = _judgment(
        store, context_store, DAY_ONE, "603127", 20, "BUY", 100
    )

    first = broker.execute_judgment("paper", judgment.id)
    second = broker.execute_judgment("paper", judgment.id)

    assert first.id == second.id
    assert len(first.orders) == 1
    assert first.orders[0].status == "filled"
    assert len(first.fills) == 1
    assert all(check.passed for check in first.checks[first.orders[0].id])
    account = store.get_account("paper")
    position = store.get_position("paper", "603127")
    assert account.cash == Decimal("98000.00")
    assert position.quantity == 100
    assert position.sellable_quantity == 0
    assert position.average_cost == Decimal("20.00")
    assert len(paper_store.list_fills("paper")) == 1
    assert paper_store.audit_order(first.orders[0].id).valid is True
    assert paper_store.audit_account("paper").valid is True

    _link_bought_position(store)
    _backdate_core_state(store.database, DAY_ONE.replace(hour=9, minute=10))
    next_market = store.record_market_snapshot(
        MarketSnapshot(
            as_of=DAY_ONE + timedelta(minutes=1),
            source="astock-live",
            payload={"mode": "shadow", "quotes": [_quote("603127", 20)]},
        )
    )
    next_context = DecisionContextBuilder(store, context_store).build(
        next_market, "paper"
    )
    assert len(next_context.context.execution_history) == 1
    executed = next_context.context.execution_history[0]
    assert executed.code == "603127"
    assert executed.side == "BUY"
    assert executed.quantity == 100
    assert executed.sellable_after == 0


def test_non_trading_judgment_is_consumed_as_skipped_event(tmp_path: Path) -> None:
    store, context_store, paper_store, broker = _seed_paper(tmp_path)
    judgment = _judgment(
        store, context_store, DAY_ONE, "603127", 20, "WAIT", None
    )

    result = broker.execute_judgment("paper", judgment.id)

    assert len(result.events) == 1
    assert result.events[0].status == "skipped"
    assert result.orders == ()
    assert result.fills == ()
    assert paper_store.audit_account("paper").valid is True


def test_t_plus_one_rejects_same_day_then_allows_next_day_sell(
    tmp_path: Path,
) -> None:
    store, context_store, paper_store, broker = _seed_paper(tmp_path)
    buy = _judgment(store, context_store, DAY_ONE, "603127", 20, "BUY", 100)
    broker.execute_judgment("paper", buy.id)
    _link_bought_position(store)

    same_day_sell = _judgment(
        store,
        context_store,
        DAY_ONE + timedelta(minutes=30),
        "603127",
        21,
        "SELL",
        100,
    )
    rejected = broker.execute_judgment("paper", same_day_sell.id)
    assert rejected.orders[0].status == "rejected"
    assert rejected.fills == ()
    assert any(
        check.name == "t_plus_one" and not check.passed
        for check in rejected.checks[rejected.orders[0].id]
    )
    assert store.get_position("paper", "603127").quantity == 100

    assert paper_store.settle_positions(
        "paper", (DAY_ONE + timedelta(days=1)).date()
    ) == 1
    next_day_sell = _judgment(
        store,
        context_store,
        DAY_ONE + timedelta(days=1),
        "603127",
        22,
        "SELL",
        100,
    )
    filled = broker.execute_judgment("paper", next_day_sell.id)
    assert filled.orders[0].status == "filled"
    assert filled.fills[0].cash_after == Decimal("100200.00")
    assert store.list_positions("paper") == ()
    assert paper_store.audit_account("paper").valid is True


@pytest.mark.parametrize(
    ("code", "tradable", "cash", "quantity", "failed_rule"),
    [
        ("300255", True, Decimal("100000"), 100, "main_board_buy"),
        ("603127", True, Decimal("100000"), 50, "buy_lot"),
        ("603127", False, Decimal("100000"), 100, "tradable_pool"),
        ("603127", True, Decimal("1000"), 100, "cash"),
        ("603127", True, Decimal("100000"), 2000, "single_position_limit"),
    ],
)
def test_buy_hard_rules_reject_without_mutating_account(
    tmp_path: Path,
    code: str,
    tradable: bool,
    cash: Decimal,
    quantity: int,
    failed_rule: str,
) -> None:
    store, context_store, _, broker = _seed_paper(
        tmp_path, code=code, tradable=tradable, cash=cash
    )
    judgment = _judgment(
        store, context_store, DAY_ONE, code, 20, "BUY", quantity
    )

    result = broker.execute_judgment("paper", judgment.id)

    order = result.orders[0]
    assert order.status == "rejected"
    assert result.fills == ()
    assert any(
        check.name == failed_rule and not check.passed
        for check in result.checks[order.id]
    )
    assert store.get_account("paper").cash == cash
    assert store.list_positions("paper") == ()


def test_cooldown_and_duplicate_signal_rules(tmp_path: Path) -> None:
    store, context_store, _, broker = _seed_paper(tmp_path)
    store.update_account("paper", cooldown=True)
    cooldown_judgment = _judgment(
        store, context_store, DAY_ONE, "603127", 20, "BUY", 100
    )
    cooldown_result = broker.execute_judgment("paper", cooldown_judgment.id)
    assert cooldown_result.orders[0].status == "rejected"
    assert any(
        check.name == "account_cooldown" and not check.passed
        for check in cooldown_result.checks[cooldown_result.orders[0].id]
    )

    store.update_account("paper", cooldown=False)
    buy = _judgment(
        store,
        context_store,
        DAY_ONE + timedelta(minutes=10),
        "603127",
        20,
        "BUY",
        100,
    )
    broker.execute_judgment("paper", buy.id)
    _link_bought_position(store)
    duplicate = _judgment(
        store,
        context_store,
        DAY_ONE + timedelta(minutes=20),
        "603127",
        20,
        "BUY",
        100,
    )
    duplicate_result = broker.execute_judgment("paper", duplicate.id)
    assert duplicate_result.orders[0].status == "rejected"
    assert any(
        check.name == "duplicate_signal" and not check.passed
        for check in duplicate_result.checks[duplicate_result.orders[0].id]
    )
    assert store.get_position("paper", "603127").quantity == 100


def test_new_position_is_rejected_at_or_after_cutoff(tmp_path: Path) -> None:
    store, context_store, _, broker = _seed_paper(tmp_path)
    judgment = _judgment(
        store,
        context_store,
        DAY_ONE.replace(hour=14, minute=50),
        "603127",
        20,
        "BUY",
        100,
    )

    result = broker.execute_judgment("paper", judgment.id)

    assert result.orders[0].status == "rejected"
    assert any(
        check.name == "new_position_cutoff" and not check.passed
        for check in result.checks[result.orders[0].id]
    )
    assert store.list_positions("paper") == ()


def test_gross_and_named_risk_exposure_limits_are_enforced(tmp_path: Path) -> None:
    store, context_store, paper_store, _ = _seed_paper(tmp_path)
    gross_broker = PaperBroker(
        store,
        context_store,
        paper_store,
        PaperPolicy(
            max_single_position_pct=Decimal("100"),
            max_gross_exposure_pct=Decimal("1"),
        ),
    )
    gross_judgment = _judgment(
        store, context_store, DAY_ONE, "603127", 20, "BUY", 100
    )
    gross_result = gross_broker.execute_judgment("paper", gross_judgment.id)
    assert any(
        check.name == "gross_exposure_limit" and not check.passed
        for check in gross_result.checks[gross_result.orders[0].id]
    )

    store.upsert_position(
        "paper",
        "603127",
        "Test stock",
        100,
        100,
        Decimal("20"),
        DAY_ONE.date() - timedelta(days=1),
    )
    _link_bought_position(store)
    store.upsert_risk_factor("paper_risk", "Paper risk", Decimal("1"))
    risk_judgment = _judgment(
        store,
        context_store,
        DAY_ONE + timedelta(minutes=30),
        "603127",
        20,
        "BUY",
        100,
    )
    risk_result = PaperBroker(
        store, context_store, paper_store
    ).execute_judgment("paper", risk_judgment.id)
    assert any(
        check.name == "risk_exposure:paper_risk" and not check.passed
        for check in risk_result.checks[risk_result.orders[0].id]
    )


def test_new_position_uses_trade_plan_risk_factor(tmp_path: Path) -> None:
    store, context_store, paper_store, _ = _seed_paper(tmp_path)
    store.upsert_thesis(
        "paper_thesis",
        "Paper thesis",
        "active",
        "A deterministic thesis",
        "Condition passes",
        "Condition fails",
        "event",
        "confirmed",
        "Fixture catalyst",
        "Catalyst -> product -> company",
        "company",
        "Pool and leader confirm together",
    )
    store.upsert_risk_factor("paper_risk", "Paper risk", Decimal("1"))
    store.upsert_trade_plan(
        key="paper_buy_plan",
        trading_date=DAY_ONE.date(),
        thesis_key="paper_thesis",
        action="BUY",
        target_code="603127",
        target_name="Test stock",
        quantity=100,
        priority=1,
        trigger_conditions=("fixture trigger",),
        ranking_notes="fixture ranking",
        rationale="fixture rationale",
        buy_point_type="confirmation",
        risk_factor_key="paper_risk",
    )
    judgment = _judgment(
        store, context_store, DAY_ONE, "603127", 20, "BUY", 100
    )

    result = PaperBroker(
        store, context_store, paper_store
    ).execute_judgment("paper", judgment.id)

    assert result.orders[0].status == "rejected"
    assert any(
        check.name == "risk_exposure:paper_risk" and not check.passed
        for check in result.checks[result.orders[0].id]
    )


def test_stale_or_price_only_judgment_cannot_execute(tmp_path: Path) -> None:
    store, context_store, paper_store, broker = _seed_paper(tmp_path)
    full_context = _judgment(
        store, context_store, DAY_ONE, "603127", 20, "BUY", 100
    )
    store.update_account("paper", cash=Decimal("99999"))
    _backdate_core_state(store.database, DAY_ONE.replace(hour=9, minute=10))
    with pytest.raises(PaperTradingError, match="stale|updated after"):
        broker.execute_judgment("paper", full_context.id)
    assert paper_store.list_orders("paper") == ()

    market = store.record_market_snapshot(
        MarketSnapshot(
            as_of=DAY_ONE + timedelta(hours=1),
            source="astock-live",
            payload={"mode": "shadow", "quotes": [_quote("603127", 20)]},
        )
    )
    price_only = ReadOnlyAnalyzer(store).analyze(market)
    with pytest.raises(PaperTradingError, match="full decision context"):
        broker.execute_judgment("paper", price_only.id)


def test_database_failure_rolls_back_the_complete_execution(tmp_path: Path) -> None:
    store, context_store, paper_store, broker = _seed_paper(tmp_path)
    judgment = _judgment(
        store, context_store, DAY_ONE, "603127", 20, "BUY", 100
    )
    with sqlite3.connect(paper_store.database) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_paper_cash_update
            BEFORE UPDATE OF cash_cents ON accounts
            BEGIN
                SELECT RAISE(ABORT, 'forced paper failure');
            END
            """
        )

    with pytest.raises(PaperTradingError, match="forced paper failure"):
        broker.execute_judgment("paper", judgment.id)

    assert paper_store.find_execution("paper", judgment.id) is None
    assert paper_store.list_orders("paper") == ()
    assert paper_store.list_fills("paper") == ()
    assert paper_store.list_events("paper") == ()
    assert store.get_account("paper").cash == Decimal("100000.00")
    assert store.list_positions("paper") == ()


def test_account_audit_detects_manual_cash_tampering(tmp_path: Path) -> None:
    store, context_store, paper_store, broker = _seed_paper(tmp_path)
    judgment = _judgment(
        store, context_store, DAY_ONE, "603127", 20, "BUY", 100
    )
    broker.execute_judgment("paper", judgment.id)

    store.update_account("paper", cash=Decimal("97000"))

    audit = paper_store.audit_account("paper")
    assert audit.valid is False
    assert "current_cash_does_not_match_last_fill" in audit.issues


def test_reports_and_cli_are_generated_from_sqlite(tmp_path: Path, monkeypatch) -> None:
    store, context_store, paper_store, _ = _seed_paper(tmp_path)
    judgment = _judgment(
        store, context_store, DAY_ONE, "603127", 20, "BUY", 100
    )
    settings = TraderSettings(
        repo_root=tmp_path,
        astock_binary=tmp_path / "astock",
        data_dir=tmp_path,
    )
    monkeypatch.setattr(
        "trading_engine.paper_cli.TraderSettings.load", lambda: settings
    )

    execution = runner.invoke(
        app,
        [
            "paper",
            "execute",
            "--account",
            "paper",
            "--judgment",
            judgment.id,
            "--json",
        ],
    )
    assert execution.exit_code == 0, execution.stdout
    assert json.loads(execution.stdout)["fills"][0]["code"] == "603127"

    audit = runner.invoke(
        app, ["paper", "audit", "--account", "paper", "--json"]
    )
    assert audit.exit_code == 0
    assert json.loads(audit.stdout)["valid"] is True

    report = runner.invoke(
        app,
        [
            "paper",
            "report",
            "--account",
            "paper",
            "--date",
            DAY_ONE.date().isoformat(),
            "--json",
        ],
    )
    assert report.exit_code == 0, report.stdout
    paths = json.loads(report.stdout)
    state = Path(paths["state"])
    trades = Path(paths["trades"])
    daily = Path(paths["daily"])
    assert state.parent == tmp_path / "reports" / "paper"
    assert "Current cash: CNY 98,000.00" in state.read_text(encoding="utf-8")
    assert "603127 | BUY | 100" in trades.read_text(encoding="utf-8")
    assert "Decision events: 1" in daily.read_text(encoding="utf-8")
    assert PaperReportGenerator(
        store, paper_store, tmp_path / "reports"
    ).generate("paper", DAY_ONE.date()).state == str(state)


def test_main_board_code_scope() -> None:
    assert is_main_board_code("600000") is True
    assert is_main_board_code("000001") is True
    assert is_main_board_code("002001") is True
    assert is_main_board_code("300255") is False
    assert is_main_board_code("688001") is False
    assert is_main_board_code("920001") is False
