"""存储层(C1 过渡形态,docs/实现设计.md §1):

- 通用件已拆去 core/(ledger/documents/promptver/db),这里 re-export 保持旧 import 路径可用
- Expectations(预期库)是交易系统私有,待 C3 数据化(documents+watchlists)后删除
- Runs(档案袋登记)待 C2 engine 接管 bag_id 行级后泛化

旧调用方(tools/viewer/runner/tests)不需要任何改动。
"""

import psycopg

from trader.core.db import DATABASE_URL, _connect, schema_exists
from trader.core.documents import Documents
from trader.core.ledger import INITIAL_CASH, Account, AccountError
from trader.core.promptver import PromptVersions


# ── 默认账户(单例)───────────────────────────────────

_default: Account | None = None


def default_account() -> Account:
    """默认账户(单例,public schema=实盘):tools 层共用,保证读写一致。"""
    global _default
    if _default is None:
        _default = Account()
    return _default


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


_documents: Documents | None = None


def default_documents() -> Documents:
    """默认文档库(单例,public schema)。"""
    global _documents
    if _documents is None:
        _documents = Documents()
    return _documents


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
