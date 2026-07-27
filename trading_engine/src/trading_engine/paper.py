from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from trading_engine.context import DecisionContextBuilder
from trading_engine.context_models import DecisionContext, DecisionContextRecord
from trading_engine.context_store import ContextStore
from trading_engine.errors import PaperTradingError
from trading_engine.models import JudgmentProposal, JudgmentRecord
from trading_engine.paper_models import PaperExecutionResult, PaperPolicy, PaperRuleCheck
from trading_engine.paper_store import PaperStore
from trading_engine.storage import ReplayStore


CENT = Decimal("0.01")


@dataclass
class _SimPosition:
    code: str
    name: str
    quantity: int
    sellable: int
    average_cost_cents: int
    bought_on: date
    created_at: str


class PaperBroker:
    def __init__(
        self,
        store: ReplayStore,
        context_store: ContextStore,
        paper_store: PaperStore,
        policy: PaperPolicy | None = None,
    ) -> None:
        self.store = store
        self.context_store = context_store
        self.paper_store = paper_store
        self.policy = policy or PaperPolicy()

    def execute_judgment(
        self, account_name: str = "paper", judgment_id: str | None = None
    ) -> PaperExecutionResult:
        judgment = (
            self.store.get_judgment(judgment_id)
            if judgment_id is not None
            else self.store.latest_judgment()
        )
        if judgment is None:
            raise PaperTradingError("no judgment exists to execute")
        existing = self.paper_store.find_execution(account_name, judgment.id)
        if existing is not None:
            return existing
        context_record = self._validate_input(judgment, account_name)

        market_record = self.store.get_market_snapshot(judgment.snapshot_id)
        rebuilt = DecisionContextBuilder(self.store, self.context_store).build(
            market_record, account_name
        )
        if rebuilt.fingerprint != context_record.fingerprint:
            raise PaperTradingError(
                "decision context is stale; capture and analyze a fresh context"
            )

        try:
            execution_id = self._execute_transaction(
                account_name, judgment, context_record
            )
        except sqlite3.Error as exc:
            raise PaperTradingError(
                f"paper execution transaction failed: {exc}"
            ) from exc
        return self.paper_store.get_execution(execution_id)

    def _validate_input(
        self, judgment: JudgmentRecord, account_name: str
    ) -> DecisionContextRecord:
        if judgment.status != "completed" or judgment.report is None:
            raise PaperTradingError("only completed judgments can be executed")
        context_id = judgment.input_context.decision_context_id
        fingerprint = judgment.input_context.decision_context_fingerprint
        if context_id is None or fingerprint is None:
            raise PaperTradingError(
                "paper execution requires a judgment with full decision context"
            )
        context_record = self.context_store.get_context(context_id)
        context = context_record.context
        if context_record.fingerprint != fingerprint:
            raise PaperTradingError("judgment context fingerprint does not match")
        if context.account.name != account_name.strip():
            raise PaperTradingError(
                f"judgment belongs to account {context.account.name}, "
                f"not {account_name.strip()}"
            )
        if not context.ready_for_judgment:
            raise PaperTradingError("blocked decision context cannot be executed")
        if (
            context.market_snapshot_id != judgment.snapshot_id
            or judgment.report.snapshot_id != judgment.snapshot_id
            or judgment.report.as_of != context.as_of
        ):
            raise PaperTradingError("judgment, context, and market snapshot do not match")
        return context_record

    def _execute_transaction(
        self,
        account_name: str,
        judgment: JudgmentRecord,
        context_record: DecisionContextRecord,
    ) -> str:
        execution_id = uuid4().hex
        context = context_record.context
        created_at = datetime.now(UTC)
        trade_date = context.as_of.date()
        quotes = _quote_prices(context)
        tradable_codes = {
            member.code
            for pool_context in context.pools
            for member in pool_context.members
            if member.tradable
        }
        risk_limits = {
            exposure.factor.key: (
                set(exposure.position_codes),
                exposure.factor.max_exposure_pct,
            )
            for exposure in context.risk_exposures
            if exposure.factor.active
        }

        with self.paper_store.transaction() as connection:
            existing = connection.execute(
                """
                SELECT paper_executions.id
                FROM paper_executions
                JOIN accounts ON accounts.id = paper_executions.account_id
                WHERE accounts.name = ? AND paper_executions.judgment_id = ?
                """,
                (account_name.strip(), judgment.id),
            ).fetchone()
            if existing is not None:
                return existing["id"]

            account = connection.execute(
                "SELECT * FROM accounts WHERE name = ?", (account_name.strip(),)
            ).fetchone()
            if account is None:
                raise PaperTradingError(
                    f"paper account does not exist: {account_name.strip()}"
                )
            position_rows = connection.execute(
                "SELECT * FROM positions WHERE account_id = ? ORDER BY code",
                (account["id"],),
            ).fetchall()
            _assert_core_context_fresh(account, position_rows, context)
            original = {
                row["code"]: _position_from_row(row) for row in position_rows
            }
            simulated = {
                code: _copy_position(position) for code, position in original.items()
            }
            cash_cents = account["cash_cents"]

            connection.execute(
                """
                INSERT INTO paper_executions (
                    id, account_id, judgment_id, context_id, snapshot_id,
                    policy_json, status, created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'completed', ?, ?)
                """,
                (
                    execution_id,
                    account["id"],
                    judgment.id,
                    context_record.id,
                    judgment.snapshot_id,
                    self.policy.model_dump_json(),
                    created_at.isoformat(),
                    created_at.isoformat(),
                ),
            )

            assert judgment.report is not None
            filled_any = False
            for index, proposal in enumerate(judgment.report.proposals):
                if proposal.action in {"WAIT", "RESEARCH"}:
                    _insert_event(
                        connection,
                        execution_id,
                        judgment.id,
                        index,
                        proposal,
                        "skipped",
                        trade_date,
                        proposal.reason,
                        None,
                        created_at,
                    )
                    continue

                price = quotes.get(proposal.code)
                if price is None:
                    raise PaperTradingError(
                        f"decision context is missing quote: {proposal.code}"
                    )
                assert proposal.quantity is not None
                price_cents = _price_to_cents(price)
                notional_cents = price_cents * proposal.quantity
                order_id = uuid4().hex
                checks = self._checks(
                    connection=connection,
                    account=account,
                    proposal=proposal,
                    trade_date=trade_date,
                    cash_cents=cash_cents,
                    price_cents=price_cents,
                    simulated=simulated,
                    quotes=quotes,
                    tradable_codes=tradable_codes,
                    risk_limits=risk_limits,
                )
                rejected = tuple(check for check in checks if not check.passed)
                status = "rejected" if rejected else "filled"
                rejection_reason = (
                    "; ".join(check.message for check in rejected)
                    if rejected
                    else None
                )
                connection.execute(
                    """
                    INSERT INTO paper_orders (
                        id, execution_id, judgment_id, proposal_index,
                        account_id, snapshot_id, context_id, code, side,
                        quantity, price_cents, notional_cents, trade_date,
                        status, rejection_reason, proposal_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        order_id,
                        execution_id,
                        judgment.id,
                        index,
                        account["id"],
                        judgment.snapshot_id,
                        context_record.id,
                        proposal.code,
                        proposal.action,
                        proposal.quantity,
                        price_cents,
                        notional_cents,
                        trade_date.isoformat(),
                        status,
                        rejection_reason,
                        proposal.model_dump_json(),
                        created_at.isoformat(),
                    ),
                )
                for ordinal, check in enumerate(checks):
                    connection.execute(
                        """
                        INSERT INTO paper_rule_checks (
                            order_id, ordinal, rule_name, passed, message
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            order_id,
                            ordinal,
                            check.name,
                            int(check.passed),
                            check.message,
                        ),
                    )

                if rejected:
                    _insert_event(
                        connection,
                        execution_id,
                        judgment.id,
                        index,
                        proposal,
                        "rejected",
                        trade_date,
                        rejection_reason or "rejected",
                        order_id,
                        created_at,
                    )
                    continue

                cash_cents = _insert_fill_and_apply(
                    connection=connection,
                    account_id=account["id"],
                    order_id=order_id,
                    proposal=proposal,
                    price_cents=price_cents,
                    cash_cents=cash_cents,
                    simulated=simulated,
                    trade_date=trade_date,
                    market_time=context.as_of,
                    created_at=created_at,
                )
                filled_any = True
                _insert_event(
                    connection,
                    execution_id,
                    judgment.id,
                    index,
                    proposal,
                    "filled",
                    trade_date,
                    proposal.reason,
                    order_id,
                    created_at,
                )

            if filled_any:
                _persist_portfolio(
                    connection,
                    account["id"],
                    cash_cents,
                    original,
                    simulated,
                    created_at,
                )
        return execution_id

    def _checks(
        self,
        connection: sqlite3.Connection,
        account: sqlite3.Row,
        proposal: JudgmentProposal,
        trade_date: date,
        cash_cents: int,
        price_cents: int,
        simulated: dict[str, _SimPosition],
        quotes: dict[str, Decimal],
        tradable_codes: set[str],
        risk_limits: dict[str, tuple[set[str], Decimal]],
    ) -> tuple[PaperRuleCheck, ...]:
        assert proposal.quantity is not None
        duplicate = connection.execute(
            """
            SELECT 1 FROM paper_orders
            WHERE account_id = ? AND code = ? AND side = ?
              AND trade_date = ? AND status = 'filled'
            LIMIT 1
            """,
            (
                account["id"],
                proposal.code,
                proposal.action,
                trade_date.isoformat(),
            ),
        ).fetchone()
        checks = [
            _check(
                "duplicate_signal",
                duplicate is None,
                "no filled signal exists for the same code, side, and trading date",
                "same-side signal already filled on this trading date",
            )
        ]
        if proposal.action == "BUY":
            notional_cents = price_cents * proposal.quantity
            post_cash = cash_cents - notional_cents
            post_positions = {
                code: _copy_position(position)
                for code, position in simulated.items()
            }
            existing = post_positions.get(proposal.code)
            if existing is None:
                post_positions[proposal.code] = _SimPosition(
                    code=proposal.code,
                    name=proposal.code,
                    quantity=proposal.quantity,
                    sellable=0,
                    average_cost_cents=price_cents,
                    bought_on=trade_date,
                    created_at="",
                )
            else:
                existing.quantity += proposal.quantity
            total_assets, gross_value, code_value = _portfolio_values(
                post_cash, post_positions, quotes, proposal.code
            )
            single_pct = _percentage(code_value, total_assets)
            gross_pct = _percentage(gross_value, total_assets)
            checks.extend(
                (
                    _check(
                        "main_board_buy",
                        is_main_board_code(proposal.code),
                        "code is in the Shanghai/Shenzhen main-board range",
                        "BUY is limited to Shanghai/Shenzhen main-board codes",
                    ),
                    _check(
                        "buy_lot",
                        proposal.quantity % self.policy.buy_lot_size == 0,
                        f"quantity is a multiple of {self.policy.buy_lot_size}",
                        f"BUY quantity must be a multiple of {self.policy.buy_lot_size}",
                    ),
                    _check(
                        "account_cooldown",
                        not bool(account["cooldown"]),
                        "account cooldown is disabled",
                        "BUY is blocked while account cooldown is enabled",
                    ),
                    _check(
                        "tradable_pool",
                        proposal.code in tradable_codes,
                        "code is an explicitly tradable active-pool member",
                        "BUY code is not an explicitly tradable active-pool member",
                    ),
                    _check(
                        "cash",
                        post_cash >= 0,
                        "cash covers the simulated notional",
                        "insufficient cash for simulated notional",
                    ),
                    _check(
                        "single_position_limit",
                        single_pct <= self.policy.max_single_position_pct,
                        f"post-trade single position is {single_pct}%",
                        f"post-trade single position {single_pct}% exceeds "
                        f"{self.policy.max_single_position_pct}%",
                    ),
                    _check(
                        "gross_exposure_limit",
                        gross_pct <= self.policy.max_gross_exposure_pct,
                        f"post-trade gross exposure is {gross_pct}%",
                        f"post-trade gross exposure {gross_pct}% exceeds "
                        f"{self.policy.max_gross_exposure_pct}%",
                    ),
                )
            )
            for factor_key, (factor_codes, limit) in risk_limits.items():
                if proposal.code not in factor_codes:
                    continue
                exposure_value = sum(
                    _price_to_cents(quotes[code]) * post_positions[code].quantity
                    for code in factor_codes
                    if code in post_positions
                )
                exposure_pct = _percentage(exposure_value, total_assets)
                checks.append(
                    _check(
                        f"risk_exposure:{factor_key}",
                        exposure_pct <= limit,
                        f"post-trade {factor_key} exposure is {exposure_pct}%",
                        f"post-trade {factor_key} exposure {exposure_pct}% "
                        f"exceeds {limit}%",
                    )
                )
        else:
            position = simulated.get(proposal.code)
            position_quantity = position.quantity if position else 0
            sellable = position.sellable if position else 0
            lot_valid = (
                proposal.quantity % self.policy.buy_lot_size == 0
                or proposal.quantity == position_quantity
            )
            checks.extend(
                (
                    _check(
                        "position_exists",
                        position is not None,
                        "position exists",
                        "SELL position does not exist",
                    ),
                    _check(
                        "t_plus_one",
                        position is not None and proposal.quantity <= sellable,
                        "quantity is within the T+1 sellable balance",
                        f"SELL quantity exceeds sellable balance {sellable}",
                    ),
                    _check(
                        "sell_lot",
                        lot_valid,
                        "quantity is a board lot or closes the full position",
                        "SELL quantity must be a board lot or the full position",
                    ),
                )
            )
        return tuple(checks)


