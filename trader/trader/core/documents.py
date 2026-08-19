"""core·文档库(平台通用件):万物记忆,PG 持久化,行级 bag_id 隔离。

- 按 (doc_type, name, trade_date, bag_id) upsert;meta JSONB 供结构化过滤
- 交易系统的知识(如预期条目)就是这里的文档,平台不知道内容含义
- versions 统一版本史:每次写操作落一条事件(演化史/任意时点重建的机器层依据)
- bag_id 参数缺省 = 当前袋子(core.context,engine 唯一注入)
"""
from datetime import datetime as _dt

from trader.core.context import current_bag, current_user
from trader.core.db import _connect


def _eff(bag_id: int | None) -> int:
    return bag_id if bag_id is not None else current_bag()


class Documents:
    """通用文档库:运行时产出的 md 内容,按 (doc_type, name, trade_date, bag_id) upsert。"""

    def __init__(self, schema: str = "public") -> None:
        self.schema = schema
        from trader.core.db import ensure_once
        ensure_once(f"documents:{schema}", self._init_db)

    def save(self, doc_type: str, content: str, name: str = "",
             trade_date: str | None = None, ref_id: int | None = None,
             meta: dict | None = None, bag_id: int | None = None) -> int:
        """写入/更新(同键覆盖,旧版进 versions)。返回文档 id。"""
        b = _eff(bag_id)
        now = _dt.now().isoformat(timespec="seconds")
        with _connect(self.schema) as conn:
            row = conn.execute(
                "SELECT id FROM documents WHERE doc_type=%s AND name=%s"
                " AND COALESCE(trade_date,'')=%s AND bag_id=%s",
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
                    "created_at,updated_at,meta,bag_id,user_id) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    " RETURNING id",
                    (doc_type, name, trade_date, ref_id, content, now, now,
                     _meta_json(meta), b, current_user()),
                ).fetchone()
                doc_id = r["id"]
            _log_version(conn, "document", doc_id, "save",
                         {"doc_type": doc_type, "name": name, "trade_date": trade_date,
                          "content": content, "meta": meta or {}}, bag=b)
        return doc_id

    def set_meta(self, doc_id: int, meta: dict) -> None:
        """浅合并更新 meta(只传变化的键;值传 None 表示删键)。"""
        import json as _json
        with _connect(self.schema) as conn:
            row = conn.execute("SELECT meta, bag_id, user_id FROM documents WHERE id=%s", (doc_id,)).fetchone()
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
                         bag=row["bag_id"], user=row["user_id"])

    def get(self, doc_type: str, name: str = "", trade_date: str = "",
            bag_id: int | None = None) -> str | None:
        """取文档全文;无则 None(多条时取最新)。"""
        with _connect(self.schema) as conn:
            row = conn.execute(
                "SELECT content FROM documents WHERE doc_type=%s AND name=%s"
                " AND COALESCE(trade_date,'')=%s AND bag_id=%s ORDER BY updated_at DESC LIMIT 1",
                (doc_type, name, trade_date or "", _eff(bag_id)),
            ).fetchone()
        return row["content"] if row else None

    def list(self, doc_type: str | None = None, trade_date: str | None = None,
             bag_id: int | None = None) -> list[dict]:
        """文档概览(id/类型/名称/日期/字数/更新时间/meta),可按类型/日期过滤。"""
        b = _eff(bag_id)
        where, params = ["bag_id=%s"], [b]
        if doc_type:
            where.append("doc_type=%s")
            params.append(doc_type)
        if trade_date:
            where.append("COALESCE(trade_date,'')=%s")
            params.append(trade_date)
        sql = ("SELECT id,doc_type,name,trade_date,ref_id,meta,"
               "LENGTH(content) AS size,updated_at FROM documents"
               " WHERE " + " AND ".join(where) + " ORDER BY updated_at DESC")
        with _connect(self.schema) as conn:
            return conn.execute(sql, params).fetchall()

    def delete(self, doc_type: str, trade_date: str, bag_id: int | None = None) -> int:
        """删除某类型某日期的全部文档(清旧轮日志用),返回删除条数。"""
        with _connect(self.schema) as conn:
            cur = conn.execute(
                "DELETE FROM documents WHERE doc_type=%s AND COALESCE(trade_date,'')=%s"
                " AND bag_id=%s",
                (doc_type, trade_date or "", _eff(bag_id)),
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
            conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS bag_id INTEGER NOT NULL DEFAULT 0")
            conn.execute("CREATE INDEX IF NOT EXISTS documents_bag ON documents(bag_id)")
            conn.execute("ALTER TABLE documents ADD COLUMN IF NOT EXISTS user_id INTEGER NOT NULL DEFAULT 0")
            conn.execute("CREATE INDEX IF NOT EXISTS documents_user ON documents(user_id)")
            _init_versions(conn)


def _meta_json(meta: dict | None) -> str:
    import json as _json
    return _json.dumps(meta or {}, ensure_ascii=False)


def _init_versions(conn) -> None:
    """统一版本史:documents/watchlist 每次写操作各落一条(实现设计 §7)。

    粒度=全量 payload(附录 4 已定);subject_type 当前为 document/watchlist,
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
            bag_id INTEGER NOT NULL DEFAULT 0
        )"""
    )
    conn.execute("CREATE INDEX IF NOT EXISTS versions_subject"
                 " ON versions(subject_type, subject_id)")
    conn.execute("ALTER TABLE versions ADD COLUMN IF NOT EXISTS bag_id INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS versions_bag ON versions(bag_id)")
    conn.execute("ALTER TABLE versions ADD COLUMN IF NOT EXISTS user_id INTEGER NOT NULL DEFAULT 0")
    conn.execute("CREATE INDEX IF NOT EXISTS versions_user ON versions(user_id)")


def _log_version(conn, subject_type: str, subject_id, action: str,
                 payload: dict, bag: int = 0, user: int | None = None) -> None:
    """追加一条版本事件(与业务写操作同事务,业务回滚它也回滚)。"""
    import json as _json
    conn.execute(
        "INSERT INTO versions(subject_type, subject_id, action, payload, ts, bag_id, user_id)"
        " VALUES(%s,%s,%s,%s,%s,%s,%s)",
        (subject_type, str(subject_id), action,
         _json.dumps(payload, ensure_ascii=False),
         _dt.now().isoformat(timespec="seconds"), bag,
         current_user() if user is None else user),
    )


_documents: Documents | None = None


def default_documents() -> Documents:
    """默认文档库单例(读写自动带当前袋子)。"""
    global _documents
    if _documents is None:
        _documents = Documents()
    return _documents
