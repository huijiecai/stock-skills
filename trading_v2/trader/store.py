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


# ══════════════════════════════════════════════════════════
# 预期库:预期条目 + 池成员(与 Account 共用同一个 SQLite 文件)
# ══════════════════════════════════════════════════════════

class Expectations:
    """预期库:方向(direction)下的具体预期事件(event),独立生命周期。

    - 同方向可挂多个预期(存储芯片·存货涨价 / 存储芯片·2026年报业绩,多波炒作)
    - 池成员分 role:leader(龙头候选)/ core(核心直接受益)/ related(相关)
    - 失效与兑现并列:fail_flag 事前定义,invalid_reason 事后记录
    - stage 管阶段(影响买点):observing→emerging→confirmed→climax→fulfilling→ended
    """

    STAGES = ("observing", "emerging", "confirmed", "climax", "fulfilling", "ended")
    STATUSES = ("researching", "active", "fulfilled", "invalid")
    ROLES = ("leader", "core", "related")

    def __init__(self, db_path: Path | str = DB_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── 写 ──────────────────────────────────────────────

    def add(self, direction: str, event: str, thesis: str, catalyst: str,
            fulfill_flag: str, fail_flag: str, pool: list[dict]) -> int:
        """新增预期(研究完写入)。pool=[{code,name,role,reason}]。返回 id。"""
        now = datetime.now().isoformat(timespec="seconds")
        for m in pool:
            if m.get("role", "related") not in self.ROLES:
                raise ValueError(f"pool role 非法:{m.get('role')}(允许 {self.ROLES})")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cur = conn.execute(
                    "INSERT INTO expectations(direction,event,thesis,catalyst,"
                    "fulfill_flag,fail_flag,stage,status,created_at,updated_at)"
                    " VALUES(?,?,?,?,?,?, 'observing','active',?,?)",
                    (direction, event, thesis, catalyst, fulfill_flag, fail_flag, now, now),
                )
                eid = cur.lastrowid
                for m in pool:
                    conn.execute(
                        "INSERT INTO pool_members(expectation_id,code,name,role,reason)"
                        " VALUES(?,?,?,?,?)",
                        (eid, m["code"], m.get("name", ""),
                         m.get("role", "related"), m.get("reason", "")),
                    )
                conn.commit()
            except sqlite3.IntegrityError as e:
                conn.rollback()
                raise ValueError(f"写入失败(可能 {direction}·{event} 已存在或池成员重复):{e}") from e
            except Exception:
                conn.rollback()
                raise
        return eid

    def update(self, expectation_id: int, stage: str | None = None, status: str | None = None,
               invalid_reason: str | None = None, thesis: str | None = None,
               catalyst: str | None = None, fulfill_flag: str | None = None,
               fail_flag: str | None = None) -> None:
        """更新预期:状态字段(stage/status/invalid_reason)或内容字段(thesis/catalyst/兑现/失效)。
        内容字段用于"重新研究后修正"(Mode B)。"""
        if stage is not None and stage not in self.STAGES:
            raise ValueError(f"stage 非法:{stage}(允许 {self.STAGES})")
        if status is not None and status not in self.STATUSES:
            raise ValueError(f"status 非法:{status}(允许 {self.STATUSES})")
        fields = {"stage": stage, "status": status, "invalid_reason": invalid_reason,
                  "thesis": thesis, "catalyst": catalyst,
                  "fulfill_flag": fulfill_flag, "fail_flag": fail_flag}
        sets, args = [], []
        for col, val in fields.items():
            if val is not None:
                sets.append(f"{col}=?")
                args.append(val)
        if not sets:
            raise ValueError("没有要更新的字段")
        sets.append("updated_at=?")
        args.append(datetime.now().isoformat(timespec="seconds"))
        args.append(expectation_id)
        with self._connect() as conn:
            cur = conn.execute(f"UPDATE expectations SET {', '.join(sets)} WHERE id=?", args)
            conn.commit()
            if cur.rowcount == 0:
                raise ValueError(f"预期 {expectation_id} 不存在")

    def add_pool_member(self, expectation_id: int, code: str, name: str = "",
                        role: str = "related", reason: str = "") -> None:
        """添加/更新池成员:同代码已存在时更新 role/reason/name(重新研究修订池用)。"""
        if role not in self.ROLES:
            raise ValueError(f"role 非法:{role}(允许 {self.ROLES})")
        now = datetime.now().isoformat(timespec="seconds")
        with self._connect() as conn:
            if not conn.execute(
                "SELECT 1 FROM expectations WHERE id=?", (expectation_id,)
            ).fetchone():
                raise ValueError(f"预期 {expectation_id} 不存在")
            conn.execute(
                "INSERT INTO pool_members(expectation_id,code,name,role,reason)"
                " VALUES(?,?,?,?,?)"
                " ON CONFLICT(expectation_id, code)"
                " DO UPDATE SET name=excluded.name, role=excluded.role, reason=excluded.reason",
                (expectation_id, code, name, role, reason),
            )
            conn.execute("UPDATE expectations SET updated_at=? WHERE id=?", (now, expectation_id))
            conn.commit()

    def remove_pool_member(self, expectation_id: int, code: str) -> None:
        """从池中剔除成员(重新研究后调整池用)。"""
        with self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM pool_members WHERE expectation_id=? AND code=?",
                (expectation_id, code),
            )
            conn.commit()
            if cur.rowcount == 0:
                raise ValueError(f"池成员不存在:{code}(预期 #{expectation_id})")

    # ── 读 ──────────────────────────────────────────────

    def get_all(self) -> list[dict]:
        """全部预期(倒序),含 核心/池 成员数统计。"""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT e.*,"
                " (SELECT COUNT(*) FROM pool_members p WHERE p.expectation_id = e.id) AS pool_count,"
                " (SELECT COUNT(*) FROM pool_members p WHERE p.expectation_id = e.id"
                "   AND p.role IN ('leader','core')) AS core_count"
                " FROM expectations e ORDER BY e.id DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, expectation_id: int) -> dict | None:
        """单个预期详情(含池成员,leader>core>related 排序)。"""
        with self._connect() as conn:
            r = conn.execute(
                "SELECT * FROM expectations WHERE id = ?", (expectation_id,)
            ).fetchone()
            if r is None:
                return None
            members = conn.execute(
                "SELECT code,name,role,reason FROM pool_members WHERE expectation_id = ?"
                " ORDER BY CASE role WHEN 'leader' THEN 0 WHEN 'core' THEN 1 ELSE 2 END, code",
                (expectation_id,),
            ).fetchall()
        d = dict(r)
        d["pool"] = [dict(m) for m in members]
        return d

    def pool_codes(self, expectation_id: int, roles: tuple[str, ...] | None = None) -> list[str]:
        """某预期的池成员代码;roles 可过滤(如只取 ('leader','core'))。"""
        if roles is not None:
            bad = set(roles) - set(self.ROLES)
            if bad:
                raise ValueError(f"roles 非法:{bad}")
        with self._connect() as conn:
            if roles:
                marks = ",".join("?" * len(roles))
                rows = conn.execute(
                    f"SELECT code FROM pool_members WHERE expectation_id=? AND role IN ({marks})",
                    (expectation_id, *roles),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT code FROM pool_members WHERE expectation_id=?",
                    (expectation_id,),
                ).fetchall()
        return [r["code"] for r in rows]

    # ── 内部 ────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS expectations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    direction TEXT NOT NULL,
                    event TEXT NOT NULL,
                    thesis TEXT NOT NULL,
                    catalyst TEXT NOT NULL,
                    fulfill_flag TEXT NOT NULL,
                    fail_flag TEXT NOT NULL,
                    stage TEXT NOT NULL DEFAULT 'observing'
                        CHECK (stage IN ('observing','emerging','confirmed','climax','fulfilling','ended')),
                    status TEXT NOT NULL DEFAULT 'active'
                        CHECK (status IN ('researching','active','fulfilled','invalid')),
                    invalid_reason TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (direction, event)
                );
                CREATE TABLE IF NOT EXISTS pool_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    expectation_id INTEGER NOT NULL REFERENCES expectations(id),
                    code TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL DEFAULT 'related'
                        CHECK (role IN ('leader','core','related')),
                    reason TEXT NOT NULL DEFAULT '',
                    UNIQUE (expectation_id, code)
                );
                CREATE INDEX IF NOT EXISTS pool_members_exp
                    ON pool_members(expectation_id);
                """
            )
            conn.commit()


_expectations: Expectations | None = None


def default_expectations() -> Expectations:
    """默认预期库(单例):与默认账户同一个 SQLite 文件。"""
    global _expectations
    if _expectations is None:
        _expectations = Expectations()
    return _expectations
