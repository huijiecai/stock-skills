"""存储层:持仓+现金 / 预期库 / 文档库,PostgreSQL 存储(psycopg)。

设计:
- 金额一律用"分"(int cents),避免浮点误差
- 持仓含 sellable(可卖数量)与 bought_on(买入日):T+1 依据
- 每笔买卖记 fill(cash/position 的 before/after),可审计对账
- 隔离用 PG schema:public=实盘;replay_{date}=回放实验(一次一个命名空间)
- 连接串:环境变量 DATABASE_URL(默认本地 stock_postgres 的 trader 库)
"""

import os

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5432/trader"
)
INITIAL_CASH = 100_000_00  # 初始资金 ¥100,000(单位:分)


def _connect(schema: str = "public") -> psycopg.Connection:
    """连接并定位到指定 schema(不存在则建)。行返回 dict。"""
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True)
    with conn.cursor() as cur:
        cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        cur.execute(f'SET search_path TO "{schema}"')
    conn.autocommit = False  # 之后恢复事务模式,with 块自动提交/回滚
    return conn


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
        """全部成交记录(含决策留痕 reason/expectation_id,复盘用)。"""
        with _connect(self.schema) as conn:
            rows = conn.execute("SELECT * FROM fills ORDER BY id").fetchall()
        return rows

    # ── 交易(事务 + fill)───────────────────────────────

    def buy(self, code: str, quantity: int, price: float, on: str | None = None,
            name: str = "", reason: str = "", expectation_id: int | None = None,
            trade_time: str = "") -> dict:
        """买入:扣现金、加仓(加权成本)、记 fill(含决策留痕)。
        on=买入日(T+1 依据);name=股票名;reason=决策依据;expectation_id=关联预期;
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
        """重置模拟账户:现金恢复初始值,清空持仓与成交流水。
        预期库/文档库不受影响(它们是跨会话知识,不是账户状态)。"""
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
        ]
        with _connect(self.schema) as conn:
            for ddl in ddls:
                conn.execute(ddl)
            conn.execute(
                "INSERT INTO account(id, cash_cents) VALUES(1, %s)"
                " ON CONFLICT (id) DO NOTHING", (self.initial_cash,)
            )


# ── 默认账户(单例)───────────────────────────────────

_default: Account | None = None


def default_account() -> Account:
    """默认账户(单例,public schema=实盘):tools 层共用,保证读写一致。"""
    global _default
    if _default is None:
        _default = Account()
    return _default


def schema_exists(name: str) -> bool:
    """某隔离 schema 是否存在(回放是否跑过的判断)。"""
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        return conn.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (name,)
        ).fetchone() is not None


# ══════════════════════════════════════════════════════════
# 预期库:预期条目 + 池成员(public schema,跨会话知识)
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

    def __init__(self, schema: str = "public") -> None:
        self.schema = schema
        self._init_db()

    # ── 写 ──────────────────────────────────────────────

    def add(self, direction: str, event: str, thesis: str, catalyst: str,
            fulfill_flag: str, fail_flag: str, pool: list[dict]) -> int:
        """新增预期(研究完写入)。pool=[{code,name,role,reason}]。返回 id。"""
        from datetime import datetime as _dt

        now = _dt.now().isoformat(timespec="seconds")
        for m in pool:
            if m.get("role", "related") not in self.ROLES:
                raise ValueError(f"pool role 非法:{m.get('role')}(允许 {self.ROLES})")
        with _connect(self.schema) as conn:
            try:
                row = conn.execute(
                    "INSERT INTO expectations(direction,event,thesis,catalyst,"
                    "fulfill_flag,fail_flag,stage,status,created_at,updated_at)"
                    " VALUES(%s,%s,%s,%s,%s,%s,'observing','active',%s,%s) RETURNING id",
                    (direction, event, thesis, catalyst, fulfill_flag, fail_flag, now, now),
                ).fetchone()
                eid = row["id"]
                for m in pool:
                    conn.execute(
                        "INSERT INTO pool_members(expectation_id,code,name,role,reason)"
                        " VALUES(%s,%s,%s,%s,%s)",
                        (eid, m["code"], m.get("name", ""),
                         m.get("role", "related"), m.get("reason", "")),
                    )
            except psycopg.errors.UniqueViolation as e:
                raise ValueError(
                    f"写入失败(可能 {direction}·{event} 已存在或池成员重复):{e.diag.message_detail or e}"
                ) from e
        return eid

    def update(self, expectation_id: int, stage: str | None = None, status: str | None = None,
               invalid_reason: str | None = None, thesis: str | None = None,
               catalyst: str | None = None, fulfill_flag: str | None = None,
               fail_flag: str | None = None) -> None:
        """更新预期:状态字段(stage/status/invalid_reason)或内容字段(thesis/catalyst/兑现/失效)。"""
        from datetime import datetime as _dt

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
                sets.append(f"{col}=%s")
                args.append(val)
        if not sets:
            raise ValueError("没有要更新的字段")
        sets.append("updated_at=%s")
        args.append(_dt.now().isoformat(timespec="seconds"))
        args.append(expectation_id)
        with _connect(self.schema) as conn:
            cur = conn.execute(f"UPDATE expectations SET {', '.join(sets)} WHERE id=%s", args)
            if cur.rowcount == 0:
                raise ValueError(f"预期 {expectation_id} 不存在")

    def add_pool_member(self, expectation_id: int, code: str, name: str = "",
                        role: str = "related", reason: str = "") -> None:
        """添加/更新池成员:同代码已存在时更新 role/reason/name(重新研究修订池用)。"""
        from datetime import datetime as _dt

        if role not in self.ROLES:
            raise ValueError(f"role 非法:{role}(允许 {self.ROLES})")
        now = _dt.now().isoformat(timespec="seconds")
        with _connect(self.schema) as conn:
            if not conn.execute(
                "SELECT 1 FROM expectations WHERE id=%s", (expectation_id,)
            ).fetchone():
                raise ValueError(f"预期 {expectation_id} 不存在")
            conn.execute(
                "INSERT INTO pool_members(expectation_id,code,name,role,reason)"
                " VALUES(%s,%s,%s,%s,%s)"
                " ON CONFLICT(expectation_id, code)"
                " DO UPDATE SET name=excluded.name, role=excluded.role, reason=excluded.reason",
                (expectation_id, code, name, role, reason),
            )
            conn.execute("UPDATE expectations SET updated_at=%s WHERE id=%s",
                         (now, expectation_id))

    def remove_pool_member(self, expectation_id: int, code: str) -> None:
        """从池中剔除成员(重新研究后调整池用)。"""
        with _connect(self.schema) as conn:
            cur = conn.execute(
                "DELETE FROM pool_members WHERE expectation_id=%s AND code=%s",
                (expectation_id, code),
            )
            if cur.rowcount == 0:
                raise ValueError(f"池成员不存在:{code}(预期 #{expectation_id})")

    # ── 读 ──────────────────────────────────────────────

    def get_all(self) -> list[dict]:
        """全部预期(倒序),含 核心/池 成员数统计。"""
        with _connect(self.schema) as conn:
            return conn.execute(
                "SELECT e.*,"
                " (SELECT COUNT(*) FROM pool_members p WHERE p.expectation_id = e.id) AS pool_count,"
                " (SELECT COUNT(*) FROM pool_members p WHERE p.expectation_id = e.id"
                "   AND p.role IN ('leader','core')) AS core_count"
                " FROM expectations e ORDER BY e.id DESC"
            ).fetchall()

    def get(self, expectation_id: int) -> dict | None:
        """单个预期详情(含池成员,leader>core>related 排序)。"""
        with _connect(self.schema) as conn:
            r = conn.execute(
                "SELECT * FROM expectations WHERE id = %s", (expectation_id,)
            ).fetchone()
            if r is None:
                return None
            members = conn.execute(
                "SELECT code,name,role,reason FROM pool_members WHERE expectation_id = %s"
                " ORDER BY CASE role WHEN 'leader' THEN 0 WHEN 'core' THEN 1 ELSE 2 END, code",
                (expectation_id,),
            ).fetchall()
        d = dict(r)
        d["pool"] = members
        return d

    def pool_codes(self, expectation_id: int, roles: tuple[str, ...] | None = None) -> list[str]:
        """某预期的池成员代码;roles 可过滤(如只取 ('leader','core'))。"""
        if roles is not None:
            bad = set(roles) - set(self.ROLES)
            if bad:
                raise ValueError(f"roles 非法:{bad}")
        with _connect(self.schema) as conn:
            if roles:
                marks = ",".join(["%s"] * len(roles))
                rows = conn.execute(
                    f"SELECT code FROM pool_members WHERE expectation_id=%s AND role IN ({marks})",
                    (expectation_id, *roles),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT code FROM pool_members WHERE expectation_id=%s",
                    (expectation_id,),
                ).fetchall()
        return [r["code"] for r in rows]

    # ── 内部 ────────────────────────────────────────────

    def _init_db(self) -> None:
        ddls = [
            """CREATE TABLE IF NOT EXISTS expectations (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
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
            )""",
            """CREATE TABLE IF NOT EXISTS pool_members (
                id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                expectation_id INTEGER NOT NULL REFERENCES expectations(id),
                code TEXT NOT NULL,
                name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'related'
                    CHECK (role IN ('leader','core','related')),
                reason TEXT NOT NULL DEFAULT '',
                UNIQUE (expectation_id, code)
            )""",
            "CREATE INDEX IF NOT EXISTS pool_members_exp ON pool_members(expectation_id)",
        ]
        with _connect(self.schema) as conn:
            for ddl in ddls:
                conn.execute(ddl)


_expectations: Expectations | None = None


def default_expectations() -> Expectations:
    """默认预期库(单例,public schema):跨会话知识。"""
    global _expectations
    if _expectations is None:
        _expectations = Expectations()
    return _expectations


# ══════════════════════════════════════════════════════════
# 文档库:通用 md 内容存储(盘前报告/研究过程/盘后总结/笔记)
# ══════════════════════════════════════════════════════════

class Documents:
    """通用文档库:运行时产出的 md 内容,按 (doc_type, name, trade_date) upsert。"""

    def __init__(self, schema: str = "public") -> None:
        self.schema = schema
        self._init_db()

    def save(self, doc_type: str, content: str, name: str = "",
             trade_date: str | None = None, ref_id: int | None = None) -> int:
        """写入/更新(同 doc_type+name+trade_date 覆盖)。返回文档 id。"""
        from datetime import datetime as _dt

        now = _dt.now().isoformat(timespec="seconds")
        with _connect(self.schema) as conn:
            row = conn.execute(
                "SELECT id FROM documents WHERE doc_type=%s AND name=%s"
                " AND COALESCE(trade_date,'')=%s",
                (doc_type, name, trade_date or ""),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE documents SET content=%s, ref_id=%s, updated_at=%s WHERE id=%s",
                    (content, ref_id, now, row["id"]),
                )
                doc_id = row["id"]
            else:
                r = conn.execute(
                    "INSERT INTO documents(doc_type,name,trade_date,ref_id,content,"
                    "created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (doc_type, name, trade_date, ref_id, content, now, now),
                ).fetchone()
                doc_id = r["id"]
        return doc_id

    def get(self, doc_type: str, name: str = "", trade_date: str = "") -> str | None:
        """取文档全文;无则 None(多条时取最新)。"""
        with _connect(self.schema) as conn:
            row = conn.execute(
                "SELECT content FROM documents WHERE doc_type=%s AND name=%s"
                " AND COALESCE(trade_date,'')=%s ORDER BY updated_at DESC LIMIT 1",
                (doc_type, name, trade_date or ""),
            ).fetchone()
        return row["content"] if row else None

    def list(self, doc_type: str | None = None, trade_date: str | None = None) -> list[dict]:
        """文档概览(id/类型/名称/日期/字数/更新时间),可按类型/日期过滤。"""
        where, params = [], []
        if doc_type:
            where.append("doc_type=%s")
            params.append(doc_type)
        if trade_date:
            where.append("COALESCE(trade_date,'')=%s")
            params.append(trade_date)
        sql = ("SELECT id,doc_type,name,trade_date,ref_id,"
               "LENGTH(content) AS size,updated_at FROM documents")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY updated_at DESC"
        with _connect(self.schema) as conn:
            return conn.execute(sql, params).fetchall()

    def delete(self, doc_type: str, trade_date: str) -> int:
        """删除某类型某日期的全部文档(重开回放实验前清旧轮日志),返回删除条数。"""
        with _connect(self.schema) as conn:
            cur = conn.execute(
                "DELETE FROM documents WHERE doc_type=%s AND COALESCE(trade_date,'')=%s",
                (doc_type, trade_date or ""),
            )
            return cur.rowcount

    # ── 内部 ────────────────────────────────────────────

    def _init_db(self) -> None:
        with _connect(self.schema) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    doc_type TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    trade_date TEXT,
                    ref_id INTEGER,
                    content TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS documents_lookup"
                " ON documents(doc_type, trade_date)"
            )


_documents: Documents | None = None


def default_documents() -> Documents:
    """默认文档库(单例,public schema)。"""
    global _documents
    if _documents is None:
        _documents = Documents()
    return _documents


# ══════════════════════════════════════════════════════════
# Prompt 版本库:本地 md 是唯一编辑面,变更同步入库管理版本
# ══════════════════════════════════════════════════════════

class PromptVersions:
    """prompt 版本管理:同 hash 不重复入库,变了才存新版本。"""

    def __init__(self, schema: str = "public") -> None:
        self.schema = schema
        self._init_db()

    def save(self, name: str, content: str) -> dict:
        """存入一版(内容未变则跳过)。返回 {name, version, changed, id}。"""
        import hashlib
        from datetime import datetime as _dt

        h = hashlib.sha256(content.encode()).hexdigest()
        with _connect(self.schema) as conn:
            row = conn.execute(
                "SELECT id, version, sha256 FROM prompt_versions"
                " WHERE name=%s ORDER BY version DESC LIMIT 1", (name,)
            ).fetchone()
            if row and row["sha256"] == h:
                return {"name": name, "version": row["version"], "changed": False, "id": row["id"]}
            r = conn.execute(
                "INSERT INTO prompt_versions(name, version, content, sha256, created_at)"
                " VALUES(%s,%s,%s,%s,%s) RETURNING id",
                (name, (row["version"] + 1) if row else 1, content, h,
                 _dt.now().isoformat(timespec="seconds")),
            ).fetchone()
            return {"name": name, "version": (row["version"] + 1) if row else 1,
                    "changed": True, "id": r["id"]}

    def versions(self, name: str | None = None) -> list[dict]:
        """版本列表(倒序);name 为空列全部 prompt 的最新一版。"""
        with _connect(self.schema) as conn:
            if name:
                return conn.execute(
                    "SELECT id, name, version, sha256, LENGTH(content) AS size, created_at"
                    " FROM prompt_versions WHERE name=%s ORDER BY version DESC", (name,)
                ).fetchall()
            return conn.execute(
                "SELECT DISTINCT ON (name) id, name, version, sha256,"
                " LENGTH(content) AS size, created_at"
                " FROM prompt_versions ORDER BY name, version DESC"
            ).fetchall()

    def get(self, name: str, version: int) -> str | None:
        """取某版全文。"""
        with _connect(self.schema) as conn:
            row = conn.execute(
                "SELECT content FROM prompt_versions WHERE name=%s AND version=%s",
                (name, version),
            ).fetchone()
        return row["content"] if row else None

    def _init_db(self) -> None:
        with _connect(self.schema) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS prompt_versions (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    name TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (name, version)
                )"""
            )


