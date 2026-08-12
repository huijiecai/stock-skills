import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from trading_engine.analysis import ConservativeShadowProvider, ReadOnlyAnalyzer
from trading_engine.context import DecisionContextBuilder
from trading_engine.context_store import ContextStore
from trading_engine.models import MarketSnapshot
from trading_engine.storage import ReplayStore


OBSERVED_AT = datetime(2026, 7, 27, 11, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


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


def _seed_and_build(tmp_path: Path):
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
        OBSERVED_AT.date() - timedelta(days=1),
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
    store.set_watch_pool_member(pool.key, "000021", "research", False)
    factor = store.upsert_risk_factor("growth", "成长风格", Decimal("60"))
    store.link_position_risk_factor("paper", "603127", factor.key)
    context_store.add_evidence(
        thesis_key=thesis.key,
        kind="announcement",
        source_name="交易所公告",
        published_at=OBSERVED_AT.replace(hour=9, minute=0),
        observed_at=OBSERVED_AT.replace(hour=9, minute=1),
        summary="可观察的历史证据",
        stance="supports",
        reliability="high",
    )
    _backdate_core_state(database, OBSERVED_AT.replace(hour=9, minute=10))

    snapshot = MarketSnapshot(
        as_of=OBSERVED_AT,
        source="astock-live",
        payload={
            "mode": "shadow",
            "quotes": [
                _quote("603127", 49.79, 45.26),
                _quote("000021", 42.28, 41.99),
            ],
        },
    )
    builder = DecisionContextBuilder(store, context_store)
    context_record = builder.build(snapshot, "paper")
    return store, context_record


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


def test_conservative_provider_never_proposes_trade_from_price_alone(
    tmp_path: Path,
) -> None:
    store, context_record = _seed_and_build(tmp_path)

    record = ReadOnlyAnalyzer(store).analyze(context_record)

    assert record.status == "completed"
    assert record.attempts == 1
    assert [proposal.action for proposal in record.report.proposals] == [
        "RESEARCH",
        "WAIT",
    ]
    assert store.latest_judgment() == record


class FailOnceProvider:
    name = "test-provider"
    model = "test-v1"

    def __init__(self) -> None:
        self.calls = 0

    def judge(self, context):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary model timeout")
        return ConservativeShadowProvider().judge(context).model_copy(
            update={"provider": self.name, "model": self.model}
        )


def test_judgment_retries_and_audits_attempt_count(tmp_path: Path) -> None:
    store, context_record = _seed_and_build(tmp_path)
    provider = FailOnceProvider()

    record = ReadOnlyAnalyzer(store, provider=provider, max_attempts=2).analyze(context_record)

    assert provider.calls == 2
    assert record.status == "completed"
    assert record.attempts == 2


class AlwaysFailProvider:
    name = "test-provider"
    model = "test-v1"

    def judge(self, context):
        raise RuntimeError("model unavailable")


class MissingCodeProvider:
    name = "test-provider"
    model = "test-v1"

    def judge(self, context):
        report = ConservativeShadowProvider().judge(context)
        return report.model_copy(
            update={
                "provider": self.name,
                "model": self.model,
                "proposals": report.proposals[:1],
            }
        )


class InvalidActionProvider:
    name = "test-provider"
    model = "test-v1"

    def judge(self, context):
        return {
            "snapshot_id": context.snapshot_id,
            "as_of": context.as_of,
            "provider": self.name,
            "model": self.model,
            "proposals": [
                {
                    "code": quote.code,
                    "action": "PANIC",
                    "confidence": 1,
                    "reason": "invalid action",
                }
                for quote in context.quotes
            ],
        }


def test_judgment_failure_is_persisted_without_breaking_snapshot(tmp_path: Path) -> None:
    store, context_record = _seed_and_build(tmp_path)

    record = ReadOnlyAnalyzer(
        store, provider=AlwaysFailProvider(), max_attempts=2
    ).analyze(context_record)

    assert record.status == "failed"
    assert record.attempts == 2
    assert record.report is None
    assert record.error == "model unavailable"
    assert store.latest_judgment() == record


def test_judgment_rejects_output_that_omits_an_input_code(tmp_path: Path) -> None:
    store, context_record = _seed_and_build(tmp_path)

    record = ReadOnlyAnalyzer(
        store, provider=MissingCodeProvider(), max_attempts=1
    ).analyze(context_record)

    assert record.status == "failed"
    assert record.error == "judgment output stock codes do not match input snapshot"


def test_judgment_rejects_provider_output_that_fails_schema(tmp_path: Path) -> None:
    store, context_record = _seed_and_build(tmp_path)

    record = ReadOnlyAnalyzer(
        store, provider=InvalidActionProvider(), max_attempts=1
    ).analyze(context_record)

    assert record.status == "failed"
    assert "Input should be 'WAIT', 'RESEARCH', 'BUY' or 'SELL'" in record.error
