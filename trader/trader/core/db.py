"""core·数据库连接。

- DATABASE_URL:环境变量(默认本地 stock_postgres 的 trader 库)
- _connect(schema):定位到指定 schema(老 schema 隔离路径仍用;新表走 public 行级 bag_id)
- schema_exists:老回放袋(run_* schema)是否存在的判断
"""
import os

import psycopg
from psycopg.rows import dict_row

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:password@localhost:5432/trader"
)


def _connect(schema: str = "public") -> psycopg.Connection:
    """连接并定位到指定 schema(不存在则建)。行返回 dict。"""
    conn = psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True)
    with conn.cursor() as cur:
        cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        cur.execute(f'SET search_path TO "{schema}"')
    conn.autocommit = False  # 之后恢复事务模式,with 块自动提交/回滚
    return conn


def schema_exists(name: str) -> bool:
    """某隔离 schema 是否存在(回放是否跑过的判断)。"""
    with psycopg.connect(DATABASE_URL, row_factory=dict_row) as conn:
        return conn.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name = %s", (name,)
        ).fetchone() is not None
