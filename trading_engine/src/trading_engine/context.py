from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_HALF_UP

from trading_engine.context_models import (
    ContextQuote,
    DecisionContext,
    DecisionContextRecord,
    PoolDecisionContext,
    PositionDecisionContext,
    RiskExposureContext,
)
from trading_engine.context_store import ContextStore
from trading_engine.errors import ContextError
from trading_engine.models import LiveQuote, LiveSnapshotRecord, MinuteBar
from trading_engine.storage import ReplayStore


CENT = Decimal("0.01")
PERCENT = Decimal("0.0001")


class DecisionContextBuilder:
    def __init__(self, store: ReplayStore, context_store: ContextStore) -> None:
        self.store = store
        self.context_store = context_store

    def required_live_codes(self, account_name: str) -> tuple[str, ...]:
        codes = {position.code for position in self.store.list_positions(account_name)}
        for pool in self.store.list_watch_pools():
            if not pool.active:
                continue
            codes.update(
                member.code
                for member in self.store.list_watch_pool_members(pool.key)
            )
        if not codes:
            raise ContextError("context has no positions or active pool members")
        return tuple(sorted(codes))

    def build(
        self, market_record: LiveSnapshotRecord, account_name: str = "default"
    ) -> DecisionContextRecord:
        snapshot = market_record.snapshot
        as_of = snapshot.as_of
        if as_of.tzinfo is None:
            raise ContextError("market snapshot as_of must include a timezone")

        account = self.store.get_account(account_name)
        positions = self.store.list_positions(account_name)
        theses = self.store.list_theses()
        pools = tuple(pool for pool in self.store.list_watch_pools() if pool.active)
        factors = tuple(
            factor for factor in self.store.list_risk_factors() if factor.active
        )
        quotes = extract_context_quotes(market_record)
        quote_by_code = {quote.code: quote for quote in quotes}

        _require_observable("account", account.updated_at, as_of)
        for position in positions:
            _require_observable(f"position:{position.code}", position.updated_at, as_of)
            if position.bought_on > as_of.date():
                raise ContextError(
                    f"position:{position.code} has a buy date after the market snapshot"
                )
        for pool in pools:
            _require_observable(f"pool:{pool.key}", pool.updated_at, as_of)
        for factor in factors:
            _require_observable(f"risk:{factor.key}", factor.updated_at, as_of)

        blockers: list[str] = []
        position_contexts = []
        position_values: dict[str, Decimal] = {}
        relevant_thesis_keys: set[str] = set()
        position_risk_keys: dict[str, tuple[str, ...]] = {}

        for position in positions:
            quote = quote_by_code.get(position.code)
            if quote is None:
                raise ContextError(
                    f"market snapshot is missing position quote: {position.code}"
                )
            thesis_links = self.store.list_position_theses(
                account_name, position.code
            )
            risk_links = self.store.list_position_risk_factors(
                account_name, position.code
            )
            for link in (*thesis_links, *risk_links):
                _require_observable(
                    f"position-link:{position.code}", link.created_at, as_of
                )
            thesis_keys = tuple(link.thesis_key for link in thesis_links)
            risk_keys = tuple(link.risk_factor_key for link in risk_links)
            relevant_thesis_keys.update(thesis_keys)
            position_risk_keys[position.code] = risk_keys
            if not thesis_keys:
                blockers.append(f"position:{position.code}:missing_thesis")
            if not risk_keys:
                blockers.append(f"position:{position.code}:missing_risk_factor")

            market_value = _money(quote.price * position.quantity)
            cost_value = position.average_cost * position.quantity
            unrealized_pnl = _money(market_value - cost_value)
            pnl_pct = (
                ((market_value - cost_value) / cost_value * 100).quantize(PERCENT)
                if cost_value
                else Decimal("0")
            )
            position_values[position.code] = market_value
            position_contexts.append(
                PositionDecisionContext(
                    position=position,
                    quote=quote,
                    market_value=market_value,
                    unrealized_pnl=unrealized_pnl,
                    pnl_pct=pnl_pct,
                    thesis_keys=thesis_keys,
                    risk_factor_keys=risk_keys,
                )
            )

        pool_contexts = []
        for pool in pools:
            members = self.store.list_watch_pool_members(pool.key)
            for member in members:
                _require_observable(
                    f"pool-member:{pool.key}/{member.code}", member.updated_at, as_of
                )
            if pool.thesis_key:
                relevant_thesis_keys.add(pool.thesis_key)
            if not members:
                blockers.append(f"pool:{pool.key}:no_members")
            available_quotes = tuple(
                quote_by_code[member.code]
                for member in members
                if member.code in quote_by_code
            )
            missing_codes = tuple(
                member.code for member in members if member.code not in quote_by_code
            )
            if missing_codes:
                blockers.append(
                    f"pool:{pool.key}:missing_quotes={','.join(missing_codes)}"
                )
            coverage_pct = (
                (Decimal(len(available_quotes)) / len(members) * 100).quantize(
                    PERCENT
                )
                if members
                else Decimal("0")
            )
            pool_contexts.append(
                PoolDecisionContext(
                    pool=pool,
                    members=members,
                    quotes=available_quotes,
                    missing_codes=missing_codes,
                    coverage_pct=coverage_pct,
                )
            )

        relevant_theses = tuple(
            thesis
            for thesis in theses
            if thesis.key in relevant_thesis_keys
            or thesis.status in {"active", "watch"}
        )
        relevant_thesis_keys.update(thesis.key for thesis in relevant_theses)
        for thesis in relevant_theses:
            _require_observable(f"thesis:{thesis.key}", thesis.updated_at, as_of)
        all_evidence = self.context_store.list_evidence(
            tuple(sorted(relevant_thesis_keys))
        )
        included_evidence = tuple(
            evidence
            for evidence in all_evidence
            if evidence.published_at <= as_of.astimezone(UTC)
            and evidence.observed_at <= as_of.astimezone(UTC)
        )
        evidence_thesis_keys = {evidence.thesis_key for evidence in included_evidence}
        for thesis in relevant_theses:
            if thesis.status in {"active", "watch"} and (
                thesis.key not in evidence_thesis_keys
            ):
                blockers.append(f"thesis:{thesis.key}:missing_evidence")

        positions_market_value = _money(sum(position_values.values(), Decimal("0")))
        total_assets = _money(account.cash + positions_market_value)
        risk_contexts = []
        for factor in factors:
            codes = tuple(
                sorted(
                    code
                    for code, keys in position_risk_keys.items()
                    if factor.key in keys
                )
            )
            market_value = _money(
                sum((position_values[code] for code in codes), Decimal("0"))
            )
            exposure_pct = (
                (market_value / total_assets * 100).quantize(PERCENT)
                if total_assets
                else Decimal("0")
            )
            risk_contexts.append(
                RiskExposureContext(
                    factor=factor,
                    position_codes=codes,
                    market_value=market_value,
                    exposure_pct=exposure_pct,
                    limit_breached=exposure_pct > factor.max_exposure_pct,
                )
            )

        unique_blockers = tuple(dict.fromkeys(blockers))
        context = DecisionContext(
            market_snapshot_id=market_record.id,
            account=account,
            as_of=as_of,
            market_source=snapshot.source,
            cash=_money(account.cash),
            positions_market_value=positions_market_value,
            total_assets=total_assets,
            positions=tuple(position_contexts),
            theses=relevant_theses,
            pools=tuple(pool_contexts),
            risk_exposures=tuple(risk_contexts),
            evidence=included_evidence,
            excluded_future_evidence_count=len(all_evidence) - len(included_evidence),
            blockers=unique_blockers,
            ready_for_judgment=not unique_blockers,
        )
        return self.context_store.record_context(context)


