"""core·自选组(平台通用件):唯一结构化原语(实现设计 §2/§7)。

- 命名的一篮子股票,成员带任意 fields(JSONB 自由字段:role/reason/任何系统的任何标注)
- 平台不知道字段含义;取值纪律由各系统 prompt 约定
- 每次成员变更落 versions(成员级事件,旧池永远可回放;as_of 查历史时点成员)
"""
import json
from datetime import datetime as _dt

from pydantic_ai import RunContext
from tabulate import tabulate

from trader.core.db import _connect
from trader.core.documents import _init_versions, _log_version
from trader.core.market import _fetch_quotes, _tool_error_text


class Watchlists:
    """自选组存储:按 (bag_id, name) 一组,成员按 code 去重。"""

    def __init__(self, schema: str = "public") -> None:
        self.schema = schema
        self._init_db()

    # ── 写 ──────────────────────────────────────────────

    def save(self, name: str, members: list[dict], bag_id: int = 0) -> None:
        """建组/追加/更新成员(按 code upsert,不改本次未提及的成员)。
        members=[{code, name?, fields?}];fields 是自由字典,整体替换该成员的 fields。"""
        now = _dt.now().isoformat(timespec="seconds")
        with _connect(self.schema) as conn:
            row = conn.execute(
                "SELECT 1 FROM watchlists WHERE bag_id=%s AND name=%s", (bag_id, name)
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO watchlists(bag_id, name, created_at, updated_at)"
                    " VALUES(%s,%s,%s,%s)", (bag_id, name, now, now)
                )
                _log_version(conn, "watchlist", _sid(bag_id, name), "create", {"name": name})
            for m in members:
                code = (m.get("code") or "").strip()
                if not code:
                    continue
                old = conn.execute(
                    "SELECT name, fields FROM watchlist_members"
                    " WHERE bag_id=%s AND list_name=%s AND code=%s", (bag_id, name, code)
                ).fetchone()
                conn.execute(
                    "INSERT INTO watchlist_members(bag_id, list_name, code, name, fields, updated_at)"
                    " VALUES(%s,%s,%s,%s,%s,%s)"
                    " ON CONFLICT (bag_id, list_name, code)"
                    " DO UPDATE SET name=excluded.name, fields=excluded.fields,"
                    " updated_at=excluded.updated_at",
                    (bag_id, name, code, m.get("name", ""),
                     json.dumps(m.get("fields") or {}, ensure_ascii=False), now),
                )
                _log_version(conn, "watchlist", _sid(bag_id, name),
                             "update" if old else "add",
                             {"code": code, "name": m.get("name", ""),
                              "fields": m.get("fields") or {}})
            conn.execute("UPDATE watchlists SET updated_at=%s WHERE bag_id=%s AND name=%s",
                         (now, bag_id, name))

    def remove_member(self, name: str, code: str, bag_id: int = 0) -> None:
        """从组中剔除一个成员(重新研究调整用;versions 落 remove 事件)。"""
        with _connect(self.schema) as conn:
            cur = conn.execute(
                "DELETE FROM watchlist_members"
                " WHERE bag_id=%s AND list_name=%s AND code=%s", (bag_id, name, code)
            )
            if cur.rowcount == 0:
                raise ValueError(f"成员不存在:{code}(自选组 {name})")
            _log_version(conn, "watchlist", _sid(bag_id, name), "remove", {"code": code})

    # ── 读 ──────────────────────────────────────────────

    def get(self, name: str, as_of: str = "", bag_id: int = 0) -> list[dict]:
        """组成员列表 [{code, name, fields}]。as_of(YYYYMMDD 或 ISO 日期)→
        从 versions 折叠出该日时点的成员(复盘/历史重建用)。"""
        if not as_of:
            with _connect(self.schema) as conn:
                return conn.execute(
                    "SELECT code, name, fields FROM watchlist_members"
                    " WHERE bag_id=%s AND list_name=%s ORDER BY code", (bag_id, name)
                ).fetchall()
        with _connect(self.schema) as conn:
            events = conn.execute(
                "SELECT action, payload, ts FROM versions"
                " WHERE subject_type='watchlist' AND subject_id=%s AND ts <= %s"
                " ORDER BY id", (_sid(bag_id, name), _as_of_ts(as_of))
            ).fetchall()
        members: dict[str, dict] = {}
        for e in events:
            p = e["payload"] or {}
            code = p.get("code", "")
            if e["action"] == "remove":
                members.pop(code, None)
            elif code:
                members[code] = {"code": code, "name": p.get("name", ""),
                                 "fields": p.get("fields", {})}
        return sorted(members.values(), key=lambda m: m["code"])

    def list_all(self, bag_id: int = 0) -> list[dict]:
        """全部自选组概览(名称/成员数/更新时间)。scan 快览用。"""
        with _connect(self.schema) as conn:
            return conn.execute(
                "SELECT w.name, COUNT(m.code) AS member_count, w.updated_at"
                " FROM watchlists w LEFT JOIN watchlist_members m"
                " ON m.bag_id = w.bag_id AND m.list_name = w.name"
                " WHERE w.bag_id=%s GROUP BY w.name, w.updated_at"
                " ORDER BY w.updated_at DESC", (bag_id,)
            ).fetchall()

    # ── 内部 ────────────────────────────────────────────

    def _init_db(self) -> None:
        with _connect(self.schema) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS watchlists (
                    bag_id INTEGER NOT NULL DEFAULT 0,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (bag_id, name)
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS watchlist_members (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    bag_id INTEGER NOT NULL DEFAULT 0,
                    list_name TEXT NOT NULL,
                    code TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    fields JSONB NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    UNIQUE (bag_id, list_name, code)
                )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS watchlist_members_lookup"
                         " ON watchlist_members(bag_id, list_name)")
            _init_versions(conn)


