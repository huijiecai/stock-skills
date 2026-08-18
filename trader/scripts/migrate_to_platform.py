"""一次性迁移:老预期库 → 平台通用件(documents + watchlists),完成后清除旧结构。

按《实现设计》§4/§7 与用户指令:迁移完成后,新模型里不存在的表和字段全部删除。
幂等:重复运行时已迁移/已删除的部分自动跳过。

步骤:
1. 正本现金:老 account 表 → wallets(bag 0)
2. expectations + pool_members → documents('expectation') + watchlists(bag 0,含 versions 初始事件)
3. 清除:expectations / pool_members / account 表;fills.expectation_id 列;runs.schema_name 列;
   老隔离 schema(run_*/replay_*)与其 runs 登记行
"""
import json
import sys
from datetime import datetime

sys.path.insert(0, ".")

import psycopg

from trader.core.db import DATABASE_URL, _connect
from trader.core.documents import _init_versions, _log_version, _meta_json


def table_exists(conn, schema: str, table: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM information_schema.tables"
        " WHERE table_schema=%s AND table_name=%s", (schema, table)
    ).fetchone() is not None


def column_exists(conn, schema: str, table: str, column: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM information_schema.columns"
        " WHERE table_schema=%s AND table_name=%s AND column_name=%s",
        (schema, table, column)
    ).fetchone() is not None


def migrate() -> None:
    now = datetime.now().isoformat(timespec="seconds")
    # 先确保新模型表结构齐(versions.bag_id / watchlists / wallets 等)
    from trader.core.documents import Documents
    from trader.core.ledger import Account
    from trader.core.runs import Runs
    from trader.core.watchlist import Watchlists
    Documents(); Account(); Runs(); Watchlists()
    with _connect() as conn:
        # ① 正本现金 → wallets
        if table_exists(conn, "public", "account"):
            cash = conn.execute("SELECT cash_cents FROM account WHERE id=1").fetchone()
            if cash:
                conn.execute(
                    "UPDATE wallets SET cash_cents=%s WHERE bag_id=0", (cash["cash_cents"],))
                print(f"① 正本现金迁移:wallets(0) = ¥{cash['cash_cents'] / 100:,.2f}")

        # ② 预期库 → documents + watchlists
        if table_exists(conn, "public", "expectations"):
            exps = conn.execute("SELECT * FROM expectations ORDER BY id").fetchall()
            n_docs = n_members = 0
            for e in exps:
                name = f"{e['direction']}-{e['event']}"
                meta = {"direction": e["direction"], "event": e["event"],
                        "stage": e["stage"], "status": e["status"], "watchlist": name}
                if e.get("invalid_reason"):
                    meta["invalid_reason"] = e["invalid_reason"]
                sections = [f"# {e['direction']} · {e['event']}",
                            f"## 逻辑\n{e['thesis']}", f"## 催化锚点\n{e['catalyst']}",
                            f"## 兑现标志\n{e['fulfill_flag']}", f"## 失效标志\n{e['fail_flag']}"]
                if e.get("invalid_reason"):
                    sections.append(f"## 失效原因\n{e['invalid_reason']}")
                sections.append(f"\n> 迁移自老预期库 #{e['id']}({e['created_at'][:10]} 建,"
                                f"{e['updated_at'][:16]} 更新)")
                content = "\n\n".join(sections)
                row = conn.execute(
                    "SELECT id FROM documents WHERE doc_type='expectation' AND name=%s"
                    " AND COALESCE(trade_date,'')='' AND bag_id=0", (name,)).fetchone()
                if row:
                    doc_id = row["id"]
                else:
                    r = conn.execute(
                        "INSERT INTO documents(doc_type,name,trade_date,ref_id,content,"
                        " created_at,updated_at,meta,bag_id)"
                        " VALUES('expectation',%s,NULL,%s,%s,%s,%s,%s,0) RETURNING id",
                        (name, e["id"], content, e["created_at"], e["updated_at"],
                         _meta_json(meta))).fetchone()
                    doc_id = r["id"]
                    _log_version(conn, "document", doc_id, "save",
                                 {"doc_type": "expectation", "name": name, "content": content,
                                  "meta": meta, "migrated_from": e["id"]}, bag=0)
                    n_docs += 1
                members = conn.execute(
                    "SELECT * FROM pool_members WHERE expectation_id=%s ORDER BY id",
                    (e["id"],)).fetchall()
                wl = "archived-" + name if e["status"] in ("fulfilled", "invalid") else name
                conn.execute(
                    "INSERT INTO watchlists(bag_id, name, created_at, updated_at)"
                    " VALUES(0,%s,%s,%s) ON CONFLICT (bag_id,name) DO NOTHING",
                    (wl, e["created_at"], e["updated_at"]))
                _log_version(conn, "watchlist", f"0:{wl}", "create", {"name": wl}, bag=0)
                for m in members:
                    fields = {"role": m["role"], "reason": m["reason"]}
                    conn.execute(
                        "INSERT INTO watchlist_members(bag_id, list_name, code, name, fields, updated_at)"
                        " VALUES(0,%s,%s,%s,%s,%s) ON CONFLICT (bag_id,list_name,code)"
                        " DO UPDATE SET name=excluded.name, fields=excluded.fields",
                        (wl, m["code"], m["name"], json.dumps(fields, ensure_ascii=False), now))
                    _log_version(conn, "watchlist", f"0:{wl}", "add",
                                 {"code": m["code"], "name": m["name"], "fields": fields}, bag=0)
                    n_members += 1
            print(f"② 预期库迁移:{n_docs} 条预期 → documents,{n_members} 池成员 → watchlists"
                  + ("(老库为空,跳过)" if not exps else ""))

    # ③ 清除旧结构(独立连接,逐步幂等)
    with _connect() as conn:
        if table_exists(conn, "public", "expectations"):
            conn.execute("DROP TABLE pool_members, expectations CASCADE")
            print("③ 已删除表:expectations, pool_members")
        if table_exists(conn, "public", "account"):
            conn.execute("DROP TABLE account CASCADE")
            print("③ 已删除表:account(现金已入 wallets)")
        if column_exists(conn, "public", "fills", "expectation_id"):
            conn.execute("ALTER TABLE fills DROP COLUMN expectation_id")
            print("③ 已删除列:fills.expectation_id")
        if column_exists(conn, "public", "runs", "schema_name"):
            conn.execute("ALTER TABLE runs DROP COLUMN schema_name")
            print("③ 已删除列:runs.schema_name")

    with psycopg.connect(DATABASE_URL, autocommit=True,
                         row_factory=psycopg.rows.dict_row) as conn:
        schemas = [r["schema_name"] for r in conn.execute(
            "SELECT schema_name FROM information_schema.schemata"
            " WHERE schema_name LIKE 'run\\_%' OR schema_name LIKE 'replay\\_%'"
        ).fetchall()]
        for s in schemas:
            conn.execute(f'DROP SCHEMA "{s}" CASCADE')
        if schemas:
            print(f"③ 已删除老隔离 schema {len(schemas)} 个:{', '.join(schemas[:8])}{'…' if len(schemas) > 8 else ''}")
    with _connect() as conn:
        n = conn.execute("DELETE FROM runs WHERE kind='replay'").rowcount
        if n:
            print(f"③ 已删除老回放场次登记 {n} 行(live 历史保留)")
    print("\n✓ 迁移完成:平台只剩行级表,老结构全部清除")


if __name__ == "__main__":
    migrate()