_prompt_versions: PromptVersions | None = None


def default_prompt_versions() -> PromptVersions:
    global _prompt_versions
    if _prompt_versions is None:
        _prompt_versions = PromptVersions()
    return _prompt_versions


# ══════════════════════════════════════════════════════════
# 档案袋(Runs):一次看盘一个袋子(核心设计§2)
# live=public schema(钱包连续/知识库正本);replay=独立 schema(钱包从零+知识快照+文档全袋内)
# ══════════════════════════════════════════════════════════

class Runs:
    """档案袋登记簿:建场/封存/列表/删除 + 预期库快照复制。"""

    def __init__(self, schema: str = "public") -> None:
        self.schema = schema
        self._init_db()

    def create(self, name: str, kind: str, trade_date: str,
               prompt_versions: dict) -> dict:
        """建档(同名已存在→ValueError)。kind=live/replay。
        replay 的隔离 schema 在建档后由调用方用 ensure_run_schema 创建。"""
        from datetime import datetime as _dt

        now = _dt.now().isoformat(timespec="seconds")
        with _connect(self.schema) as conn:
            try:
                r = conn.execute(
                    "INSERT INTO runs(name, kind, trade_date, schema_name, status,"
                    " prompt_versions, created_at)"
                    " VALUES(%s,%s,%s,'pending','running',%s,%s) RETURNING *",
                    (name, kind, trade_date,
                     _json_dumps(prompt_versions), now),
                ).fetchone()
            except psycopg.errors.UniqueViolation as e:
                raise ValueError(f"场次已存在:{name}(换个名字,或 replay-rm 删除旧场)") from e
        return r

    def get(self, name: str) -> dict | None:
        with _connect(self.schema) as conn:
            return conn.execute("SELECT * FROM runs WHERE name=%s", (name,)).fetchone()

    def set_schema(self, run_id: int, schema_name: str) -> None:
        with _connect(self.schema) as conn:
            conn.execute("UPDATE runs SET schema_name=%s WHERE id=%s",
                         (schema_name, run_id))

    def seal(self, run_id: int) -> None:
        from datetime import datetime as _dt
        with _connect(self.schema) as conn:
            conn.execute("UPDATE runs SET status='sealed', sealed_at=%s WHERE id=%s",
                         (_dt.now().isoformat(timespec="seconds"), run_id))

    def delete(self, name: str) -> int:
        """删场:先 drop 它的隔离 schema(袋子内一切随之消失),再删登记行。"""
        run = self.get(name)
        if run is None:
            return 0
        with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
            if run["schema_name"] and run["schema_name"] != "public":
                conn.execute(f'DROP SCHEMA IF EXISTS "{run["schema_name"]}" CASCADE')
        with _connect(self.schema) as conn:
            conn.execute("DELETE FROM runs WHERE id=%s", (run["id"],))
        return 1

    def list(self, kind: str | None = None, trade_date: str | None = None) -> list[dict]:
        where, params = [], []
        if kind:
            where.append("kind=%s")
            params.append(kind)
        if trade_date:
            where.append("trade_date=%s")
            params.append(trade_date)
        sql = "SELECT id, name, kind, trade_date, schema_name, status, prompt_versions, created_at, sealed_at FROM runs"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY id DESC"
        with _connect(self.schema) as conn:
            return conn.execute(sql, params).fetchall()

    # ── 预期库快照(开局把正本复制进袋子)────────────────

    @staticmethod
    def snapshot_expectations(source_schema: str, target_schema: str) -> str:
        """复制 expectations+pool_members(期望换新 id,池跟随)。
        返回快照指纹(sha256,对比两场起点是否一致用)。"""
        import hashlib

        src = Expectations(schema=source_schema)
        dst = Expectations(schema=target_schema)
        fingerprint = hashlib.sha256()
        with _connect(target_schema) as conn:
            conn.execute("DELETE FROM pool_members")
            conn.execute("DELETE FROM expectations")
            for e in src.get_all():
                row = _connect(source_schema).execute(
                    "SELECT * FROM expectations WHERE id=%s", (e["id"],)
                ).fetchone()
                r = conn.execute(
                    "INSERT INTO expectations(direction,event,thesis,catalyst,"
                    "fulfill_flag,fail_flag,stage,status,invalid_reason,created_at,updated_at)"
                    " VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (row["direction"], row["event"], row["thesis"], row["catalyst"],
                     row["fulfill_flag"], row["fail_flag"], row["stage"], row["status"],
                     row["invalid_reason"], row["created_at"], row["updated_at"]),
                ).fetchone()
                new_id = r["id"]
                for m in src.get(e["id"])["pool"]:
                    conn.execute(
                        "INSERT INTO pool_members(expectation_id,code,name,role,reason)"
                        " VALUES(%s,%s,%s,%s,%s)",
                        (new_id, m["code"], m["name"], m["role"], m["reason"]),
                    )
                fingerprint.update(
                    f"{e['id']}:{e['direction']}:{e['event']}:{e['stage']}:{e['status']};".encode()
                )
        return fingerprint.hexdigest()[:16]

    @staticmethod
    def copy_docs(source_schema: str, target_schema: str,
                  doc_types: tuple[str, ...], trade_date: str) -> int:
        """把某日的指定类型文档从正本复制进袋子(预案/收盘属于知识,袋子自包含用)。"""
        src, dst = Documents(schema=source_schema), Documents(schema=target_schema)
        n = 0
        for dt in doc_types:
            for d in src.list(dt, trade_date):
                content = src.get(dt, name=d["name"], trade_date=trade_date)
                if content:
                    dst.save(dt, content, name=d["name"], trade_date=trade_date,
                             ref_id=d["ref_id"])
                    n += 1
        return n

    def _init_db(self) -> None:
        with _connect(self.schema) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    name TEXT NOT NULL UNIQUE,
                    kind TEXT NOT NULL CHECK (kind IN ('live','replay')),
                    trade_date TEXT,
                    schema_name TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'running',
                    prompt_versions TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    sealed_at TEXT
                )"""
            )


def _json_dumps(obj) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


_runs: Runs | None = None


def default_runs() -> Runs:
    global _runs
    if _runs is None:
        _runs = Runs()
    return _runs


def bind_run_schema(schema: str) -> None:
    """把本进程的三个默认单例切到某场 schema(回放袋内读写全走这里)。"""
    global _default, _expectations, _documents
    _default = Account(schema=schema)
    _expectations = Expectations(schema=schema)
    _documents = Documents(schema=schema)
