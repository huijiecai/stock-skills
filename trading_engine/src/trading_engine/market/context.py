from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, time
from decimal import Decimal, ROUND_HALF_UP

from trading_engine.market.context_models import (
    ContextQuote,
    DecisionContext,
    DecisionContextRecord,
    ExecutedTradeContext,
    HistoricalObservationContext,
    HistoricalPoolObservation,
    HistoricalPositionObservation,
    MarketCandidateContext,
    MarketDiscoveryContext,
    MarketIndexContext,
    PoolDecisionContext,
    PoolMemberSignalContext,
    PoolMetricsContext,
    PositionDecisionContext,
    PricePathContext,
    RiskExposureContext,
    SectorLeaderContext,
    StrategyRulesContext,
    TradePlanContext,
)

from trading_engine.market.context_store import ContextStore
from trading_engine.errors import ContextError
from trading_engine.store.models import LiveQuote, MarketSnapshot, MinuteBar
from trading_engine.trading.paper_store import PaperStore
from trading_engine.store.storage import ReplayStore


CENT = Decimal("0.01")
PERCENT = Decimal("0.0001")
LIMIT_UP_PCT = Decimal("9.5")
STRONG_PCT = Decimal("5")
MONITORED_POOL_STATUSES = {"active", "dormant"}


STRATEGY_RULES = StrategyRulesContext(
    main_board_prefixes=("600", "601", "603", "605", "000", "001", "002", "003"),
    buy_lot_size=100,
    max_theme_exposure_pct=Decimal("30"),
    default_shared_risk_limit_pct=Decimal("60"),
    max_batch_buys=2,
    no_new_positions_after=time(14, 50),
    sell_confirmation_points=2,
    buy_gates=(
        "thesis is stored with a testable catalyst or new validation point",
        "capital breadth, leader price response, and catalyst evidence are all confirmed",
        "expectation, realization condition, and invalidation condition are locked",
        "event, transmission chain, direct-beneficiary pool, and linkage conclusion are explicit",
        "an independent buy-point type is present",
    ),
    ranking_dimensions=(
        "expectation freshness",
        "capital confirmation quality",
        "leader quality",
        "buy-point quality",
        "portfolio shared-risk impact",
    ),
    sell_exit_rules=(
        "exit A clears a position when the expectation realizes, ends, or is invalidated",
        "exit B requires at least two independent failure signals and confirmed capital withdrawal",
        "a single price move, board break, or intraday fluctuation cannot independently trigger a sale",
        "same-day buys are evaluated but cannot be sold under T+1",
    ),
    operating_rules=(
        "fixed pools are defined before market validation and cannot be reverse-built from winners",
        "dormant monitored pools remain visible so intraday reactivation can be detected",
        "leader identity is determined before tradability and account checks",
        "no new position is opened at or after 14:50",
        "one evidence fingerprint cannot be consumed repeatedly as a new exit signal",
        "insufficient information results in WAIT or RESEARCH, never inferred facts",
    ),
)


