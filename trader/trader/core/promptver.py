"""core·指令库(平台通用件):prompts 身份表 + prompt_versions 内容表,版本不可变。

三层身份(工作台架构 §3,GitHub repo 模式):
- prompts.id:代理键(join 用)
- prompts.slug:机器名,`[a-z0-9_-]`,不可变;manifest.stages[].prompt 引用它
- prompts.display_name:显示名,可中文、可随时改

命名空间 = (system, slug):同用户两个系统各有 premarket,互不相干。
用户级指令(如 _coach 教练风格):system_id IS NULL + user_id 命名空间。
"""
import hashlib

from trader.core.db import _connect, ensure_once


class PromptVersions:
    """指令版本管理:身份自动 ensure,同 hash 不重复入库,变了才存新版本。"""

    def __init__(self, schema: str = "public") -> None:
        self.schema = schema
        ensure_once(f"promptver:{schema}", self._init_db)

    # ── 身份层(prompts 表)──────────────────────────────

    def ensure_prompt(self, system_id: int | None, slug: str,
                      display_name: str = "", user_id: int = 0) -> dict:
        """取或建指令身份;display_name 有值则更新(显示名可随时改)。"""
        from datetime import datetime as _dt

        row = self.get_prompt(system_id, slug, user_id)
        if row is None:
            with _connect(self.schema) as conn:
                row = conn.execute(
                    "INSERT INTO prompts(system_id, user_id, slug, display_name, created_at)"
                    " VALUES(%s,%s,%s,%s,%s) RETURNING *",
                    (system_id, user_id if system_id is None else 0, slug,
                     display_name or slug, _dt.now().isoformat(timespec="seconds")),
                ).fetchone()
        elif display_name and display_name != row["display_name"]:
            with _connect(self.schema) as conn:
                row = conn.execute(
                    "UPDATE prompts SET display_name=%s WHERE id=%s RETURNING *",
                    (display_name, row["id"])).fetchone()
        return row

    def get_prompt(self, system_id: int | None, slug: str,
                   user_id: int = 0) -> dict | None:
        if system_id is not None:
            sql = "SELECT * FROM prompts WHERE system_id=%s AND slug=%s"
            args = (system_id, slug)
        else:
            sql = "SELECT * FROM prompts WHERE system_id IS NULL AND user_id=%s AND slug=%s"
            args = (user_id, slug)
        with _connect(self.schema) as conn:
            return conn.execute(sql, args).fetchone()

    def list_prompts(self, system_id: int | None = None,
                     user_id: int = 0) -> list[dict]:
        """指令身份列表(system_id=None 列用户级)。"""
        if system_id is not None:
            sql, args = "SELECT * FROM prompts WHERE system_id=%s ORDER BY slug", (system_id,)
        else:
            sql, args = ("SELECT * FROM prompts WHERE system_id IS NULL AND user_id=%s"
                         " ORDER BY slug", (user_id,))
        with _connect(self.schema) as conn:
            return conn.execute(sql, args).fetchall()

    # ── 内容层(prompt_versions 表)─────────────────────

    def save(self, system_id: int | None, slug: str, content: str,
             user_id: int = 0, display_name: str = "") -> dict:
        """存入一版(内容未变则跳过;身份不存在则自动建)。返回 {slug, version, changed, id}。"""
        from datetime import datetime as _dt

        prompt = self.ensure_prompt(system_id, slug, display_name, user_id)
        h = hashlib.sha256(content.encode()).hexdigest()
        with _connect(self.schema) as conn:
            row = conn.execute(
                "SELECT id, version, sha256 FROM prompt_versions"
                " WHERE prompt_id=%s ORDER BY version DESC LIMIT 1",
                (prompt["id"],)).fetchone()
            if row and row["sha256"] == h:
                return {"slug": slug, "version": row["version"], "changed": False,
                        "id": row["id"]}
            version = (row["version"] + 1) if row else 1
            r = conn.execute(
                "INSERT INTO prompt_versions(prompt_id, version, content, sha256, created_at)"
                " VALUES(%s,%s,%s,%s,%s) RETURNING id",
                (prompt["id"], version, content, h,
                 _dt.now().isoformat(timespec="seconds")),
            ).fetchone()
            return {"slug": slug, "version": version, "changed": True, "id": r["id"]}

    def latest(self, system_id: int | None, slug: str, user_id: int = 0) -> str | None:
        """取某指令最新版全文(运行时加载入口)。无则 None。"""
        prompt = self.get_prompt(system_id, slug, user_id)
        if prompt is None:
            return None
        with _connect(self.schema) as conn:
            row = conn.execute(
                "SELECT content FROM prompt_versions WHERE prompt_id=%s"
                " ORDER BY version DESC LIMIT 1", (prompt["id"],)).fetchone()
        return row["content"] if row else None

    def versions(self, system_id: int | None, slug: str,
                 user_id: int = 0) -> list[dict]:
        """某指令版本列表(倒序)。"""
        prompt = self.get_prompt(system_id, slug, user_id)
        if prompt is None:
            return []
        with _connect(self.schema) as conn:
            return conn.execute(
                "SELECT id, prompt_id, version, sha256, LENGTH(content) AS size, created_at"
                " FROM prompt_versions WHERE prompt_id=%s ORDER BY version DESC",
                (prompt["id"],)).fetchall()

    def get(self, system_id: int | None, slug: str, version: int,
            user_id: int = 0) -> str | None:
        """取某版全文。"""
        prompt = self.get_prompt(system_id, slug, user_id)
        if prompt is None:
            return None
        with _connect(self.schema) as conn:
            row = conn.execute(
                "SELECT content FROM prompt_versions"
                " WHERE prompt_id=%s AND version=%s", (prompt["id"], version)).fetchone()
        return row["content"] if row else None

    def _init_db(self) -> None:
        with _connect(self.schema) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS prompts (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    system_id INTEGER,
                    user_id INTEGER NOT NULL DEFAULT 0,
                    slug TEXT NOT NULL,
                    display_name TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                )"""
            )
            # 命名空间:系统级 (system_id, slug);用户级 (user_id, slug)——NULL 不进唯一键
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS prompts_system_slug ON prompts(system_id, slug)"
                " WHERE system_id IS NOT NULL")
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS prompts_user_slug ON prompts(user_id, slug)"
                " WHERE system_id IS NULL")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS prompt_versions (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    prompt_id INTEGER NOT NULL REFERENCES prompts(id),
                    version INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (prompt_id, version)
                )"""
            )


_prompt_versions: PromptVersions | None = None


def default_prompt_versions() -> PromptVersions:
    global _prompt_versions
    if _prompt_versions is None:
        _prompt_versions = PromptVersions()
    return _prompt_versions