def is_main_board_code(code: str) -> bool:
    return code.startswith(
        ("600", "601", "603", "605", "000", "001", "002", "003")
    )


def _assert_core_context_fresh(
    account: sqlite3.Row,
    position_rows: list[sqlite3.Row],
    context: DecisionContext,
) -> None:
    if (
        account["id"] != context.account.id
        or account["cash_cents"] != _money_to_cents(context.account.cash)
        or bool(account["cooldown"]) != context.account.cooldown
    ):
        raise PaperTradingError("account changed after decision context was captured")
    expected = {item.position.code: item.position for item in context.positions}
    actual = {row["code"]: row for row in position_rows}
    if set(actual) != set(expected):
        raise PaperTradingError("positions changed after decision context was captured")
    for code, position in expected.items():
        row = actual[code]
        if (
            row["name"] != position.name
            or row["quantity"] != position.quantity
            or row["sellable_quantity"] != position.sellable_quantity
            or row["average_cost_cents"] != _money_to_cents(position.average_cost)
            or row["bought_on"] != position.bought_on.isoformat()
        ):
            raise PaperTradingError(
                f"position {code} changed after decision context was captured"
            )


def _insert_fill_and_apply(
    connection: sqlite3.Connection,
    account_id: str,
    order_id: str,
    proposal: JudgmentProposal,
    price_cents: int,
    cash_cents: int,
    simulated: dict[str, _SimPosition],
    trade_date: date,
    market_time: datetime,
    created_at: datetime,
) -> int:
    assert proposal.quantity is not None
    position = simulated.get(proposal.code)
    before_quantity = position.quantity if position else 0
    before_sellable = position.sellable if position else 0
    before_cost = position.average_cost_cents if position else None
    notional_cents = price_cents * proposal.quantity
    cash_before = cash_cents

    if proposal.action == "BUY":
        cash_cents -= notional_cents
        if position is None:
            position = _SimPosition(
                code=proposal.code,
                name=proposal.code,
                quantity=proposal.quantity,
                sellable=0,
                average_cost_cents=price_cents,
                bought_on=trade_date,
                created_at=created_at.isoformat(),
            )
            simulated[proposal.code] = position
        else:
            total_cost = (
                position.average_cost_cents * position.quantity + notional_cents
            )
            position.quantity += proposal.quantity
            position.average_cost_cents = _rounded_average_cost(
                total_cost, position.quantity
            )
            position.bought_on = trade_date
    else:
        assert position is not None
        cash_cents += notional_cents
        position.quantity -= proposal.quantity
        position.sellable -= proposal.quantity
        if position.quantity == 0:
            del simulated[proposal.code]

    after = simulated.get(proposal.code)
    after_quantity = after.quantity if after else 0
    after_sellable = after.sellable if after else 0
    after_cost = after.average_cost_cents if after else None
    connection.execute(
        """
        INSERT INTO paper_fills (
            id, order_id, account_id, code, side, quantity,
            price_cents, notional_cents, cash_before_cents,
            cash_after_cents, position_quantity_before,
            position_quantity_after, sellable_before, sellable_after,
            average_cost_before_cents, average_cost_after_cents,
            filled_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid4().hex,
            order_id,
            account_id,
            proposal.code,
            proposal.action,
            proposal.quantity,
            price_cents,
            notional_cents,
            cash_before,
            cash_cents,
            before_quantity,
            after_quantity,
            before_sellable,
            after_sellable,
            before_cost,
            after_cost,
            market_time.isoformat(),
            created_at.isoformat(),
        ),
    )
    return cash_cents


def _persist_portfolio(
    connection: sqlite3.Connection,
    account_id: str,
    cash_cents: int,
    original: dict[str, _SimPosition],
    simulated: dict[str, _SimPosition],
    updated_at: datetime,
) -> None:
    timestamp = updated_at.isoformat()
    connection.execute(
        "UPDATE accounts SET cash_cents = ?, updated_at = ? WHERE id = ?",
        (cash_cents, timestamp, account_id),
    )
    for code in sorted(set(original) | set(simulated)):
        position = simulated.get(code)
        if position is None:
            connection.execute(
                "DELETE FROM position_theses WHERE account_id = ? AND code = ?",
                (account_id, code),
            )
            connection.execute(
                """
                DELETE FROM position_risk_factors
                WHERE account_id = ? AND code = ?
                """,
                (account_id, code),
            )
            connection.execute(
                "DELETE FROM positions WHERE account_id = ? AND code = ?",
                (account_id, code),
            )
            continue
        connection.execute(
            """
            INSERT INTO positions (
                account_id, code, name, quantity, sellable_quantity,
                average_cost_cents, bought_on, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(account_id, code) DO UPDATE SET
                name = excluded.name,
                quantity = excluded.quantity,
                sellable_quantity = excluded.sellable_quantity,
                average_cost_cents = excluded.average_cost_cents,
                bought_on = excluded.bought_on,
                updated_at = excluded.updated_at
            """,
            (
                account_id,
                position.code,
                position.name,
                position.quantity,
                position.sellable,
                position.average_cost_cents,
                position.bought_on.isoformat(),
                position.created_at or timestamp,
                timestamp,
            ),
        )


def _insert_event(
    connection: sqlite3.Connection,
    execution_id: str,
    judgment_id: str,
    proposal_index: int,
    proposal: JudgmentProposal,
    status: str,
    trade_date: date,
    reason: str,
    order_id: str | None,
    created_at: datetime,
) -> None:
    connection.execute(
        """
        INSERT INTO paper_decision_events (
            id, execution_id, judgment_id, proposal_index, code,
            action, status, trade_date, reason, order_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            uuid4().hex,
            execution_id,
            judgment_id,
            proposal_index,
            proposal.code,
            proposal.action,
            status,
            trade_date.isoformat(),
            reason,
            order_id,
            created_at.isoformat(),
        ),
    )


def _portfolio_values(
    cash_cents: int,
    positions: dict[str, _SimPosition],
    quotes: dict[str, Decimal],
    target_code: str,
) -> tuple[int, int, int]:
    gross = 0
    target = 0
    for code, position in positions.items():
        if code not in quotes:
            raise PaperTradingError(f"decision context is missing quote: {code}")
        value = _price_to_cents(quotes[code]) * position.quantity
        gross += value
        if code == target_code:
            target = value
    return cash_cents + gross, gross, target


def _quote_prices(context: DecisionContext) -> dict[str, Decimal]:
    prices = {
        item.quote.code: item.quote.price for item in context.positions
    }
    for pool in context.pools:
        for quote in pool.quotes:
            prices.setdefault(quote.code, quote.price)
    return prices


def _position_from_row(row: sqlite3.Row) -> _SimPosition:
    return _SimPosition(
        code=row["code"],
        name=row["name"],
        quantity=row["quantity"],
        sellable=row["sellable_quantity"],
        average_cost_cents=row["average_cost_cents"],
        bought_on=date.fromisoformat(row["bought_on"]),
        created_at=row["created_at"],
    )


def _copy_position(position: _SimPosition) -> _SimPosition:
    return _SimPosition(**position.__dict__)


def _check(
    name: str,
    passed: bool,
    success: str,
    failure: str,
) -> PaperRuleCheck:
    return PaperRuleCheck(
        name=name,
        passed=passed,
        message=success if passed else failure,
    )


def _percentage(value: int, total: int) -> Decimal:
    if total <= 0:
        return Decimal("100") if value > 0 else Decimal("0")
    return (Decimal(value) / Decimal(total) * 100).quantize(Decimal("0.0001"))


def _price_to_cents(value: Decimal) -> int:
    rounded = value.quantize(CENT, rounding=ROUND_HALF_UP)
    cents = int(rounded * 100)
    if cents <= 0:
        raise PaperTradingError("paper fill price must be greater than zero")
    return cents


def _money_to_cents(value: Decimal) -> int:
    return int(value * 100)


def _rounded_average_cost(total_cost_cents: int, quantity: int) -> int:
    return int(
        (Decimal(total_cost_cents) / quantity).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )
