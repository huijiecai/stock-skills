"""core·钱包与账本(平台通用件):模拟账户,PG 持久化,行级 portfolio_id 隔离。

- 金额一律用"分"(int cents),避免浮点误差
- 现金按组合挂 wallets(portfolio_id, cash_cents, initial_cents)
- 持仓含 sellable(可卖数量)与 bought_on(买入日):T+1 依据
- 每笔买卖记 fill(before/after + run_id 归因,可审计对账)
  fill 的主人是组合(portfolio_id 必填:期初/出入金等非执行流水也成立);
  run_id 可空(行为归因:哪场下的单)
- portfolio_id 参数缺省 = 当前组合(core.context,engine 唯一注入)
- schema 参数仅测试隔离用
"""
from trader.core.context import current_portfolio, current_run, current_user
from trader.core.db import _connect, ensure_once

INITIAL_CASH = 100_000_00  # 初始资金 ¥100,000(单位:分)


class WalletError(Exception):
    """钱包操作失败(现金不足 / 可卖不足 / 组合未开局等)。"""


def _eff(portfolio_id: int | None) -> int:
    return portfolio_id if portfolio_id is not None else current_portfolio()


class Wallet:
    """模拟钱包:单 agent 顺序使用,PG 持久化,行级组合隔离。"""

    def __init__(self, schema: str = "public", initial_cash: int = INITIAL_CASH) -> None:
        self.schema = schema
        self.initial_cash = initial_cash
        ensure_once(f"ledger:{schema}", self._init_db)

    # ── 查询 ────────────────────────────────────────────

    def cash(self, portfolio_id: int | None = None) -> int:
        """现金(分)。"""
        with _connect(self.schema) as conn:
            return self._cash(conn, _eff(portfolio_id))

    def positions(self, portfolio_id: int | None = None) -> list[dict]:
        """全部持仓(quantity>0),avg_cost 转为元(展示用)。"""
        p = _eff(portfolio_id)
        with _connect(self.schema) as conn:
            rows = conn.execute(
                "SELECT code, name, quantity, sellable, avg_cost_cents, bought_on"
                " FROM positions WHERE quantity > 0 AND portfolio_id=%s ORDER BY code", (p,)
            ).fetchall()
        return [
            {"code": r["code"], "name": r["name"], "quantity": r["quantity"],
             "sellable": r["sellable"], "avg_cost": r["avg_cost_cents"] / 100,
             "bought_on": r["bought_on"]}
            for r in rows
        ]

    def position(self, code: str, portfolio_id: int | None = None) -> dict | None:
        """单只持仓,无则 None。"""
        with _connect(self.schema) as conn:
            r = conn.execute(
                "SELECT * FROM positions WHERE code = %s AND portfolio_id = %s",
                (code, _eff(portfolio_id)),
            ).fetchone()
        if r is None or r["quantity"] == 0:
            return None
        return {"code": r["code"], "name": r["name"], "quantity": r["quantity"],
                "sellable": r["sellable"], "avg_cost": r["avg_cost_cents"] / 100,
                "bought_on": r["bought_on"]}

    def fills(self, portfolio_id: int | None = None) -> list[dict]:
        """全部成交记录(含决策留痕 reason + run_id 归因,复盘用)。"""
        with _connect(self.schema) as conn:
            return conn.execute(
                "SELECT * FROM fills WHERE portfolio_id=%s ORDER BY id",
                (_eff(portfolio_id),)).fetchall()

    # ── 交易(事务 + fill)───────────────────────────────

    def buy(self, code: str, quantity: int, price: float, on: str | None = None,
            name: str = "", reason: str = "", trade_time: str = "",
            portfolio_id: int | None = None, run_id: int | None = None) -> dict:
        """买入:扣现金、加仓(加权成本)、记 fill(含决策留痕 + run_id)。
        on=买入日(T+1 依据);trade_time=成交时点(回放 "20260814 09:35" 或真实时间)。"""
        from datetime import date as _d, datetime as _dt

        p = _eff(portfolio_id)
        rid = run_id if run_id is not None else current_run()
        on = on or _d.today().isoformat()
        price_c = round(price * 100)
        notional = price_c * quantity
        now = _dt.now().isoformat(timespec="seconds")
        tt = trade_time or now
        with _connect(self.schema) as conn:
            try:
                cash_before = self._cash(conn, p)
                if cash_before < notional:
                    raise WalletError(
                        f"现金不足:需 ¥{notional / 100:,.2f},只有 ¥{cash_before / 100:,.2f}"
                    )
                row = conn.execute(
                    "SELECT quantity, avg_cost_cents FROM positions"
                    " WHERE code = %s AND portfolio_id = %s", (code, p)
                ).fetchone()
                if row and row["quantity"] > 0:
                    old_qty, old_cost = row["quantity"], row["avg_cost_cents"]
                    new_qty = old_qty + quantity
                    new_cost = (old_qty * old_cost + notional) // new_qty
                    conn.execute(
                        "UPDATE positions SET quantity=%s, avg_cost_cents=%s, bought_on=%s,"
                        " name=CASE WHEN %s!='' THEN %s ELSE name END"
                        " WHERE code=%s AND portfolio_id=%s",
                        (new_qty, new_cost, on, name, name, code, p),
                    )
                    pos_before = old_qty
                else:
                    conn.execute(
                        "INSERT INTO positions(portfolio_id, code, name, quantity, sellable,"
                        " avg_cost_cents, bought_on) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                        (p, code, name, quantity, 0, price_c, on),
                    )
                    pos_before = 0
                cash_after = cash_before - notional
                conn.execute(
                    "UPDATE wallets SET cash_cents=%s WHERE portfolio_id=%s", (cash_after, p))
                conn.execute(
                    "INSERT INTO fills(portfolio_id, run_id, user_id, code, side, quantity,"
                    " price_cents, cash_before_cents, cash_after_cents, position_before,"
                    " position_after, created_at, reason, name, trade_time)"
                    " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (p, rid, current_user(), code, "BUY", quantity, price_c, cash_before,
                     cash_after, pos_before, pos_before + quantity, now, reason, name, tt),
                )
            except Exception:
                raise  # with 块退出时自动 rollback
        return {"code": code, "side": "BUY", "quantity": quantity, "price": price,
                "cash_after": cash_after / 100, "position_after": pos_before + quantity}

    def sell(self, code: str, quantity: int, price: float, reason: str = "",
             trade_time: str = "", portfolio_id: int | None = None,
             run_id: int | None = None) -> dict:
        """卖出:校验可卖(T+1)、加现金、减仓(成本不变)、记 fill(含决策留痕)。"""
        from datetime import datetime as _dt

        p = _eff(portfolio_id)
        rid = run_id if run_id is not None else current_run()
        price_c = round(price * 100)
        notional = price_c * quantity
        now = _dt.now().isoformat(timespec="seconds")
        tt = trade_time or now
        with _connect(self.schema) as conn:
            try:
                pos = conn.execute(
                    "SELECT * FROM positions WHERE code = %s AND portfolio_id = %s", (code, p)
                ).fetchone()
                if pos is None or pos["quantity"] == 0:
                    raise WalletError(f"无持仓: {code}")
                if pos["sellable"] < quantity:
                    raise WalletError(
                        f"可卖不足(T+1): {code} 可卖 {pos['sellable']},想卖 {quantity}"
                    )
                cash_before = self._cash(conn, p)
                cash_after = cash_before + notional
                new_qty = pos["quantity"] - quantity
                new_sellable = pos["sellable"] - quantity
                conn.execute(
                    "UPDATE positions SET quantity=%s, sellable=%s"
                    " WHERE code=%s AND portfolio_id=%s",
                    (new_qty, new_sellable, code, p),
                )
                conn.execute(
                    "UPDATE wallets SET cash_cents=%s WHERE portfolio_id=%s", (cash_after, p))
                conn.execute(
                    "INSERT INTO fills(portfolio_id, run_id, user_id, code, side, quantity,"
                    " price_cents, cash_before_cents, cash_after_cents, position_before,"
                    " position_after, created_at, reason, name, trade_time)"
                    " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (p, rid, current_user(), code, "SELL", quantity, price_c, cash_before,
                     cash_after, pos["quantity"], new_qty, now, reason, pos["name"], tt),
                )
            except Exception:
                raise
        return {"code": code, "side": "SELL", "quantity": quantity, "price": price,
                "cash_after": cash_after / 100, "position_after": new_qty}

    # ── 组合开局(core/portfolios.py 调)─────────────────

    def open_wallet(self, cash_cents: int, initial_cents: int,
                    portfolio_id: int | None = None) -> None:
        """给组合开钱包(幂等拒绝:已开局报错,防止误覆盖)。"""
        with _connect(self.schema) as conn:
            row = conn.execute(
                "SELECT 1 FROM wallets WHERE portfolio_id=%s", (_eff(portfolio_id),)).fetchone()
            if row:
                raise WalletError(f"组合 {portfolio_id} 钱包已开局")
            conn.execute(
                "INSERT INTO wallets(portfolio_id, cash_cents, initial_cents, user_id)"
                " VALUES(%s,%s,%s,%s)",
                (_eff(portfolio_id), cash_cents, initial_cents, current_user())
            )

    # ── T+1 ─────────────────────────────────────────────

    def reset(self, portfolio_id: int | None = None) -> None:
        """清空组合的持仓与流水,现金恢复初始(测试/重开实验用)。"""
        p = _eff(portfolio_id)
        with _connect(self.schema) as conn:
            conn.execute(
                "UPDATE wallets SET cash_cents=initial_cents WHERE portfolio_id=%s", (p,))
            conn.execute("DELETE FROM positions WHERE portfolio_id=%s", (p,))
            conn.execute("DELETE FROM fills WHERE portfolio_id=%s", (p,))

    def settle(self, today: str | None = None, portfolio_id: int | None = None) -> int:
        """解锁 T+1:bought_on 早于 today 的持仓全部可卖。返回解锁条数。"""
        from datetime import date as _d

        today = today or _d.today().isoformat()
        with _connect(self.schema) as conn:
            cur = conn.execute(
                "UPDATE positions SET sellable = quantity"
                " WHERE portfolio_id=%s AND bought_on < %s AND sellable != quantity",
                (_eff(portfolio_id), today),
            )
            return cur.rowcount

    # ── 内部 ────────────────────────────────────────────

    @staticmethod
    def _cash(conn, portfolio: int) -> int:
        row = conn.execute(
            "SELECT cash_cents FROM wallets WHERE portfolio_id = %s", (portfolio,)
        ).fetchone()
        if row is None:
            raise WalletError(
                f"组合 {portfolio} 钱包未开局(engine 开场时会建;先开局再交易)")
        return row["cash_cents"]

    def _init_db(self) -> None:
        ddls = [
            """CREATE TABLE IF NOT EXISTS positions (
                code TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL CHECK (quantity >= 0),
                sellable INTEGER NOT NULL CHECK (sellable >= 0 AND sellable <= quantity),
                avg_cost_cents INTEGER NOT NULL CHECK (avg_cost_cents > 0),
                bought_on TEXT NOT NULL,
                portfolio_id INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (portfolio_id, code)
            )""",
            """CREATE TABLE IF NOT EXISTS fills (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                code TEXT NOT NULL,
                side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                price_cents INTEGER NOT NULL CHECK (price_cents > 0),
                cash_before_cents INTEGER NOT NULL CHECK (cash_before_cents >= 0),
                cash_after_cents INTEGER NOT NULL CHECK (cash_after_cents >= 0),
                position_before INTEGER NOT NULL CHECK (position_before >= 0),
                position_after INTEGER NOT NULL CHECK (position_after >= 0),
                created_at TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                name TEXT NOT NULL DEFAULT '',
                trade_time TEXT,
                portfolio_id INTEGER NOT NULL DEFAULT 0,
                run_id INTEGER,
                user_id INTEGER NOT NULL DEFAULT 0
            )""",
            """CREATE TABLE IF NOT EXISTS wallets (
                portfolio_id INTEGER PRIMARY KEY,
                cash_cents INTEGER NOT NULL CHECK (cash_cents >= 0),
                initial_cents INTEGER NOT NULL CHECK (initial_cents > 0),
                user_id INTEGER NOT NULL DEFAULT 0
            )""",
            "CREATE INDEX IF NOT EXISTS fills_portfolio ON fills(portfolio_id)",
        ]
        with _connect(self.schema) as conn:
            for ddl in ddls:
                conn.execute(ddl)
            # 实盘钱包兜底(migration 会把真实现金从老 account 表对过来)
            conn.execute(
                "INSERT INTO wallets(portfolio_id, cash_cents, initial_cents)"
                " VALUES(0, %s, %s) ON CONFLICT (portfolio_id) DO NOTHING",
                (self.initial_cash, self.initial_cash)
            )


_default: Wallet | None = None


def default_wallet() -> Wallet:
    """默认钱包单例(tools 层共用;读写自动带当前组合)。"""
    global _default
    if _default is None:
        _default = Wallet()
    return _default
