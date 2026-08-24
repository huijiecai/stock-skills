"""数据库连接与初始化守卫(全项目唯一出入口)。

- DATABASE_URL:环境变量(默认本地 stock_postgres 的 trader 库)
- 连接池:进程级 psycopg_pool 单例(见 ADR-0010);store 一律
  `with _connect(schema) as conn:`,借出/归还而非每调用新建
- TRADER_SCHEMA:只把默认 "public" 重定向到该值(pytest 在 conftest 设 t_api,
  根治测试直写 public,见 ADR-0007);显式传入的 t_* 等 schema 不受影响
- schema_exists:schema 是否存在(测试/老数据探查),按名字直查不经重定向
- ensure_once:DDL 幂等初始化进程内只跑一次(并发 DDL 死锁教训,见 ADR-0008)
"""
import atexit
import os
import threading
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5432/trader"
)
POOL_MAX = int(os.environ.get("TRADER_DB_POOL_MAX", "8"))

_init_lock = threading.RLock()  # 可重入:_init_db 内部再建子表(如 Ledgers→Bags)不自锁
_init_done: set[str] = set()

_pool: ConnectionPool | None = None
_pool_lock = threading.Lock()


def ensure_once(key: str, init_fn) -> None:
    """store 的 _init_db 进程内只执行一次(key=存储类:schema)。"""
    with _init_lock:
        if key in _init_done:
            return
        init_fn()
        _init_done.add(key)


def _get_pool() -> ConnectionPool:
    """进程级连接池单例。惰性建池:import 本模块不触网。"""
    global _pool
    with _pool_lock:
        if _pool is None:
            pool = ConnectionPool(
                DATABASE_URL,
                min_size=1,
                max_size=POOL_MAX,
                kwargs={"row_factory": dict_row},
                # checkout 前探活,防 DB 重启后拿到死连接(会换掉坏的自动补新的)
                check=ConnectionPool.check_connection,
                open=False,
            )
            pool.open(wait=True)  # 首连就绪再放行,DB 不在线在第一次用时即报错
            _pool = pool
    return _pool


def close_pool() -> None:
    """进程退出前显式关池(atexit 注册)。

    不显式关,池对象靠 __del__ 兜底——此时解释器线程设施半拆除,
    调度线程 5s 内停不掉,退出时白出一行警告噪音(CLI 一次性脚本常见)。
    """
    global _pool
    with _pool_lock:
        pool, _pool = _pool, None
    if pool is not None:
        pool.close()


atexit.register(close_pool)


def _resolve(schema: str) -> str:
    """TRADER_SCHEMA 只重定向默认 "public";显式 t_* 等 schema 原样通过。"""
    override = os.environ.get("TRADER_SCHEMA")
    return override if (override and schema == "public") else schema


@contextmanager
def _connect(schema: str = "public"):
    """借一条池连接并定位到指定 schema(不存在则建)。行返回 dict。

    事务语义与改造前完全一致(pool.connection 内嵌 with conn):
    块内无异常退出自动提交,异常自动回滚;连接归还池而非关闭。
    search_path 每次借用都重设——池连接被各 schema 复用,
    而 SET 提交后会跨事务留存在连接上,不重设会串 schema。
    """
    schema = _resolve(schema)
    with _get_pool().connection() as conn:
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        conn.execute(f'SET search_path TO "{schema}"')
        yield conn


def schema_exists(name: str) -> bool:
    """某隔离 schema 是否存在(测试隔离/老数据探查)。按名字直查,不经 _resolve。"""
    with _get_pool().connection() as conn:
        return conn.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (name,)
        ).fetchone() is not None
