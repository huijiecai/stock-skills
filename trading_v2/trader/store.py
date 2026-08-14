"""账户层:持仓 + 现金,SQLite 存储(模拟交易账户,完全独立)。

设计(继承 v1 思路,简化):
- 金额一律用"分"(int cents)存储,避免浮点误差
- 持仓含 sellable(可卖数量)与 bought_on(买入日):T+1 依据
- 每笔买卖记 fill(cash/position 的 before/after),可审计对账
- 加仓会重置整仓 T+1(保守简化:宁可多锁一天,不错放一天)
"""

import sqlite3
from datetime import date, datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "account.db"
INITIAL_CASH = 100_000_00  # 初始资金 ¥100,000(单位:分)


class AccountError(Exception):
    """账户操作失败(现金不足 / 可卖不足等)。"""


class Account:
    """模拟账户:单 agent 顺序使用,SQLite 持久化。"""

    def __init__(self, db_path: Path | str = DB_PATH, initial_cash: int = INITIAL_CASH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initial_cash = initial_cash
        self._init_db()

    # ── 查询 ────────────────────────────────────────────

    def cash(self) -> int:
        """现金(分)。"""
        with self._connect() as conn:
            return self._cash(conn)

    def positions(self) -> list[dict]:
        """全部持仓(quantity>0),avg_cost 转为元(展示用)。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT code, quantity, sellable, avg_cost_cents, bought_on"
                " FROM positions WHERE quantity > 0 ORDER BY code"
            ).fetchall()
        return [
            {"code": r["code"], "quantity": r["quantity"], "sellable": r["sellable"],
             "avg_cost": r["avg_cost_cents"] / 100, "bought_on": r["bought_on"]}
            for r in rows
        ]

    def position(self, code: str) -> dict | None:
        """单只持仓,无则 None。"""
        with self._connect() as conn:
            r = conn.execute("SELECT * FROM positions WHERE code = ?", (code,)).fetchone()
        if r is None or r["quantity"] == 0:
            return None
        return {"code": r["code"], "quantity": r["quantity"], "sellable": r["sellable"],
                "avg_cost": r["avg_cost_cents"] / 100, "bought_on": r["bought_on"]}

    def fills(self) -> list[dict]:
        """全部成交记录(审计对账用)。"""
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM fills ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    # ── 交易(事务 + fill)───────────────────────────────

    def buy(self, code: str, quantity: int, price: float, on: str | None = None) -> dict:
        """买入:扣现金、加仓(加权成本)、记 fill。
        on=买入日 YYYY-MM-DD(T+1 依据,默认今天)。
        """
        on = on or date.today().isoformat()
        price_c = round(price * 100)
        notional = price_c * quantity
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cash_before = self._cash(conn)
                if cash_before < notional:
                    raise AccountError(
                        f"现金不足:需 ¥{notional / 100:,.2f},只有 ¥{cash_before / 100:,.2f}"
                    )
                row = conn.execute(
                    "SELECT quantity, avg_cost_cents FROM positions WHERE code = ?", (code,)
                ).fetchone()
                if row and row["quantity"] > 0:
                    old_qty, old_cost = row["quantity"], row["avg_cost_cents"]
                    new_qty = old_qty + quantity
                    new_cost = (old_qty * old_cost + notional) // new_qty
                    conn.execute(
                        "UPDATE positions SET quantity=?, avg_cost_cents=?, bought_on=? WHERE code=?",
                        (new_qty, new_cost, on, code),
                    )
                    pos_before = old_qty
                else:
                    conn.execute(
                        "INSERT INTO positions(code, quantity, sellable, avg_cost_cents, bought_on)"
                        " VALUES(?,?,0,?,?)",
                        (code, quantity, price_c, on),
                    )
                    pos_before = 0
                cash_after = cash_before - notional
                conn.execute("UPDATE account SET cash_cents=? WHERE id=1", (cash_after,))
                conn.execute(
                    "INSERT INTO fills(code, side, quantity, price_cents, cash_before_cents,"
                    " cash_after_cents, position_before, position_after, created_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (code, "BUY", quantity, price_c, cash_before, cash_after,
                     pos_before, pos_before + quantity, now),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {"code": code, "side": "BUY", "quantity": quantity, "price": price,
                "cash_after": cash_after / 100, "position_after": pos_before + quantity}

    def sell(self, code: str, quantity: int, price: float) -> dict:
        """卖出:校验可卖(T+1)、加现金、减仓(成本不变)、记 fill。"""
        price_c = round(price * 100)
        notional = price_c * quantity
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                pos = conn.execute("SELECT * FROM positions WHERE code = ?", (code,)).fetchone()
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
                    "UPDATE positions SET quantity=?, sellable=? WHERE code=?",
                    (new_qty, new_sellable, code),
                )
                conn.execute("UPDATE account SET cash_cents=? WHERE id=1", (cash_after,))
                conn.execute(
                    "INSERT INTO fills(code, side, quantity, price_cents, cash_before_cents,"
                    " cash_after_cents, position_before, position_after, created_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (code, "SELL", quantity, price_c, cash_before, cash_after,
                     pos["quantity"], new_qty, now),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {"code": code, "side": "SELL", "quantity": quantity, "price": price,
                "cash_after": cash_after / 100, "position_after": new_qty}

    # ── T+1 ─────────────────────────────────────────────

    def settle(self, today: str | None = None) -> int:
        """解锁 T+1:bought_on 早于 today 的持仓全部可卖。返回解锁条数。"""
        today = today or date.today().isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE positions SET sellable = quantity"
                " WHERE bought_on < ? AND sellable != quantity",
                (today,),
            )
            conn.commit()
            return cur.rowcount

    # ── 内部 ────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _cash(conn: sqlite3.Connection) -> int:
        return conn.execute("SELECT cash_cents FROM account WHERE id = 1").fetchone()["cash_cents"]

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS account (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    cash_cents INTEGER NOT NULL CHECK (cash_cents >= 0)
                );
                CREATE TABLE IF NOT EXISTS positions (
                    code TEXT PRIMARY KEY,
                    quantity INTEGER NOT NULL CHECK (quantity >= 0),
                    sellable INTEGER NOT NULL CHECK (sellable >= 0 AND sellable <= quantity),
                    avg_cost_cents INTEGER NOT NULL CHECK (avg_cost_cents > 0),
                    bought_on TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS fills (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT NOT NULL,
                    side TEXT NOT NULL CHECK (side IN ('BUY','SELL')),
                    quantity INTEGER NOT NULL CHECK (quantity > 0),
                    price_cents INTEGER NOT NULL CHECK (price_cents > 0),
                    cash_before_cents INTEGER NOT NULL CHECK (cash_before_cents >= 0),
                    cash_after_cents INTEGER NOT NULL CHECK (cash_after_cents >= 0),
                    position_before INTEGER NOT NULL CHECK (position_before >= 0),
                    position_after INTEGER NOT NULL CHECK (position_after >= 0),
                    created_at TEXT NOT NULL
                );
                """
            )
            if conn.execute("SELECT COUNT(*) FROM account").fetchone()[0] == 0:
                conn.execute(
                    "INSERT INTO account(id, cash_cents) VALUES(1, ?)", (self.initial_cash,)
                )
            conn.commit()


# ── 默认账户(单例)───────────────────────────────────

_default: Account | None = None


def default_account() -> Account:
    """默认账户(单例):tools 层共用同一个 SQLite 账户,保证读写一致。"""
    global _default
    if _default is None:
        _default = Account()
    return _default
