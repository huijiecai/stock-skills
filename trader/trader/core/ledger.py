"""core·账本(平台通用件):模拟账户,PG 持久化,行级 bag_id 隔离(实现设计 §7)。

- 金额一律用"分"(int cents),避免浮点误差
- 现金按袋子挂 wallets(bag_id, cash_cents, initial_cents);正本=bag_id 0
- 持仓含 sellable(可卖数量)与 bought_on(买入日):T+1 依据
- 每笔买卖记 fill(before/after + run_id 归因),可审计对账
- bag_id 参数缺省 = 当前袋子(core.context,engine 唯一注入)
- schema 参数仅测试隔离用(老 schema 路径已退役)
"""
from trader.core.context import current_bag, current_run
from trader.core.db import _connect

INITIAL_CASH = 100_000_00  # 初始资金 ¥100,000(单位:分)


class AccountError(Exception):
    """账户操作失败(现金不足 / 可卖不足 / 袋子未开局等)。"""


def _eff(bag_id: int | None) -> int:
    return bag_id if bag_id is not None else current_bag()


class Account:
    """模拟账户:单 agent 顺序使用,PG 持久化,行级袋子隔离。"""

    def __init__(self, schema: str = "public", initial_cash: int = INITIAL_CASH) -> None:
        self.schema = schema
        self.initial_cash = initial_cash
        self._init_db()

    # ── 查询 ────────────────────────────────────────────

    def cash(self, bag_id: int | None = None) -> int:
        """现金(分)。"""
        with _connect(self.schema) as conn:
            return self._cash(conn, _eff(bag_id))

    def positions(self, bag_id: int | None = None) -> list[dict]:
        """全部持仓(quantity>0),avg_cost 转为元(展示用)。"""
        b = _eff(bag_id)
        with _connect(self.schema) as conn:
            rows = conn.execute(
                "SELECT code, name, quantity, sellable, avg_cost_cents, bought_on"
                " FROM positions WHERE quantity > 0 AND bag_id=%s ORDER BY code", (b,)
            ).fetchall()
        return [
            {"code": r["code"], "name": r["name"], "quantity": r["quantity"],
             "sellable": r["sellable"], "avg_cost": r["avg_cost_cents"] / 100,
             "bought_on": r["bought_on"]}
            for r in rows
        ]

    def position(self, code: str, bag_id: int | None = None) -> dict | None:
        """单只持仓,无则 None。"""
        with _connect(self.schema) as conn:
            r = conn.execute(
                "SELECT * FROM positions WHERE code = %s AND bag_id = %s",
                (code, _eff(bag_id)),
            ).fetchone()
        if r is None or r["quantity"] == 0:
            return None
        return {"code": r["code"], "name": r["name"], "quantity": r["quantity"],
                "sellable": r["sellable"], "avg_cost": r["avg_cost_cents"] / 100,
                "bought_on": r["bought_on"]}

    def fills(self, bag_id: int | None = None) -> list[dict]:
        """全部成交记录(含决策留痕 reason + run_id 归因,复盘用)。"""
        with _connect(self.schema) as conn:
            rows = conn.execute(
                "SELECT * FROM fills WHERE bag_id=%s ORDER BY id", (_eff(bag_id),)
            ).fetchall()
        return rows

    # ── 交易(事务 + fill)───────────────────────────────

    def buy(self, code: str, quantity: int, price: float, on: str | None = None,
            name: str = "", reason: str = "", trade_time: str = "",
            bag_id: int | None = None, run_id: int | None = None) -> dict:
        """买入:扣现金、加仓(加权成本)、记 fill(含决策留痕 + run_id)。
        on=买入日(T+1 依据);trade_time=成交时点(回放 "20260814 09:35" 或真实时间)。"""
        from datetime import date as _d, datetime as _dt

        b = _eff(bag_id)
        rid = run_id if run_id is not None else current_run()
        on = on or _d.today().isoformat()
        price_c = round(price * 100)
        notional = price_c * quantity
        now = _dt.now().isoformat(timespec="seconds")
        tt = trade_time or now
        with _connect(self.schema) as conn:
            try:
                cash_before = self._cash(conn, b)
                if cash_before < notional:
                    raise AccountError(
                        f"现金不足:需 ¥{notional / 100:,.2f},只有 ¥{cash_before / 100:,.2f}"
                    )
                row = conn.execute(
                    "SELECT quantity, avg_cost_cents FROM positions"
                    " WHERE code = %s AND bag_id = %s", (code, b)
                ).fetchone()
                if row and row["quantity"] > 0:
                    old_qty, old_cost = row["quantity"], row["avg_cost_cents"]
                    new_qty = old_qty + quantity
                    new_cost = (old_qty * old_cost + notional) // new_qty
                    conn.execute(
                        "UPDATE positions SET quantity=%s, avg_cost_cents=%s, bought_on=%s,"
                        " name=CASE WHEN %s!='' THEN %s ELSE name END"
                        " WHERE code=%s AND bag_id=%s",
                        (new_qty, new_cost, on, name, name, code, b),
                    )
                    pos_before = old_qty
                else:
                    conn.execute(
                        "INSERT INTO positions(bag_id, code, name, quantity, sellable,"
                        " avg_cost_cents, bought_on) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                        (b, code, name, quantity, 0, price_c, on),
                    )
                    pos_before = 0
                cash_after = cash_before - notional
                conn.execute("UPDATE wallets SET cash_cents=%s WHERE bag_id=%s", (cash_after, b))
                conn.execute(
                    "INSERT INTO fills(bag_id, run_id, code, side, quantity, price_cents,"
                    " cash_before_cents, cash_after_cents, position_before, position_after,"
                    " created_at, reason, name, trade_time)"
                    " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (b, rid, code, "BUY", quantity, price_c, cash_before, cash_after,
                     pos_before, pos_before + quantity, now, reason, name, tt),
                )
            except Exception:
                raise  # with 块退出时自动 rollback
        return {"code": code, "side": "BUY", "quantity": quantity, "price": price,
                "cash_after": cash_after / 100, "position_after": pos_before + quantity}

    def sell(self, code: str, quantity: int, price: float, reason: str = "",
             trade_time: str = "", bag_id: int | None = None,
             run_id: int | None = None) -> dict:
        """卖出:校验可卖(T+1)、加现金、减仓(成本不变)、记 fill(含决策留痕)。"""
        from datetime import datetime as _dt

        b = _eff(bag_id)
        rid = run_id if run_id is not None else current_run()
        price_c = round(price * 100)
        notional = price_c * quantity
        now = _dt.now().isoformat(timespec="seconds")
        tt = trade_time or now
        with _connect(self.schema) as conn:
            try:
                pos = conn.execute(
                    "SELECT * FROM positions WHERE code = %s AND bag_id = %s", (code, b)
                ).fetchone()
                if pos is None or pos["quantity"] == 0:
                    raise AccountError(f"无持仓: {code}")
                if pos["sellable"] < quantity:
                    raise AccountError(
                        f"可卖不足(T+1): {code} 可卖 {pos['sellable']},想卖 {quantity}"
                    )
                cash_before = self._cash(conn, b)
                cash_after = cash_before + notional
                new_qty = pos["quantity"] - quantity
                new_sellable = pos["sellable"] - quantity
                conn.execute(
                    "UPDATE positions SET quantity=%s, sellable=%s WHERE code=%s AND bag_id=%s",
                    (new_qty, new_sellable, code, b),
                )
                conn.execute("UPDATE wallets SET cash_cents=%s WHERE bag_id=%s", (cash_after, b))
                conn.execute(
                    "INSERT INTO fills(bag_id, run_id, code, side, quantity, price_cents,"
                    " cash_before_cents, cash_after_cents, position_before, position_after,"
                    " created_at, reason, name, trade_time)"
                    " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (b, rid, code, "SELL", quantity, price_c, cash_before, cash_after,
                     pos["quantity"], new_qty, now, reason, pos["name"], tt),
                )
            except Exception:
                raise
        return {"code": code, "side": "SELL", "quantity": quantity, "price": price,
                "cash_after": cash_after / 100, "position_after": new_qty}

    # ── 袋子开局(core/bag.py 调)────────────────────────

    def open_wallet(self, cash_cents: int, initial_cents: int,
                    bag_id: int | None = None) -> None:
        """给袋子开钱包(幂等拒绝:已开局报错,防止误覆盖)。"""
        with _connect(self.schema) as conn:
            row = conn.execute("SELECT 1 FROM wallets WHERE bag_id=%s", (_eff(bag_id),)).fetchone()
            if row:
                raise AccountError(f"袋子 {bag_id} 钱包已开局")
            conn.execute(
                "INSERT INTO wallets(bag_id, cash_cents, initial_cents) VALUES(%s,%s,%s)",
                (_eff(bag_id), cash_cents, initial_cents)
            )

    # ── T+1 ─────────────────────────────────────────────

    def reset(self, bag_id: int | None = None) -> None:
        """清空袋子的持仓与流水,现金恢复初始(测试/重开实验用)。"""
        b = _eff(bag_id)
        with _connect(self.schema) as conn:
            conn.execute(
                "UPDATE wallets SET cash_cents=initial_cents WHERE bag_id=%s", (b,))
            conn.execute("DELETE FROM positions WHERE bag_id=%s", (b,))
            conn.execute("DELETE FROM fills WHERE bag_id=%s", (b,))

    def settle(self, today: str | None = None, bag_id: int | None = None) -> int:
        """解锁 T+1:bought_on 早于 today 的持仓全部可卖。返回解锁条数。"""
        from datetime import date as _d

        today = today or _d.today().isoformat()
        with _connect(self.schema) as conn:
            cur = conn.execute(
                "UPDATE positions SET sellable = quantity"
                " WHERE bag_id=%s AND bought_on < %s AND sellable != quantity",
                (_eff(bag_id), today),
            )
            return cur.rowcount

    # ── 内部 ────────────────────────────────────────────

    @staticmethod
    def _cash(conn, bag: int) -> int:
        row = conn.execute(
            "SELECT cash_cents FROM wallets WHERE bag_id = %s", (bag,)
        ).fetchone()
        if row is None:
            raise AccountError(f"袋子 {bag} 钱包未开局(engine 开场时会建;先开局再交易)")
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
                bag_id INTEGER NOT NULL DEFAULT 0
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
                bag_id INTEGER NOT NULL DEFAULT 0,
                run_id INTEGER
            )""",
            """CREATE TABLE IF NOT EXISTS wallets (
                bag_id INTEGER PRIMARY KEY,
                cash_cents INTEGER NOT NULL CHECK (cash_cents >= 0),
                initial_cents INTEGER NOT NULL CHECK (initial_cents > 0)
            )""",
            # 行级迁移(实现设计 §7,只加不改):
            "ALTER TABLE positions ADD COLUMN IF NOT EXISTS bag_id INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE fills ADD COLUMN IF NOT EXISTS bag_id INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE fills ADD COLUMN IF NOT EXISTS run_id INTEGER",
            # 老 code 主键 → (bag_id, code) 唯一
            "ALTER TABLE positions DROP CONSTRAINT IF EXISTS positions_pkey",
            "CREATE UNIQUE INDEX IF NOT EXISTS positions_bag_code ON positions(bag_id, code)",
            "CREATE INDEX IF NOT EXISTS fills_bag ON fills(bag_id)",
        ]
        with _connect(self.schema) as conn:
            for ddl in ddls:
                conn.execute(ddl)
            # 正本钱包兜底(migration 会把真实现金从老 account 表对过来)
            conn.execute(
                "INSERT INTO wallets(bag_id, cash_cents, initial_cents) VALUES(0, %s, %s)"
                " ON CONFLICT (bag_id) DO NOTHING", (self.initial_cash, self.initial_cash)
            )


_default: Account | None = None


def default_account() -> Account:
    """默认账户单例(tools 层共用;读写自动带当前袋子)。"""
    global _default
    if _default is None:
        _default = Account()
    return _default
