"""core·场次登记(平台通用件):一场一次登记,封面(prompt 版本指纹/系统/时钟/组合)+ metrics。

一场执行的完整身份五元组:system_id × stage × user_id × clock × portfolio_id。
kind 为推导字段(single 由 stage 决定;live=实时钟+实盘组合;replay=模拟钟+实验组合),
由 derive_kind() 统一计算,调用方不再手写。
"""
import json
from datetime import datetime as _dt

import psycopg

from trader.core.db import _connect, ensure_once


def derive_kind(stage_kind: str, clock: str, portfolio_type: str) -> str:
    """推导场次类型:stage(single/loop) × 时钟(real/simulated) × 组合角色。"""
    if stage_kind == "single":
        return "single"
    if clock == "simulated":
        return "replay"
    if portfolio_type == "main":
        return "live"
    return "paper"   # 实时钟 + 模拟组合(模拟盘)


class Runs:
    """场次登记簿:建场/封存/列表/删除(行级组合隔离)。"""

    def __init__(self, schema: str = "public") -> None:
        self.schema = schema
        ensure_once(f"runs:{schema}", self._init_db)

    def create(self, slug: str, kind: str, trade_date: str,
               prompt_versions: dict, system_id: int = 1,
               user_id: int = 0, stage: str = "",
               clock: str = "real", clock_date: str = "",
               portfolio_id: int = 0) -> dict:
        """建档(同名已存在→ValueError)。kind 由 derive_kind 推导后传入;
        portfolio_id 建档即绑(实盘=系统实盘组合,实验=新开组合)。"""
        now = _dt.now().isoformat(timespec="seconds")
        with _connect(self.schema) as conn:
            try:
                r = conn.execute(
                    "INSERT INTO runs(user_id, slug, kind, trade_date, status,"
                    " prompt_versions, system_id, stage, clock, clock_date,"
                    " portfolio_id, created_at)"
                    " VALUES(%s,%s,%s,%s,'running',%s,%s,%s,%s,%s,%s,%s) RETURNING *",
                    (user_id, slug, kind, trade_date,
                     json.dumps(prompt_versions, ensure_ascii=False), system_id, stage,
                     clock, clock_date or None, portfolio_id, now),
                ).fetchone()
            except psycopg.errors.UniqueViolation as e:
                raise ValueError(f"场次已存在:{slug}(换个名字,或 replay-rm 删除旧场)") from e
        return r

    def get(self, slug: str, user_id: int = 0) -> dict | None:
        with _connect(self.schema) as conn:
            return conn.execute("SELECT * FROM runs WHERE user_id=%s AND slug=%s",
                                (user_id, slug)).fetchone()

    def get_by_id(self, run_id: int) -> dict | None:
        with _connect(self.schema) as conn:
            return conn.execute("SELECT * FROM runs WHERE id=%s", (run_id,)).fetchone()

    def set_status(self, run_id: int, status: str) -> None:
        """状态流转(running→stopping→sealed);engine 轮询 stopping 实现优雅停止。"""
        with _connect(self.schema) as conn:
            conn.execute("UPDATE runs SET status=%s WHERE id=%s", (status, run_id))

    def set_fingerprint(self, run_id: int, fingerprint: str) -> None:
        with _connect(self.schema) as conn:
            conn.execute("UPDATE runs SET fingerprint=%s WHERE id=%s", (fingerprint, run_id))

    def seal(self, run_id: int, metrics: dict | None = None) -> None:
        """封场;metrics(指标)一并落库。"""
        now = _dt.now().isoformat(timespec="seconds")
        with _connect(self.schema) as conn:
            if metrics is not None:
                conn.execute(
                    "UPDATE runs SET status='sealed', sealed_at=%s, metrics=%s WHERE id=%s",
                    (now, json.dumps(metrics, ensure_ascii=False), run_id))
            else:
                conn.execute("UPDATE runs SET status='sealed', sealed_at=%s WHERE id=%s",
                             (now, run_id))

    def delete(self, slug: str, user_id: int = 0) -> int:
        """删场(按用户+名):行级组合整体销毁(一个事务)再删登记行。"""
        from trader.core.portfolios import Portfolios
        run = self.get(slug, user_id)
        if run is None:
            return 0
        if run.get("portfolio_id"):
            Portfolios(self.schema).delete(run["portfolio_id"])
        with _connect(self.schema) as conn:
            conn.execute("DELETE FROM runs WHERE id=%s", (run["id"],))
        return 1

    def list(self, kind: str | None = None, trade_date: str | None = None,
             user_id: int | None = None, system: str | None = None) -> list[dict]:
        """列表(倒序)。system 参数为系统 slug(边界解析:join systems 取 slug,
        对外呈现仍是 slug,内部已用代理键关联)。"""
        where, params = [], []
        if user_id is not None:
            where.append("r.user_id=%s")
            params.append(user_id)
        if system:
            where.append("s.slug=%s")
            params.append(system)
        if kind:
            where.append("r.kind=%s")
            params.append(kind)
        if trade_date:
            where.append("r.trade_date=%s")
            params.append(trade_date)
        sql = ("SELECT r.id, r.user_id, r.slug, r.kind, r.trade_date, r.portfolio_id,"
               " r.status, s.slug AS system, r.stage, r.clock, r.clock_date,"
               " r.prompt_versions, r.fingerprint, r.metrics, r.created_at, r.sealed_at"
               " FROM runs r LEFT JOIN systems s ON s.id=r.system_id")
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY r.id DESC"
        with _connect(self.schema) as conn:
            return conn.execute(sql, params).fetchall()

    def _init_db(self) -> None:
        with _connect(self.schema) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS runs (
                    id INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
                    slug TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    trade_date TEXT,
                    status TEXT NOT NULL DEFAULT 'running',
                    prompt_versions TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    sealed_at TEXT
                )"""
            )
            conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS system_id INTEGER NOT NULL DEFAULT 1")
            conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS stage TEXT NOT NULL DEFAULT ''")
            conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS portfolio_id INTEGER NOT NULL DEFAULT 0")
            conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS metrics JSONB")
            conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS fingerprint TEXT")
            conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS user_id INTEGER NOT NULL DEFAULT 0")
            conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS clock TEXT NOT NULL DEFAULT 'real'")
            conn.execute("ALTER TABLE runs ADD COLUMN IF NOT EXISTS clock_date TEXT")
            conn.execute("ALTER TABLE runs DROP CONSTRAINT IF EXISTS runs_name_key")
            conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS runs_user_slug ON runs(user_id, slug)")


_runs: Runs | None = None


def default_runs() -> Runs:
    global _runs
    if _runs is None:
        _runs = Runs()
    return _runs
