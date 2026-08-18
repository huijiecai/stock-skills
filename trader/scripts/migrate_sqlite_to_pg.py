"""一次性迁移:data/account.db(SQLite)→ PostgreSQL public schema。

保 id、跑完后对齐各自增序列。幂等:重复跑前先清空目标表。
用法:cd trader && uv run python scripts/migrate_sqlite_to_pg.py
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from trader.core.db import _connect  # noqa: E402

SRC = Path(__file__).resolve().parent.parent / "data" / "account.db"


def rows(cur):
    cur_rows = cur.fetchall()
    return [dict(r) for r in cur_rows]


def main() -> None:
    Account(), Expectations(), Documents()  # 触发 public schema 建表
    lite = sqlite3.connect(SRC)
    lite.row_factory = sqlite3.Row
    with _connect("public") as pg:
        # 清空目标(幂等)
        for t in ("fills", "positions", "pool_members", "expectations", "documents", "account"):
            pg.execute(f"DELETE FROM {t}")

        a = rows(lite.execute("SELECT * FROM account"))
        for r in a:
            pg.execute("DELETE FROM account WHERE id=1")
            pg.execute("INSERT INTO account(id, cash_cents) VALUES(1, %s)", (r["cash_cents"],))

        for t, cols in [
            ("positions", ["code", "name", "quantity", "sellable", "avg_cost_cents", "bought_on"]),
            ("fills", ["id", "code", "side", "quantity", "price_cents", "cash_before_cents",
                       "cash_after_cents", "position_before", "position_after", "created_at",
                       "reason", "expectation_id", "name", "trade_time"]),
            ("expectations", ["id", "direction", "event", "thesis", "catalyst", "fulfill_flag",
                              "fail_flag", "stage", "status", "invalid_reason",
                              "created_at", "updated_at"]),
            ("pool_members", ["id", "expectation_id", "code", "name", "role", "reason"]),
            ("documents", ["id", "doc_type", "name", "trade_date", "ref_id", "content",
                           "created_at", "updated_at"]),
        ]:
            data = rows(lite.execute(f"SELECT {','.join(cols)} FROM {t}"))
            ph = ",".join(["%s"] * len(cols))
            for r in data:
                pg.execute(f"INSERT INTO {t}({','.join(cols)}) VALUES({ph})",
                           tuple(r[c] for c in cols))
            print(f"  {t}: {len(data)} 行")

        # 对齐自增序列到当前最大 id
        for t in ("fills", "expectations", "pool_members", "documents"):
            pg.execute(
                f"SELECT setval(pg_get_serial_sequence('{t}','id'),"
                f" COALESCE((SELECT MAX(id) FROM {t}), 0) + 1, false)"
            )
    print("迁移完成 ✓")


if __name__ == "__main__":
    main()
