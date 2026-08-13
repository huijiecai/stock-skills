"""Read-only judgment generator (test/audit infrastructure).

Consumes a :class:`DecisionContextRecord` and produces a :class:`JudgmentRecord`
via a pluggable :class:`JudgmentProvider`. Used by tests to build judgments for
paper-trade verification, and by the legacy ``analyze`` audit path.

The old ``ConservativeShadowProvider`` and ``DeepSeekProvider`` have been
removed — the live agent path (``engine.agent``) replaced them. This module
keeps only the analyzer shell so tests can construct deterministic judgments.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from trading_engine.errors import JudgmentError
from trading_engine.store.models import (
    JudgmentContext,
    JudgmentProposal,
    JudgmentRecord,
    JudgmentReport,
    LiveQuote,
)
from trading_engine.store.storage import ReplayStore

if TYPE_CHECKING:
    from trading_engine.market.context_models import DecisionContextRecord


class JudgmentProvider(Protocol):
    name: str
    model: str

    def judge(self, context: JudgmentContext) -> JudgmentReport:
        """Return a structured proposal without executing any action."""


class StaticShadowProvider:
    """Deterministic fallback: all WAIT. Used as the default provider when no
    real LLM is configured (tests, audit, offline)."""

    name = "shadow-static"
    model = "wait-v1"

    def judge(self, context: JudgmentContext) -> JudgmentReport:
        proposals = tuple(
            JudgmentProposal(
                code=quote.code,
                action="WAIT",
                confidence=0.2,
                reason="static shadow — no signal",
                evidence=(f"change_pct={quote.change_pct:+.2f}",),
            )
            for quote in context.quotes
        )
        return JudgmentReport(
            snapshot_id=context.snapshot_id,
            as_of=context.as_of,
            provider=self.name,
            model=self.model,
            proposals=proposals,
            limitations=("static shadow provider — all WAIT",),
        )


class ReadOnlyAnalyzer:
    def __init__(
        self,
        store: ReplayStore,
        provider: JudgmentProvider | None = None,
        max_attempts: int = 2,
    ) -> None:
        if max_attempts < 1:
            raise JudgmentError("max_attempts must be at least 1")
        self.store = store
        self.provider = provider
        self.max_attempts = max_attempts

    def analyze(
        self,
        decision_context: "DecisionContextRecord",
    ) -> JudgmentRecord:
        context_data = decision_context.context
        if not context_data.ready_for_judgment:
            raise JudgmentError(
                "decision context is blocked: " + ", ".join(context_data.blockers)
            )
        quotes = _context_quotes(decision_context)
        try:
            context = JudgmentContext(
                snapshot_id=context_data.market_snapshot_id,
                as_of=context_data.as_of,
                source=context_data.market_source,
                quotes=quotes,
                decision_context_id=decision_context.id,
                decision_context_fingerprint=decision_context.fingerprint,
                domain_context=context_data.model_dump(mode="json"),
                policy="context-read-only-v1",
            )
        except Exception as exc:
            raise JudgmentError(f"invalid judgment input: {exc}") from exc

        if self.provider is None:
            self.provider = StaticShadowProvider()

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                provider_output = self.provider.judge(context)
                report = JudgmentReport.model_validate(
                    provider_output.model_dump()
                    if isinstance(provider_output, JudgmentReport)
                    else provider_output
                )
                if report.snapshot_id != context_data.market_snapshot_id:
                    raise JudgmentError("judgment output snapshot_id does not match input")
                if report.provider != self.provider.name or report.model != self.provider.model:
                    raise JudgmentError("judgment output provider metadata does not match")
                if report.as_of != context.as_of:
                    raise JudgmentError("judgment output timestamp does not match input")
                input_codes = [quote.code for quote in context.quotes]
                output_codes = [proposal.code for proposal in report.proposals]
                if len(output_codes) != len(set(output_codes)):
                    raise JudgmentError("judgment output contains duplicate stock codes")
                if set(output_codes) != set(input_codes):
                    raise JudgmentError(
                        "judgment output stock codes do not match input snapshot"
                    )
                return self.store.record_judgment(
                    context_data.market_snapshot_id,
                    context,
                    report,
                    self.provider.name,
                    self.provider.model,
                    attempt,
                )
            except Exception as exc:
                last_error = exc

        message = str(last_error or "judgment provider failed")
        return self.store.record_failed_judgment(
            context_data.market_snapshot_id,
            context,
            self.provider.name,
            self.provider.model,
            self.max_attempts,
            message,
        )


def _context_quotes(
    decision_context: "DecisionContextRecord",
) -> tuple[LiveQuote, ...]:
    by_code = {}
    context = decision_context.context
    for position_context in context.positions:
        by_code[position_context.quote.code] = position_context.quote
    for pool_context in context.pools:
        for quote in pool_context.quotes:
            by_code.setdefault(quote.code, quote)
    return tuple(
        LiveQuote(
            code=quote.code,
            price=float(quote.price),
            pre_close=float(quote.pre_close),
            change_pct=float(quote.change_pct),
            volume=quote.volume,
            amount=float(quote.amount),
            open=float(quote.open),
            high=float(quote.high),
            low=float(quote.low),
        )
        for quote in by_code.values()
    )
