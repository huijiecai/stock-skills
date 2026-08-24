"""core·文档库(平台通用件):万物记忆,PG 持久化,行级 portfolio_id 隔离。

- 按 (doc_type, name, trade_date, portfolio_id) upsert;meta JSONB 供结构化过滤
- 交易系统的知识(如预期条目)就是这里的文档,平台不知道内容含义
- versions 统一版本史:每次写操作落一条事件(演化史/任意时点重建的机器层依据)
- portfolio_id 参数缺省 = 当前组合(core.context,engine 唯一注入)
"""
from datetime import datetime as _dt

from trader.core.context import current_portfolio, current_run, current_user
from trader.core.db import _connect


def _eff(portfolio_id: int | None) -> int:
    return portfolio_id if portfolio_id is not None else current_portfolio()


class Documents:
    """通用文档库:运行时产出的 md 内容,按 (doc_type, name, trade_date, portfolio_id) upsert。"""

    def __init__(self, schema: str = "public") -> None:
        self.schema = schema
        from trader.core.db import ensure_once
        ensure_once(f"documents:{schema}", self._init_db)

    def save(self, doc_type: str, content: str, name: str = "",
             trade_date: str | None = None, ref_id: int | None = None,
             meta: dict | None = None, portfolio_id: int | None = None) -> int:
        """写入/更新(同键覆盖,旧版进 versions)。返回文档 id。"""
        b = _eff(portfolio_id)
        now = _dt.now().isoformat(timespec="seconds")
        with _connect(self.schema) as conn:
            row = conn.execute(
                "SELECT id FROM documents WHERE doc_type=%s AND name=%s"
                " AND COALESCE(trade_date,'')=%s AND portfolio_id=%s",
                (doc_type, name, trade_date or "", b),
            ).fetchone()
            if row:
                conn.execute(
                    "UPDATE documents SET content=%s, ref_id=%s, meta=%s, updated_at=%s WHERE id=%s",
                    (content, ref_id, _meta_json(meta), now, row["id"]),
                )
                doc_id = row["id"]
            else:
                r = conn.execute(
                    "INSERT INTO documents(doc_type,name,trade_date,ref_id,content,"
                    "created_at,updated_at,meta,portfolio_id,user_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    " RETURNING id",
                    (doc_type, name, trade_date, ref_id, content, now, now,
                     _meta_json(meta), b, current_user()),
                ).fetchone()
                doc_id = r["id"]
            _log_version(conn, "document", doc_id, "save",
                         {"doc_type": doc_type, "name": name, "trade_date": trade_date,
                          "content": content, "meta": meta or {}}, portfolio=b)
        self._link_run(doc_id, "output")
        return doc_id

    def set_meta(self, doc_id: int, meta: dict) -> None:
        """浅合并更新 meta(只传变化的键;值传 None 表示删键)。"""
        import json as _json
        with _connect(self.schema) as conn:
            row = conn.execute("SELECT meta, portfolio_id, user_id FROM documents WHERE id=%s", (doc_id,)).fetchone()
            if row is None:
                raise ValueError(f"文档 {doc_id} 不存在")
            merged = dict(row["meta"] or {})
            for k, v in meta.items():
                if v is None:
                    merged.pop(k, None)
                else:
                    merged[k] = v
            conn.execute("UPDATE documents SET meta=%s, updated_at=%s WHERE id=%s",
                         (_json.dumps(merged, ensure_ascii=False),
                          _dt.now().isoformat(timespec="seconds"), doc_id))
            _log_version(conn, "document", doc_id, "meta", {"meta": merged},
                         portfolio=row["portfolio_id"], user=row["user_id"])
        self._link_run(doc_id, "output")

    def get(self, doc_type: str, name: str = "", trade_date: str = "",
            portfolio_id: int | None = None) -> str | None:
        """取文档全文;无则 None(多条时取最新)。"""
        row = self.resolve(doc_type, name, trade_date, portfolio_id)
        if row:
            self._link_run(row["id"], "input")
        return row["content"] if row else None

    def resolve(self, doc_type: str, name: str = "", trade_date: str = "",
                portfolio_id: int | None = None) -> dict | None:
        """按业务键取完整文档,不自动记输入边;阶段解析器会补充语义化槽位。"""
        with _connect(self.schema) as conn:
            return conn.execute(
                "SELECT * FROM documents WHERE doc_type=%s AND name=%s"
                " AND COALESCE(trade_date,'')=%s AND portfolio_id=%s"
                " ORDER BY updated_at DESC LIMIT 1",
                (doc_type, name, trade_date or "", _eff(portfolio_id)),
            ).fetchone()

    def resolve_id(self, doc_id: int, portfolio_id: int | None = None) -> dict | None:
        """按稳定 id 取完整文档,仍限制在当前/指定组合。"""
        with _connect(self.schema) as conn:
            return conn.execute(
                "SELECT * FROM documents WHERE id=%s AND portfolio_id=%s",
                (doc_id, _eff(portfolio_id)),
            ).fetchone()

    def for_run(self, run_id: int) -> list[dict]:
        """场次明确读写过的文档，供证据链 UI 展示。"""
        with _connect(self.schema) as conn:
            return conn.execute(
                "SELECT d.id,d.doc_type,d.name,d.trade_date,"
                " COALESCE(rd.meta_snapshot,d.meta) AS meta,d.created_at,"
                " COALESCE(rd.document_updated_at,d.updated_at) AS updated_at,"
                " rd.relation,rd.round,rd.stage,rd.slot,rd.source_stage,rd.source_output,"
                " rd.created_at AS linked_at,"
                " LENGTH(COALESCE(rd.content_snapshot,d.content)) AS size"
                " FROM run_documents rd JOIN documents d ON d.id=rd.document_id"
                " WHERE rd.run_id=%s ORDER BY rd.relation,rd.round,rd.id",
                (run_id,),
            ).fetchall()

    def get_for_run(self, run_id: int, document_id: int) -> dict | None:
        """Read one document through its run evidence edge, never by ambient portfolio."""
        with _connect(self.schema) as conn:
            return conn.execute(
                "SELECT d.id,d.doc_type,d.name,d.trade_date,"
                " COALESCE(rd.meta_snapshot,d.meta) AS meta,"
                " COALESCE(rd.content_snapshot,d.content) AS content,"
                " rd.relation,rd.round,rd.stage,rd.slot,rd.source_stage,rd.source_output,"
                " rd.created_at AS linked_at,"
                " COALESCE(rd.document_updated_at,d.updated_at) AS document_updated_at"
                " FROM run_documents rd JOIN documents d ON d.id=rd.document_id"
                " WHERE rd.run_id=%s AND rd.document_id=%s"
                " ORDER BY CASE rd.relation WHEN 'output' THEN 0 ELSE 1 END LIMIT 1",
                (run_id, document_id),
            ).fetchone()

    def link_run(self, doc_id: int, relation: str, stage: str = "", slot: str = "",
                 source_stage: str = "", source_output: str = "") -> None:
        """公开的证据边接口;阶段引擎可补充槽位,普通工具调用保持空槽位。"""
        self._link_run(doc_id, relation, stage, slot, source_stage, source_output)

    def linked_in_current_round(self, doc_id: int, relation: str) -> bool:
        """兼容旧 Prompt:判断它是否已经在本轮自行写过/读过目标文档。"""
        run_id = current_run()
        if not run_id:
            return False
        from trader.core.events import current_round
        with _connect(self.schema) as conn:
            row = conn.execute(
                "SELECT 1 FROM run_documents WHERE run_id=%s AND document_id=%s"
                " AND relation=%s AND round=%s",
                (run_id, doc_id, relation, current_round()),
            ).fetchone()
        return row is not None

    def _link_run(self, doc_id: int, relation: str, stage: str = "", slot: str = "",
                  source_stage: str = "", source_output: str = "") -> None:
        """尽力记录当前场次的文档读写；观测失败不能影响业务调用。"""
        run_id = current_run()
        if not run_id:
            return
        try:
            from trader.core.events import current_round
            with _connect(self.schema) as conn:
                conn.execute(
                    "INSERT INTO run_documents(run_id,document_id,relation,round,stage,slot,"
                    " source_stage,source_output,content_snapshot,meta_snapshot,"
                    " document_updated_at,created_at)"
                    " SELECT %s,d.id,%s,%s,%s,%s,%s,%s,d.content,d.meta,d.updated_at,%s"
                    " FROM documents d WHERE d.id=%s"
                    " ON CONFLICT(run_id,document_id,relation) DO UPDATE SET"
                    " round=GREATEST(run_documents.round,excluded.round),"
                    " stage=CASE WHEN excluded.stage<>'' THEN excluded.stage ELSE run_documents.stage END,"
                    " slot=CASE WHEN excluded.slot<>'' THEN excluded.slot ELSE run_documents.slot END,"
                    " source_stage=CASE WHEN excluded.source_stage<>'' THEN excluded.source_stage ELSE run_documents.source_stage END,"
                    " source_output=CASE WHEN excluded.source_output<>'' THEN excluded.source_output ELSE run_documents.source_output END",
                    (run_id, relation, current_round(), stage, slot,
                     source_stage, source_output, _dt.now().isoformat(timespec="seconds"), doc_id),
                )
        except Exception:  # noqa: BLE001 -- 证据观测失败不能杀执行
            pass

    def list(self, doc_type: str | None = None, trade_date: str | None = None,
             portfolio_id: int | None = None) -> list[dict]:
        """文档概览(id/类型/名称/日期/字数/更新时间/meta),可按类型/日期过滤。"""
        b = _eff(portfolio_id)
        where, params = ["portfolio_id=%s"], [b]
        if doc_type:
            where.append("doc_type=%s")
            params.append(doc_type)
        if trade_date:
            where.append("COALESCE(trade_date,'')=%s")
            params.append(trade_date)
        sql = ("SELECT id,doc_type,name,trade_date,ref_id,meta,"
               "LENGTH(content) AS size,created_at,updated_at FROM documents"
               " WHERE " + " AND ".join(where) + " ORDER BY updated_at DESC")
        with _connect(self.schema) as conn:
            return conn.execute(sql, params).fetchall()

    def delete(self, doc_type: str, trade_date: str, portfolio_id: int | None = None) -> int:
        """删除某类型某日期的全部文档(清旧轮日志用),返回删除条数。"""
        with _connect(self.schema) as conn:
            cur = conn.execute(
                "DELETE FROM documents WHERE doc_type=%s AND COALESCE(trade_date,'')=%s"
                " AND portfolio_id=%s",
                (doc_type, trade_date or "", _eff(portfolio_id)),
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
            conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS meta JSONB NOT NULL DEFAULT '{}'")
            conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS portfolio_id INTEGER NOT NULL DEFAULT 0")
            conn.execute("CREATE INDEX IF NOT EXISTS documents_portfolio ON documents(portfolio_id)")
            conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_id INTEGER NOT NULL DEFAULT 0")
            conn.execute("CREATE INDEX IF NOT EXISTS documents_user ON documents(user_id)")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS run_documents (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    run_id INTEGER NOT NULL,
                    document_id INTEGER NOT NULL,
                    relation TEXT NOT NULL CHECK (relation IN ('input','output')),
                    round INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    UNIQUE (run_id, document_id, relation)
                )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS run_documents_run ON run_documents(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS run_documents_document ON run_documents(document_id)")
            conn.execute("ALTER TABLE run_documents ADD COLUMN IF NOT EXISTS stage TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE run_documents ADD COLUMN IF NOT EXISTS slot TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE run_documents ADD COLUMN IF NOT EXISTS source_stage TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE run_documents ADD COLUMN IF NOT EXISTS source_output TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE run_documents ADD COLUMN IF NOT EXISTS content_snapshot TEXT")
            conn.execute("ALTER TABLE run_documents ADD COLUMN IF NOT EXISTS meta_snapshot JSONB")
            conn.execute("ALTER TABLE run_documents ADD COLUMN IF NOT EXISTS document_updated_at TEXT")
            _init_versions(conn)


def _meta_json(meta: dict | None) -> str:
    import json as _json
    return _json.dumps(meta or {}, ensure_ascii=False)


def _init_versions(conn) -> None:
    """统一版本史:documents/watchlist 每次写操作各落一条(实现设计 §7)。

    粒度=全量 payload(见 ADR-0006);subject_type 当前为 document/watchlist,
    将来任何要留痕的对象都往这里追加。
    """
    conn.execute(
        """CREATE TABLE IF NOT EXISTS versions (
            id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
            subject_type TEXT NOT NULL,
            subject_id TEXT NOT NULL,
            action TEXT NOT NULL,
            payload JSONB NOT NULL,
            ts TEXT NOT NULL,
            portfolio_id INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS versions_subject"
                 " ON versions(subject_type, subject_id)")
    conn.execute("ALTER TABLE versions ADD COLUMN IF NOT EXISTS portfolio_id INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS versions_portfolio ON versions(portfolio_id)")
    conn.execute("ALTER TABLE versions ADD COLUMN IF NOT EXISTS user_id INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS versions_user ON versions(user_id)")


def _log_version(conn, subject_type: str, subject_id, action: str,
                 payload: dict, portfolio: int = 0, user: int | None = None) -> None:
    """追加一条版本事件(与业务写操作同事务,业务回滚它也回滚)。"""
    import json as _json
    conn.execute(
        "INSERT INTO versions(subject_type, subject_id, action, payload, ts, portfolio_id, user_id)"
        " VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (subject_type, str(subject_id), action,
         _json.dumps(payload, ensure_ascii=False),
         _dt.now().isoformat(timespec="seconds"), portfolio,
         current_user() if user is None else user),
    )


_documents: Documents | None = None


def default_documents() -> Documents:
    """默认文档库单例(读写自动带当前组合)。"""
    global _documents
    if _documents is None:
        _documents = Documents()
    return _documents
