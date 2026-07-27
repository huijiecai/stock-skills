from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from trading_engine.analysis import ConservativeShadowProvider, ReadOnlyAnalyzer
from trading_engine.models import LiveSnapshotRecord, MarketSnapshot
from trading_engine.storage import ReplayStore


OBSERVED_AT = datetime(2026, 7, 27, 11, 30, tzinfo=ZoneInfo("Asia/Shanghai"))


def _snapshot_record(tmp_path: Path) -> tuple[ReplayStore, LiveSnapshotRecord]:
    store = ReplayStore(tmp_path / "trader.db")
    snapshot = MarketSnapshot(
        as_of=OBSERVED_AT,
        source="astock-live",
        payload={
            "mode": "shadow",
            "quotes": [
                {
                    "code": "603127",
                    "price": 49.79,
                    "pre_close": 45.26,
                    "change_pct": 10.0088,
                    "volume": 1,
                    "amount": 1,
                    "open": 45.26,
                    "high": 49.79,
                    "low": 45.26,
                },
                {
                    "code": "000021",
                    "price": 42.28,
                    "pre_close": 41.99,
                    "change_pct": 0.6906,
                    "volume": 1,
                    "amount": 1,
                    "open": 41.99,
                    "high": 42.28,
                    "low": 41.99,
                },
            ],
        },
    )
    return store, store.record_live_snapshot(snapshot)


def test_conservative_provider_never_proposes_trade_from_price_alone(
    tmp_path: Path,
) -> None:
    store, snapshot = _snapshot_record(tmp_path)

    record = ReadOnlyAnalyzer(store).analyze(snapshot)

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
    store, snapshot = _snapshot_record(tmp_path)
    provider = FailOnceProvider()

    record = ReadOnlyAnalyzer(store, provider=provider, max_attempts=2).analyze(snapshot)

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
    store, snapshot = _snapshot_record(tmp_path)

    record = ReadOnlyAnalyzer(
        store, provider=AlwaysFailProvider(), max_attempts=2
    ).analyze(snapshot)

    assert record.status == "failed"
    assert record.attempts == 2
    assert record.report is None
    assert record.error == "model unavailable"
    assert store.latest_live_snapshot().id == snapshot.id


def test_judgment_rejects_output_that_omits_an_input_code(tmp_path: Path) -> None:
    store, snapshot = _snapshot_record(tmp_path)

    record = ReadOnlyAnalyzer(
        store, provider=MissingCodeProvider(), max_attempts=1
    ).analyze(snapshot)

    assert record.status == "failed"
    assert record.error == "judgment output stock codes do not match input snapshot"


def test_judgment_rejects_provider_output_that_fails_schema(tmp_path: Path) -> None:
    store, snapshot = _snapshot_record(tmp_path)

    record = ReadOnlyAnalyzer(
        store, provider=InvalidActionProvider(), max_attempts=1
    ).analyze(snapshot)

    assert record.status == "failed"
    assert "Input should be 'WAIT', 'RESEARCH', 'BUY' or 'SELL'" in record.error