class DecisionContextBuilder:
    def __init__(self, store: ReplayStore, context_store: ContextStore) -> None:
        self.store = store
        self.context_store = context_store

    def required_live_codes(
        self, account_name: str, trading_date: date | None = None
    ) -> tuple[str, ...]:
        codes = {position.code for position in self.store.list_positions(account_name)}
        for pool in self.store.list_watch_pools():
            if pool.monitoring_status not in MONITORED_POOL_STATUSES:
                continue
            codes.update(
                member.code
                for member in self.store.list_watch_pool_members(pool.key)
            )
        effective_date = trading_date or datetime.now().astimezone().date()
        codes.update(
            plan.target_code
            for plan in self.store.list_trade_plans(
                effective_date, ("active", "triggered")
            )
        )
        if not codes:
            raise ContextError(
                "context has no positions, monitored pool members, or trade plans"
            )
        return tuple(sorted(codes))

    def build(
        self, snapshot: MarketSnapshot, account_name: str = "paper"
    ) -> DecisionContextRecord:
        as_of = snapshot.as_of
        if as_of.tzinfo is None:
            raise ContextError("market snapshot as_of must include a timezone")

        account = self.store.get_account(account_name)
        positions = self.store.list_positions(account_name)
        theses = self.store.list_theses()
        pools = tuple(
            pool
            for pool in self.store.list_watch_pools()
            if pool.monitoring_status in MONITORED_POOL_STATUSES
        )
        plans = self.store.list_trade_plans(
            as_of.date(), ("active", "triggered")
        )
        factors = tuple(
            factor for factor in self.store.list_risk_factors() if factor.active
        )
        quotes = extract_context_quotes(snapshot)
        quote_by_code = {quote.code: quote for quote in quotes}

        _require_observable(
            "account", account.updated_at, as_of, source=snapshot.source
        )
        for position in positions:
            _require_observable(
                f"position:{position.code}",
                position.updated_at,
                as_of,
                source=snapshot.source,
            )
            if position.bought_on > as_of.date():
                raise ContextError(
                    f"position:{position.code} has a buy date after the market snapshot"
                )
        for pool in pools:
            _require_observable(
                f"pool:{pool.key}", pool.updated_at, as_of, source=snapshot.source
            )
        for plan in plans:
            _require_observable(
                f"plan:{plan.key}", plan.updated_at, as_of, source=snapshot.source
            )
        for factor in factors:
            _require_observable(
                f"risk:{factor.key}", factor.updated_at, as_of, source=snapshot.source
            )

        blockers: list[str] = []
        position_contexts = []
        position_values: dict[str, Decimal] = {}
        relevant_thesis_keys: set[str] = set()
        position_risk_keys: dict[str, tuple[str, ...]] = {}
        relevant_thesis_keys.update(plan.thesis_key for plan in plans)

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
                    f"position-link:{position.code}",
                    link.created_at,
                    as_of,
                    source=snapshot.source,
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

        pool_contexts: list[PoolDecisionContext] = []
        for pool in pools:
            members = self.store.list_watch_pool_members(pool.key)
            for member in members:
                _require_observable(
                    f"pool-member:{pool.key}/{member.code}",
                    member.updated_at,
                    as_of,
                    source=snapshot.source,
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
            member_signals, metrics = _pool_signals(members, quote_by_code)
            pool_contexts.append(
                PoolDecisionContext(
                    pool=pool,
                    members=members,
                    quotes=available_quotes,
                    member_signals=member_signals,
                    metrics=metrics,
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
            _require_observable(
                f"thesis:{thesis.key}",
                thesis.updated_at,
                as_of,
                source=snapshot.source,
            )
            if thesis.key in {plan.thesis_key for plan in plans}:
                required_detail = {
                    "thesis_type": thesis.thesis_type,
                    "stage": thesis.stage,
                    "catalyst_anchor": thesis.catalyst_anchor,
                    "transmission_chain": thesis.transmission_chain,
                    "linkage_conclusion": thesis.linkage_conclusion,
                    "confirmation_condition": thesis.confirmation_condition,
                }
                for field, value in required_detail.items():
                    if value is None:
                        blockers.append(
                            f"thesis:{thesis.key}:missing_{field}"
                        )
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

        prior_records = tuple(
            record
            for record in self.context_store.list_contexts_before(
                account_name, as_of
            )
            if record.context.as_of.date() == as_of.date()
        )
        selected_history = _select_observation_history(prior_records, plans)
        observation_history = tuple(
            _compact_observation(record.context) for record in selected_history
        )
        history_times = {item.as_of for item in observation_history}
        plan_contexts = []
        for plan in plans:
            target_quote = quote_by_code.get(plan.target_code)
            target_pool_keys = tuple(
                sorted(
                    pool.pool.key
                    for pool in pool_contexts
                    if any(
                        member.code == plan.target_code
                        for member in pool.members
                    )
                )
            )
            if target_quote is None:
                blockers.append(f"plan:{plan.key}:missing_target_quote")
            if not target_pool_keys:
                blockers.append(f"plan:{plan.key}:target_not_in_monitored_pool")
            observed_times = tuple(
                sorted(
                    value
                    for value in (*history_times, as_of)
                    if value.time().replace(tzinfo=None) in plan.observation_times
                )
            )
            observed_clocks = {
                value.time().replace(tzinfo=None) for value in observed_times
            }
            missing_observation_times = tuple(
                value
                for value in plan.observation_times
                if value <= as_of.time().replace(tzinfo=None)
                and value not in observed_clocks
            )
            if missing_observation_times:
                blockers.append(
                    f"plan:{plan.key}:missing_observations="
                    + ",".join(
                        value.isoformat(timespec="minutes")
                        for value in missing_observation_times
                    )
                )
            plan_contexts.append(
                TradePlanContext(
                    plan=plan,
                    observed_times=observed_times,
                    missing_observation_times=missing_observation_times,
                    target_quote=target_quote,
                    target_pool_keys=target_pool_keys,
                )
            )

        prior_decisions = tuple(
            decision
            for decision in self.context_store.list_prior_decisions(
                account_name, as_of
            )
            if decision.as_of.date() == as_of.date()
        )
        execution_history = tuple(
            ExecutedTradeContext(
                order_id=fill.order_id,
                filled_at=fill.filled_at,
                code=fill.code,
                side=fill.side,
                quantity=fill.quantity,
                price=fill.price,
                notional=fill.notional,
                cash_after=fill.cash_after,
                position_quantity_after=fill.position_quantity_after,
                sellable_after=fill.sellable_after,
            )
            for fill in PaperStore(self.store.database).list_fills(account_name)
            if fill.filled_at.date() == as_of.date()
            and fill.filled_at.astimezone(UTC) <= as_of.astimezone(UTC)
        )
        market_discovery = _market_discovery(snapshot.payload, quote_by_code)

        snapshot_digest = hashlib.sha256(
            json.dumps(
                snapshot.model_dump(mode="json"),
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        unique_blockers = tuple(dict.fromkeys(blockers))
        context = DecisionContext(
            market_snapshot_id=snapshot_digest,
            account=account,
            as_of=as_of,
            market_source=snapshot.source,
            cash=_money(account.cash),
            positions_market_value=positions_market_value,
            total_assets=total_assets,
            positions=tuple(position_contexts),
            theses=relevant_theses,
            pools=tuple(pool_contexts),
            trade_plans=tuple(plan_contexts),
            observation_history=observation_history,
            prior_decisions=prior_decisions,
            execution_history=execution_history,
            risk_exposures=tuple(risk_contexts),
            evidence=included_evidence,
            market_discovery=market_discovery,
            strategy_rules=STRATEGY_RULES,
            excluded_future_evidence_count=len(all_evidence) - len(included_evidence),
            blockers=unique_blockers,
            ready_for_judgment=not unique_blockers,
        )
        return self.context_store.record_context(context)


def extract_context_quotes(
    snapshot: MarketSnapshot,
) -> tuple[ContextQuote, ...]:
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
                    path=_path_from_session_quote(quote, snapshot.as_of),
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
                    name=instrument.get("name"),
                    observed_at=snapshot.as_of,
                    price=price,
                    pre_close=pre_close,
                    change_pct=(
                        ((price - pre_close) / pre_close * 100).quantize(PERCENT)
                        if pre_close
                        else Decimal("0")
                    ),
                    volume=volume,
                    amount=amount,
                    open=opening,
                    high=high,
                    low=low,
                    path=_path_from_bars(
                        bars,
                        pre_close,
                        price,
                        opening,
                        high,
                        low,
                    ),
                )
            )
        return tuple(quotes)

    raise ContextError(f"unsupported market snapshot source: {snapshot.source}")


def _require_observable(
    label: str, observed_at: datetime, as_of: datetime, *, source: str = ""
) -> None:
    if observed_at.tzinfo is None:
        raise ContextError(f"{label} timestamp must include a timezone")
    if source == "astock-replay":
        return
    if observed_at.astimezone(UTC) > as_of.astimezone(UTC):
        raise ContextError(f"{label} was updated after the market snapshot")


def _require_unique_codes(quotes: list[ContextQuote]) -> None:
    codes = [quote.code for quote in quotes]
    if len(codes) != len(set(codes)):
        raise ContextError("market snapshot contains duplicate stock codes")


def _path_from_session_quote(
    quote: LiveQuote, observed_at: datetime
) -> PricePathContext:
    price = _decimal(quote.price)
    pre_close = _decimal(quote.pre_close)
    opening = _decimal(quote.open)
    high = _decimal(quote.high)
    low = _decimal(quote.low)
    limit_price = pre_close * Decimal("1.095") if pre_close else None
    return PricePathContext(
        source="session_quote",
        bar_count=0,
        latest_bar_time=observed_at,
        change_from_open_pct=_relative_pct(price - opening, opening),
        rebound_from_low_pct=_relative_pct(price - low, low),
        drawdown_from_high_pct=_relative_pct(price - high, high),
        ten_minute_change_pct=None,
        dipped_below_pre_close=bool(pre_close and low < pre_close),
        recovered_above_pre_close=bool(
            pre_close and low < pre_close and price >= pre_close
        ),
        limit_up_like=bool(limit_price and price >= limit_price),
        one_word_limit_like=bool(
            limit_price
            and opening >= limit_price
            and low >= limit_price
            and high >= limit_price
        ),
    )


def _path_from_bars(
    bars: tuple[MinuteBar, ...],
    pre_close: Decimal,
    price: Decimal,
    opening: Decimal,
    high: Decimal,
    low: Decimal,
) -> PricePathContext:
    if not bars:
        return PricePathContext(
            source="minute_bars",
            bar_count=0,
            change_from_open_pct=Decimal("0"),
            rebound_from_low_pct=Decimal("0"),
            drawdown_from_high_pct=Decimal("0"),
            ten_minute_change_pct=None,
            dipped_below_pre_close=False,
            recovered_above_pre_close=False,
            limit_up_like=False,
            one_word_limit_like=False,
        )
    closes = tuple(_decimal(bar.close) for bar in bars)
    lows = tuple(_decimal(bar.low) for bar in bars)
    limit_price = pre_close * Decimal("1.095") if pre_close else None
    comparison_close = closes[-11] if len(closes) >= 11 else None
    dipped = bool(pre_close and any(value < pre_close for value in lows))
    recovered = bool(
        pre_close
        and dipped
        and price >= pre_close
        and any(value >= pre_close for value in closes)
    )
    one_word = bool(
        limit_price
        and all(
            _decimal(bar.open) >= limit_price
            and _decimal(bar.high) >= limit_price
            and _decimal(bar.low) >= limit_price
            and _decimal(bar.close) >= limit_price
            for bar in bars
        )
    )
    return PricePathContext(
        source="minute_bars",
        bar_count=len(bars),
        first_bar_time=bars[0].time,
        latest_bar_time=bars[-1].time,
        change_from_open_pct=_relative_pct(price - opening, opening),
        rebound_from_low_pct=_relative_pct(price - low, low),
        drawdown_from_high_pct=_relative_pct(price - high, high),
        ten_minute_change_pct=(
            _relative_pct(price - comparison_close, comparison_close)
            if comparison_close is not None
            else None
        ),
        dipped_below_pre_close=dipped,
        recovered_above_pre_close=recovered,
        limit_up_like=bool(limit_price and price >= limit_price),
        one_word_limit_like=one_word,
    )


def _pool_signals(
    members,
    quote_by_code: dict[str, ContextQuote],
) -> tuple[tuple[PoolMemberSignalContext, ...], PoolMetricsContext]:
    available = [
        (member, quote_by_code[member.code])
        for member in members
        if member.code in quote_by_code
    ]
    change_order = {
        member.code: rank
        for rank, (member, _) in enumerate(
            sorted(
                available,
                key=lambda item: (item[1].change_pct, item[1].amount),
                reverse=True,
            ),
            start=1,
        )
    }
    amount_order = {
        member.code: rank
        for rank, (member, _) in enumerate(
            sorted(
                available,
                key=lambda item: (item[1].amount, item[1].change_pct),
                reverse=True,
            ),
            start=1,
        )
    }
    signals = tuple(
        PoolMemberSignalContext(
            code=member.code,
            name=quote.name,
            role=member.role,
            relationship=member.relationship,
            tradable=member.tradable,
            causal_chain=member.causal_chain,
            change_pct=quote.change_pct,
            amount=quote.amount,
            change_rank=change_order[member.code],
            amount_rank=amount_order[member.code],
            is_up=quote.change_pct > 0,
            is_strong=quote.change_pct >= STRONG_PCT,
            is_limit_up=quote.change_pct >= LIMIT_UP_PCT,
            path=quote.path or _empty_path(),
        )
        for member, quote in sorted(available, key=lambda item: item[0].code)
    )
    up_count = sum(signal.is_up for signal in signals)
    down_count = sum(signal.change_pct < 0 for signal in signals)
    flat_count = len(signals) - up_count - down_count
    tradable_signals = tuple(signal for signal in signals if signal.tradable)
    leaders = tuple(
        signal.code
        for signal in sorted(signals, key=lambda item: item.change_rank)[:3]
    )
    metrics = PoolMetricsContext(
        registered_count=len(members),
        quoted_count=len(signals),
        up_count=up_count,
        down_count=down_count,
        flat_count=flat_count,
        strong_count=sum(signal.is_strong for signal in signals),
        limit_up_count=sum(signal.is_limit_up for signal in signals),
        tradable_count=len(tradable_signals),
        tradable_up_count=sum(signal.is_up for signal in tradable_signals),
        breadth_pct=(
            (Decimal(up_count) / len(signals) * 100).quantize(PERCENT)
            if signals
            else Decimal("0")
        ),
        leader_codes=leaders,
    )
    return signals, metrics


def _select_observation_history(prior_records, plans):
    if not prior_records:
        return ()
    desired_times = {
        value for plan in plans for value in plan.observation_times
    }
    selected = [
        record
        for record in prior_records
        if record.context.as_of.time().replace(tzinfo=None) in desired_times
    ]
    selected.extend(prior_records[-4:])
    by_id = {record.id: record for record in selected}
    return tuple(sorted(by_id.values(), key=lambda record: record.context.as_of))


def _compact_observation(context: DecisionContext) -> HistoricalObservationContext:
    positions = tuple(
        HistoricalPositionObservation(
            code=item.position.code,
            change_pct=item.quote.change_pct,
            price=item.quote.price,
            path=item.quote.path or _empty_path(),
        )
        for item in context.positions
    )
    pools = tuple(
        HistoricalPoolObservation(
            pool_key=item.pool.key,
            monitoring_status=item.pool.monitoring_status,
            metrics=item.metrics or _empty_pool_metrics(len(item.members)),
            member_signals=item.member_signals,
        )
        for item in context.pools
    )
    return HistoricalObservationContext(
        as_of=context.as_of,
        positions=positions,
        pools=pools,
    )


def _market_discovery(
    payload: dict, quote_by_code: dict[str, ContextQuote]
) -> MarketDiscoveryContext:
    raw = payload.get("market_discovery")
    if not isinstance(raw, dict):
        return MarketDiscoveryContext(
            coverage_mode="registered_universe",
            scanned_codes=tuple(sorted(quote_by_code)),
            missing_capabilities=(
                "full_market_candidates",
                "sector_rank",
                "limit_up_events",
                "index_context",
            ),
        )
    return MarketDiscoveryContext(
        coverage_mode=raw.get("coverage_mode", "candidate_universe"),
        scanned_codes=tuple(raw.get("scanned_codes", sorted(quote_by_code))),
        universe_count=raw.get("universe_count"),
        scanned_count=raw.get("scanned_count"),
        missing_quote_count=raw.get("missing_quote_count"),
        failed_batches=raw.get("failed_batches"),
        candidate_codes=tuple(raw.get("candidate_codes", ())),
        candidates=tuple(
            _market_candidate(row) for row in raw.get("candidates", ())
        ),
        top_amount=tuple(
            _market_candidate(row) for row in raw.get("top_amount", ())
        ),
        sector_leaders=tuple(
            _sector_leader(row) for row in raw.get("sector_leaders", ())
        ),
        indices=tuple(_market_index(row) for row in raw.get("indices", ())),
        limit_up_codes=tuple(raw.get("limit_up_codes", ())),
        missing_capabilities=tuple(raw.get("missing_capabilities", ())),
    )


def _market_candidate(row: object) -> MarketCandidateContext:
    if not isinstance(row, dict):
        raise ContextError("market discovery candidate must be an object")
    return MarketCandidateContext(
        code=str(row.get("code", "")),
        name=str(row.get("name", "")),
        industry=row.get("industry") or None,
        sector=row.get("sector") or None,
        business=row.get("business") or None,
        price=_decimal(row.get("price", 0)),
        pre_close=_decimal(row.get("pre_close", 0)),
        change_pct=_decimal(row.get("change_pct", 0)),
        amount=_decimal(row.get("amount", 0)),
        low=_decimal(row.get("low", 0)),
        rebound_pct=_decimal(row.get("rebound_pct", 0)),
        limit_up=bool(row.get("limit_up", False)),
        reasons=tuple(str(value) for value in row.get("reasons", ())),
    )


def _sector_leader(row: object) -> SectorLeaderContext:
    if not isinstance(row, dict):
        raise ContextError("market discovery sector leader must be an object")
    return SectorLeaderContext(
        code=str(row.get("code", "")),
        name=str(row.get("name", "")),
        block_type=row.get("block_type"),
        change_pct=_decimal(row.get("change_pct", 0)),
        amount=_decimal(row.get("amount", 0)),
        limit_up_count=int(row.get("limit_up_count", 0)),
    )


def _market_index(row: object) -> MarketIndexContext:
    if not isinstance(row, dict):
        raise ContextError("market discovery index must be an object")
    return MarketIndexContext(
        code=str(row.get("code", "")),
        name=str(row.get("name", "")),
        price=_decimal(row.get("price", 0)),
        pre_close=_decimal(row.get("pre_close", 0)),
        change_pct=_decimal(row.get("change_pct", 0)),
        amount=_decimal(row.get("amount", 0)),
    )


def _empty_path() -> PricePathContext:
    return PricePathContext(
        source="session_quote",
        bar_count=0,
        dipped_below_pre_close=False,
        recovered_above_pre_close=False,
        limit_up_like=False,
        one_word_limit_like=False,
    )


def _empty_pool_metrics(registered_count: int) -> PoolMetricsContext:
    return PoolMetricsContext(
        registered_count=registered_count,
        quoted_count=0,
        up_count=0,
        down_count=0,
        flat_count=0,
        strong_count=0,
        limit_up_count=0,
        tradable_count=0,
        tradable_up_count=0,
        breadth_pct=Decimal("0"),
        leader_codes=(),
    )


def _relative_pct(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return (numerator / denominator * 100).quantize(PERCENT)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)