def extract_context_quotes(
    market_record: LiveSnapshotRecord,
) -> tuple[ContextQuote, ...]:
    snapshot = market_record.snapshot
    if snapshot.as_of.tzinfo is None:
        raise ContextError("market snapshot as_of must include a timezone")
    if snapshot.source == "astock-live":
        rows = snapshot.payload.get("quotes")
        if not isinstance(rows, list) or not rows:
            raise ContextError("live snapshot contains no quotes")
        quotes = []
        for row in rows:
            quote = LiveQuote.model_validate(row)
            quotes.append(
                ContextQuote(
                    code=quote.code,
                    observed_at=snapshot.as_of,
                    price=_decimal(quote.price),
                    pre_close=_decimal(quote.pre_close),
                    change_pct=_decimal(quote.change_pct),
                    volume=quote.volume,
                    amount=_decimal(quote.amount),
                    open=_decimal(quote.open),
                    high=_decimal(quote.high),
                    low=_decimal(quote.low),
                )
            )
        _require_unique_codes(quotes)
        return tuple(quotes)

    if snapshot.source == "astock-replay":
        instruments = snapshot.payload.get("instruments")
        if not isinstance(instruments, dict) or not instruments:
            raise ContextError("replay snapshot contains no instruments")
        quotes = []
        for code in sorted(instruments):
            instrument = instruments[code]
            pre_close = _decimal(instrument["pre_close"])
            bars = tuple(
                MinuteBar.model_validate(row) for row in instrument.get("bars", [])
            )
            if any(bar.time > snapshot.as_of for bar in bars):
                raise ContextError(f"replay snapshot contains a future bar: {code}")
            if bars:
                price = _decimal(bars[-1].close)
                opening = _decimal(bars[0].open)
                high = max(_decimal(bar.high) for bar in bars)
                low = min(_decimal(bar.low) for bar in bars)
                volume = sum(bar.volume for bar in bars)
                amount = sum((_decimal(bar.amount) for bar in bars), Decimal("0"))
            else:
                price = opening = high = low = pre_close
                volume = 0
                amount = Decimal("0")
            quotes.append(
                ContextQuote(
                    code=code,
                    observed_at=snapshot.as_of,
                    price=price,
                    pre_close=pre_close,
                    change_pct=((price - pre_close) / pre_close * 100).quantize(
                        PERCENT
                    ),
                    volume=volume,
                    amount=amount,
                    open=opening,
                    high=high,
                    low=low,
                )
            )
        return tuple(quotes)

    raise ContextError(f"unsupported market snapshot source: {snapshot.source}")


def _require_observable(label: str, observed_at: datetime, as_of: datetime) -> None:
    if observed_at.tzinfo is None:
        raise ContextError(f"{label} timestamp must include a timezone")
    if observed_at.astimezone(UTC) > as_of.astimezone(UTC):
        raise ContextError(f"{label} was updated after the market snapshot")


def _require_unique_codes(quotes: list[ContextQuote]) -> None:
    codes = [quote.code for quote in quotes]
    if len(codes) != len(set(codes)):
        raise ContextError("market snapshot contains duplicate stock codes")


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