def _sid(bag_id: int, name: str) -> str:
    """versions.subject_id:袋子范围 + 组名。"""
    return f"{bag_id}:{name}"


def _as_of_ts(as_of: str) -> str:
    """YYYYMMDD → 当日 23:59:59(versions.ts 是 ISO,按天粒度比较)。"""
    d = as_of.replace("-", "")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}T23:59:59"


_watchlists: Watchlists | None = None


def default_watchlists() -> Watchlists:
    global _watchlists
    if _watchlists is None:
        _watchlists = Watchlists()
    return _watchlists


# ── 工具(AI 调用,通用)────────────────────────────────

def save_watchlist(ctx: RunContext[None], name: str, members: list[dict]) -> str:
    """建自选组/追加更新成员(按代码 upsert,不动本次未提及的成员)。
    name=组名(如 exp37);members=[{code, name, fields}];fields 是自由字典
    (如 {"role":"leader","reason":"封测直接受益"}),取值纪律由系统 prompt 约定。"""
    default_watchlists().save(name, members)
    n = len([m for m in members if (m.get("code") or "").strip()])
    return f"已写入自选组 {name}(本次 {n} 个成员,变更已留版本)"


def get_watchlist(ctx: RunContext[None], name: str, as_of: str = "") -> str:
    """查自选组成员。as_of=YYYYMMDD 时返回该日时点的成员(从版本史重建,
    复盘"当时的池"用);空=当前成员。"""
    try:
        data = default_watchlists().get(name, as_of=as_of)
    except Exception as e:  # noqa: BLE001 —— as_of 折叠异常给 AI 明确提示
        return f"查询失败:{e}"
    if not data:
        return f"自选组 {name} {'在 ' + as_of + ' 时' if as_of else ''}没有成员"
    rows = [[m["code"], m["name"] or "-", json.dumps(m["fields"], ensure_ascii=False)]
            for m in data]
    tag = f"(as_of {as_of},历史重建)" if as_of else ""
    return f"自选组 {name} {len(data)} 个成员{tag}\n" + tabulate(
        rows, headers=["代码", "名称", "字段"], tablefmt="plain")


def get_watchlist_quotes(ctx: RunContext[None], name: str, mode: str = "live",
                         date: str = "", time: str = "", as_of: str = "") -> str:
    """查自选组全部成员报价 + X/Y 上涨统计(池健康度的通用版)。
    mode=live/replay(replay 时 date 必填,time 可选)。as_of 用历史时点成员名单配当前查询。"""
    members = default_watchlists().get(name, as_of=as_of)
    if not members:
        return f"自选组 {name} 没有成员"
    quotes = _fetch_quotes(mode, [m["code"] for m in members], date, time or None)
    q_by = {q["code"]: (m, q) for m in members for q in quotes if q["code"] == m["code"]}
    up = sum(1 for _, (_, q) in q_by.items() if q.get("change_pct", 0) > 0)
    rows = [[q["code"], q["name"] or q["code"], q["price"], f"{q['change_pct']:+.2f}%"]
            for q in quotes]
    tag = f"(成员 as_of {as_of})" if as_of else ""
    return (f"自选组 {name} {tag}健康度: {up}/{len(quotes)} 上涨\n" + tabulate(
        rows, headers=["代码", "名称", "现价", "涨跌"], tablefmt="plain", floatfmt=".2f"))


def remove_watchlist_member(ctx: RunContext[None], name: str, code: str) -> str:
    """从自选组剔除一个成员(重新研究调整用,剔除后旧名单仍可 as_of 回看)。"""
    try:
        default_watchlists().remove_member(name, code)
    except ValueError as e:
        return f"拒绝:{e}"
    return f"已从 {name} 剔除:{code}"


# astock 失败(如盘后调 live)返回错误文本给 AI,不崩 run
get_watchlist_quotes = _tool_error_text(get_watchlist_quotes)
