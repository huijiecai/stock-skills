from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from trading_engine.errors import JudgmentError
from trading_engine.models import (
    JudgmentContext,
    JudgmentProposal,
    JudgmentRecord,
    JudgmentReport,
    LiveQuote,
    LiveSnapshotRecord,
)
from trading_engine.storage import ReplayStore

if TYPE_CHECKING:
    from trading_engine.context_models import DecisionContextRecord


class JudgmentProvider(Protocol):
    name: str
    model: str

    def judge(self, context: JudgmentContext) -> JudgmentReport:
        """Return a structured proposal without executing any action."""


class ConservativeShadowProvider:
    """Deterministic fallback until an external LLM adapter is configured."""

    name = "shadow-rules"
    model = "conservative-v1"

    def judge(self, context: JudgmentContext) -> JudgmentReport:
        proposals = []
        for quote in context.quotes:
            if abs(quote.change_pct) >= 5:
                action = "RESEARCH"
                confidence = 0.35
                reason = (
                    f"涨跌幅 {quote.change_pct:+.2f}% 达到观察阈值；完整结构化上下文"
                    "已加载，等待外部LLM检查预期、联动和资金证据。"
                    if context.domain_context is not None
                    else (
                        f"涨跌幅 {quote.change_pct:+.2f}% 达到观察阈值；仅凭价格不能"
                        "确认预期、板块联动或资金撤退，需要补充证据。"
                    )
                )
                evidence = (f"price_change_pct={quote.change_pct:+.2f}",)
            else:
                action = "WAIT"
                confidence = 0.2
                reason = (
                    "完整上下文已通过校验；保守节点未检测到价格触发，等待外部LLM"
                    "完成语义判断。"
                    if context.domain_context is not None
                    else "当前快照没有足够的方向、催化和资金证据，保持只读观察。"
                )
                evidence = (f"price_change_pct={quote.change_pct:+.2f}",)
            proposals.append(
                JudgmentProposal(
                    code=quote.code,
                    action=action,
                    confidence=confidence,
                    reason=reason,
                    evidence=evidence,
                )
            )

        limitations = (
            (
                "完整结构化上下文已载入；当前保守节点只执行确定性价格触发，"
                "不替代后续LLM语义判断。"
            ),
            "BUY/SELL 必须等待外部LLM和代码校验，本节点不会执行交易。",
        ) if context.domain_context is not None else (
            "本轮只消费实时价格快照，未读取板块、催化、持仓预期或账户风险数据。",
            "BUY/SELL 必须等待后续证据节点和代码校验，本节点不会执行交易。",
        )

        return JudgmentReport(
            snapshot_id=context.snapshot_id,
            as_of=context.as_of,
            provider=self.name,
            model=self.model,
            proposals=tuple(proposals),
            limitations=limitations,
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
        self.provider = provider or ConservativeShadowProvider()
        self.max_attempts = max_attempts

    def analyze(
        self,
        snapshot_record: LiveSnapshotRecord,
        decision_context: "DecisionContextRecord | None" = None,
    ) -> JudgmentRecord:
        if decision_context is not None:
            if (
                decision_context.context.market_snapshot_id
                != snapshot_record.id
            ):
                raise JudgmentError(
                    "decision context market snapshot does not match judgment input"
                )
            if not decision_context.context.ready_for_judgment:
                raise JudgmentError(
                    "decision context is blocked: "
                    + ", ".join(decision_context.context.blockers)
                )
            quotes = _context_quotes(decision_context)
        else:
            quotes = tuple(snapshot_record.snapshot.payload.get("quotes", []))
        try:
            context = JudgmentContext(
                snapshot_id=snapshot_record.id,
                as_of=snapshot_record.snapshot.as_of,
                source=snapshot_record.snapshot.source,
                quotes=quotes,
                decision_context_id=(
                    decision_context.id if decision_context is not None else None
                ),
                decision_context_fingerprint=(
                    decision_context.fingerprint
                    if decision_context is not None
                    else None
                ),
                domain_context=(
                    decision_context.context.model_dump(mode="json")
                    if decision_context is not None
                    else None
                ),
                policy=(
                    "context-read-only-v1"
                    if decision_context is not None
                    else "read-only-shadow-v1"
                ),
            )
        except Exception as exc:
            raise JudgmentError(f"invalid judgment input: {exc}") from exc

        last_error: Exception | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                provider_output = self.provider.judge(context)
                report = JudgmentReport.model_validate(
                    provider_output.model_dump()
                    if isinstance(provider_output, JudgmentReport)
                    else provider_output
                )
                if report.snapshot_id != snapshot_record.id:
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
                    snapshot_record.id,
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
            snapshot_record.id,
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
