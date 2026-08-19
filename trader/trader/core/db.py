"""core·数据库连接。

- DATABASE_URL:环境变量(默认本地 stock_postgres 的 trader 库)
- _connect(schema):连接定位 schema(测试隔离用);生产数据全在 public 行级 bag_id
- schema_exists:schema 是否存在(测试/老数据探查)
- ensure_once:DDL 幂等初始化进程内只跑一次——每连接跑 DDL 会与并发写抢
  AccessExclusiveLock 造成死锁(8/19 实测两次靠重试自愈),多用户下必须根治
"""
import os
import threading

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5432/trader"
)

_init_lock = threading.RLock()  # 可重入:_init_db 内部再建子表(如 Ledgers→Bags)不自锁
_init_done: set[str] = set()


def ensure_once(key: str, init_fn) -> None:
    """store 的 _init_db 进程内只执行一次(key=存储类:schema)。"""
    with _init_lock:
        if key in _init_done:
            return
        init_fn()
        _init_done.add(key)


def _connect(schema: str = "public") -> psycopg.Connection:
    """连接并定位到指定 schema(不存在则建)。行返回 dict。"""
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True)
    with conn.cursor() as cur:
        cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        cur.execute(f'SET search_path TO "{schema}"')
    conn.autocommit = False  # 之后恢复事务模式,with 块自动提交/回滚
    return conn


def schema_exists(name: str) -> bool:
    """某隔离 schema 是否存在(测试隔离/老数据探查)。"""
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        return conn.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (name,)
        ).fetchone() is not None
