"""core·账本(平台通用件):模拟账户,PG 持久化。

设计(docs/实现设计.md §2/§7):
- 金额一律用"分"(int cents),避免浮点误差
- 持仓含 sellable(可卖数量)与 bought_on(买入日):T+1 依据
- 每笔买卖记 fill(cash/position 的 before/after),可审计对账
- schema 参数是老隔离路径(C3 前回放袋仍用);行级 bag_id 列已加,store 层注入后接管
"""
from trader.core.db import _connect

INITIAL_CASH = 100_000_00  # 初始资金 ¥100,000(单位:分)


class AccountError(Exception):
    """账户操作失败(现金不足 / 可卖不足等)。"""


class Account:
    """模拟账户:单 agent 顺序使用,PG 持久化。schema 隔离(public=实盘)。"""

    def __init__(self, schema: str = "public", initial_cash: int = INITIAL_CASH) -> None:
        self.schema = schema
        self.initial_cash = initial_cash
        self._init_db()

    # ── 查询 ────────────────────────────────────────────

    def cash(self) -> int:
        """现金(分)。"""
        with _connect(self.schema) as conn:
            return self._cash(conn)

    def positions(self) -> list[dict]:
        """全部持仓(quantity>0),avg_cost 转为元(展示用)。"""
        with _connect(self.schema) as conn:
            rows = conn.execute(
                "SELECT code, name, quantity, sellable, avg_cost_cents, bought_on"
                " FROM positions WHERE quantity > 0 ORDER BY code"
            ).fetchall()
        return [
            {"code": r["code"], "name": r["name"], "quantity": r["quantity"],
             "sellable": r["sellable"], "avg_cost": r["avg_cost_cents"] / 100,
             "bought_on": r["bought_on"]}
            for r in rows
        ]

    def position(self, code: str) -> dict | None:
        """单只持仓,无则 None。"""
        with _connect(self.schema) as conn:
            r = conn.execute("SELECT * FROM positions WHERE code = %s", (code,)).fetchone()
        if r is None or r["quantity"] == 0:
            return None
        return {"code": r["code"], "name": r["name"], "quantity": r["quantity"],
                "sellable": r["sellable"], "avg_cost": r["avg_cost_cents"] / 100,
                "bought_on": r["bought_on"]}

    def fills(self) -> list[dict]:
        """全部成交记录(含决策留痕 reason,复盘用)。"""
        with _connect(self.schema) as conn:
            rows = conn.execute("SELECT * FROM fills ORDER BY id").fetchall()
        return rows

    # ── 交易(事务 + fill)───────────────────────────────

    def buy(self, code: str, quantity: int, price: float, on: str | None = None,
            name: str = "", reason: str = "", expectation_id: int | None = None,
            trade_time: str = "") -> dict:
        """买入:扣现金、加仓(加权成本)、记 fill(含决策留痕)。
        on=买入日(T+1 依据);name=股票名;reason=决策依据;expectation_id=关联预期(老列,C1e 起不再写入);
        trade_time=成交时点(回放 "20260814 09:35" 或真实时间)。"""
        from datetime import date as _d, datetime as _dt

        on = on or _d.today().isoformat()
        price_c = round(price * 100)
        notional = price_c * quantity
        now = _dt.now().isoformat(timespec="seconds")
        tt = trade_time or now
        with _connect(self.schema) as conn:
            try:
                cash_before = self._cash(conn)
                if cash_before < notional:
                    raise AccountError(
                        f"现金不足:需 ¥{notional / 100:,.2f},只有 ¥{cash_before / 100:,.2f}"
                    )
                row = conn.execute(
                    "SELECT quantity, avg_cost_cents FROM positions WHERE code = %s", (code,)
                ).fetchone()
                if row and row["quantity"] > 0:
                    old_qty, old_cost = row["quantity"], row["avg_cost_cents"]
                    new_qty = old_qty + quantity
                    new_cost = (old_qty * old_cost + notional) // new_qty
                    conn.execute(
                        "UPDATE positions SET quantity=%s, avg_cost_cents=%s, bought_on=%s,"
                        " name=CASE WHEN %s!='' THEN %s ELSE name END WHERE code=%s",
                        (new_qty, new_cost, on, name, name, code),
                    )
                    pos_before = old_qty
                else:
                    conn.execute(
                        "INSERT INTO positions(code, name, quantity, sellable, avg_cost_cents, bought_on)"
                        " VALUES(%s,%s,%s,%s,%s,%s)",
                        (code, name, quantity, 0, price_c, on),
                    )
                    pos_before = 0
                cash_after = cash_before - notional
                conn.execute("UPDATE account SET cash_cents=%s WHERE id=1", (cash_after,))
                conn.execute(
                    "INSERT INTO fills(code, side, quantity, price_cents, cash_before_cents,"
                    " cash_after_cents, position_before, position_after, created_at,"
                    " reason, expectation_id, name, trade_time)"
                    " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (code, "BUY", quantity, price_c, cash_before, cash_after,
                     pos_before, pos_before + quantity, now, reason, expectation_id, name, tt),
                )
            except Exception:
                raise  # with 块退出时自动 rollback
        return {"code": code, "side": "BUY", "quantity": quantity, "price": price,
                "cash_after": cash_after / 100, "position_after": pos_before + quantity}

    def sell(self, code: str, quantity: int, price: float, reason: str = "",
             expectation_id: int | None = None, trade_time: str = "") -> dict:
        """卖出:校验可卖(T+1)、加现金、减仓(成本不变)、记 fill(含决策留痕)。"""
        from datetime import datetime as _dt

        price_c = round(price * 100)
        notional = price_c * quantity
        now = _dt.now().isoformat(timespec="seconds")
        tt = trade_time or now
        with _connect(self.schema) as conn:
            try:
                pos = conn.execute("SELECT * FROM positions WHERE code = %s", (code,)).fetchone()
                if pos is None or pos["quantity"] == 0:
                    raise AccountError(f"无持仓: {code}")
                if pos["sellable"] < quantity:
                    raise AccountError(
                        f"可卖不足(T+1): {code} 可卖 {pos['sellable']},想卖 {quantity}"
                    )
                cash_before = self._cash(conn)
                cash_after = cash_before + notional
                new_qty = pos["quantity"] - quantity
                new_sellable = pos["sellable"] - quantity
                conn.execute(
                    "UPDATE positions SET quantity=%s, sellable=%s WHERE code=%s",
                    (new_qty, new_sellable, code),
                )
                conn.execute("UPDATE account SET cash_cents=%s WHERE id=1", (cash_after,))
                conn.execute(
                    "INSERT INTO fills(code, side, quantity, price_cents, cash_before_cents,"
                    " cash_after_cents, position_before, position_after, created_at,"
                    " reason, expectation_id, name, trade_time)"
                    " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (code, "SELL", quantity, price_c, cash_before, cash_after,
                     pos["quantity"], new_qty, now, reason, expectation_id,
                     pos["name"], tt),
                )
            except Exception:
                raise
        return {"code": code, "side": "SELL", "quantity": quantity, "price": price,
                "cash_after": cash_after / 100, "position_after": new_qty}

    # ── T+1 ─────────────────────────────────────────────

    def reset(self) -> None:
        """重置模拟账户:现金恢复初始值,清空持仓与成交流水。"""
        with _connect(self.schema) as conn:
            conn.execute("UPDATE account SET cash_cents=%s WHERE id=1", (self.initial_cash,))
            conn.execute("DELETE FROM positions")
            conn.execute("DELETE FROM fills")

    def settle(self, today: str | None = None) -> int:
        """解锁 T+1:bought_on 早于 today 的持仓全部可卖。返回解锁条数。"""
        from datetime import date as _d

        today = today or _d.today().isoformat()
        with _connect(self.schema) as conn:
            cur = conn.execute(
                "UPDATE positions SET sellable = quantity"
                " WHERE bought_on < %s AND sellable != quantity",
                (today,),
            )
            return cur.rowcount

    # ── 内部 ────────────────────────────────────────────

    @staticmethod
    def _cash(conn) -> int:
        return conn.execute("SELECT cash_cents FROM account WHERE id = 1").fetchone()["cash_cents"]

    def _init_db(self) -> None:
        ddls = [
            """CREATE TABLE IF NOT EXISTS account (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                cash_cents INTEGER NOT NULL CHECK (cash_cents >= 0)
            )""",
            """CREATE TABLE IF NOT EXISTS positions (
                code TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                quantity INTEGER NOT NULL CHECK (quantity >= 0),
                sellable INTEGER NOT NULL CHECK (sellable >= 0 AND sellable <= quantity),
                avg_cost_cents INTEGER NOT NULL CHECK (avg_cost_cents > 0),
                bought_on TEXT NOT NULL
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
                expectation_id INTEGER,
                name TEXT NOT NULL DEFAULT '',
                trade_time TEXT
            )""",
            # 行级多租户(实现设计 §7):正本=0;wallets 是新袋现金表(metrics 的 initial 基准)
            "ALTER TABLE positions ADD COLUMN IF NOT EXISTS bag_id INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE fills ADD COLUMN IF NOT EXISTS bag_id INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE fills ADD COLUMN IF NOT EXISTS run_id INTEGER",
            """CREATE TABLE IF NOT EXISTS wallets (
                bag_id INTEGER PRIMARY KEY,
                cash_cents INTEGER NOT NULL CHECK (cash_cents >= 0),
                initial_cents INTEGER NOT NULL CHECK (initial_cents > 0)
            )""",
            "CREATE INDEX IF NOT EXISTS fills_bag ON fills(bag_id)",
            "CREATE INDEX IF NOT EXISTS positions_bag ON positions(bag_id)",
        ]
        with _connect(self.schema) as conn:
            for ddl in ddls:
                conn.execute(ddl)
            conn.execute(
                "INSERT INTO account(id, cash_cents) VALUES(1, %s)"
                " ON CONFLICT (id) DO NOTHING", (self.initial_cash,)
            )
            conn.execute(
                "INSERT INTO wallets(bag_id, cash_cents, initial_cents) VALUES(0, %s, %s)"
                " ON CONFLICT (bag_id) DO NOTHING", (self.initial_cash, self.initial_cash)
            )
