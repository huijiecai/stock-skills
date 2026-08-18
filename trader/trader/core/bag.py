"""core·袋子开局与销毁(实现设计 §6):模拟场三种钱包开法 + 知识复制 + 指纹。

- fresh(默认):钱包从初始资金;知识(预期/研究/笔记文档 + 全部自选组 + 当日预案)从正本复制
- fork:钱包复制正本现状(回放历史日=带未来持仓,调用方负责在封面标注)
- fork-as-of D:钱包从正本 fills 流水折叠重建"截至 D 收盘";知识复制正本现状
- custom:JSON 指定现金+持仓
"""
import hashlib
import json

from trader.core.context import set_context
from trader.core.db import _connect
from trader.core.ledger import INITIAL_CASH, Account

# 跨日知识文档(随袋复制);premarket 只复制目标日当天;close 永不复制(未来知识)
KNOWLEDGE_TYPES = ("expectation", "research", "note")


def open_live(run_id: int) -> None:
    """实盘场:写正本袋(bag 0)。"""
    set_context(0, run_id)


def open_replay(run_id: int, date: str, mode: str = "fresh",
                custom: dict | None = None, as_of: str = "") -> str:
    """模拟场开局:建钱包 + 复制知识,切上下文到袋子。返回全状态指纹。"""
    bag = run_id
    acct = Account()
    # ① 钱包
    if mode == "fresh":
        acct.open_wallet(INITIAL_CASH, INITIAL_CASH, bag)
    elif mode == "fork":
        _copy_wallet(acct, bag)
    elif mode == "fork-as-of":
        _wallet_as_of(acct, bag, as_of or date)
    elif mode == "custom":
        c = custom or {}
        cash = round(float(c.get("cash", 0)) * 100)
        acct.open_wallet(cash, max(cash, 1), bag)
        with _connect() as conn:
            for p in c.get("positions", []):
                conn.execute(
                    "INSERT INTO positions(bag_id, code, name, quantity, sellable,"
                    " avg_cost_cents, bought_on) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                    (bag, p["code"], p.get("name", ""), int(p["quantity"]),
                     0 if p.get("bought_on") == date else int(p["quantity"]),
                     round(float(p["avg_cost"]) * 100), p.get("bought_on", date)),
                )
    else:
        raise ValueError(f"未知开局模式:{mode}")
    # ② 知识复制(所有模式同规则:知识文档全量 + 当日预案 + 全部自选组)
    _copy_knowledge(bag, date)
    set_context(bag, run_id)
    return fingerprint(bag)


def fingerprint(bag: int) -> str:
    """全状态指纹:现金+持仓+知识文档+自选组的规范化哈希(对比页校验起点一致)。"""
    with _connect() as conn:
        wallet = conn.execute("SELECT cash_cents FROM wallets WHERE bag_id=%s", (bag,)).fetchone()
        positions = conn.execute(
            "SELECT code, quantity, avg_cost_cents FROM positions WHERE bag_id=%s AND quantity>0"
            " ORDER BY code", (bag,)).fetchall()
        docs = conn.execute(
            "SELECT doc_type, COALESCE(name,'') AS name, COALESCE(trade_date,'') AS d,"
            " meta, md5(content) AS chash FROM documents WHERE bag_id=%s"
            " ORDER BY doc_type, name, d", (bag,)).fetchall()
        wls = conn.execute(
            "SELECT w.name, m.code, m.fields FROM watchlists w"
            " JOIN watchlist_members m ON m.bag_id=w.bag_id AND m.list_name=w.name"
            " WHERE w.bag_id=%s ORDER BY w.name, m.code", (bag,)).fetchall()
    norm = {
        "cash": wallet["cash_cents"] if wallet else None,
        "positions": [[p["code"], p["quantity"], p["avg_cost_cents"]] for p in positions],
        "docs": [[d["doc_type"], d["name"], d["d"], json.dumps(d["meta"], sort_keys=True), d["chash"]]
                 for d in docs],
        "watchlists": [[w["name"], w["code"], json.dumps(w["fields"], sort_keys=True)] for w in wls],
    }
    return hashlib.sha256(json.dumps(norm, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]


def delete_bag(bag: int) -> None:
    """销毁袋子(行级,一个事务):业务数据 + 版本 + 钱包全清。"""
    with _connect() as conn:
        for tbl in ("documents", "watchlist_members", "watchlists", "versions",
                    "positions", "fills"):
            conn.execute(f"DELETE FROM {tbl} WHERE bag_id=%s", (bag,))
        conn.execute("DELETE FROM wallets WHERE bag_id=%s", (bag,))


# ── 内部 ────────────────────────────────────────────────

def _copy_wallet(acct: Account, bag: int) -> None:
    """fork:现金/持仓/流水(含历史)原样复制正本。"""
    with _connect() as conn:
        src = conn.execute("SELECT cash_cents, initial_cents FROM wallets WHERE bag_id=0").fetchone()
        if src is None:
            raise ValueError("正本钱包不存在(先跑一次 live 或 migration)")
        acct.open_wallet(src["cash_cents"], src["initial_cents"], bag)
        conn.execute(
            "INSERT INTO positions(bag_id, code, name, quantity, sellable, avg_cost_cents, bought_on)"
            " SELECT %s, code, name, quantity, sellable, avg_cost_cents, bought_on"
            " FROM positions WHERE bag_id=0", (bag,))
        conn.execute(
            "INSERT INTO fills(bag_id, run_id, code, side, quantity, price_cents,"
            " cash_before_cents, cash_after_cents, position_before, position_after,"
            " created_at, reason, name, trade_time)"
            " SELECT %s, run_id, code, side, quantity, price_cents, cash_before_cents,"
            " cash_after_cents, position_before, position_after, created_at, reason,"
            " name, trade_time FROM fills WHERE bag_id=0", (bag,))


def _wallet_as_of(acct: Account, bag: int, as_of: str) -> None:
    """fork-as-of:从正本流水折叠出截至 as_of 收盘的钱包(现金/持仓/T+1)。"""
    d = as_of.replace("-", "")
    iso = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
    with _connect() as conn:
        initial = conn.execute(
            "SELECT initial_cents FROM wallets WHERE bag_id=0").fetchone()["initial_cents"]
        fills = conn.execute(
            "SELECT * FROM fills WHERE bag_id=0 ORDER BY id").fetchall()
    cash, pos = initial, {}   # code → {qty, cost_cents(total), bought_on}
    for f in fills:
        ts = (f["trade_time"] or f["created_at"] or "")[:10]
        if ts > iso:
            continue
        code, qty, price_c = f["code"], f["quantity"], f["price_cents"]
        if f["side"] == "BUY":
            p = pos.setdefault(code, {"qty": 0, "cost": 0, "bought_on": f["created_at"][:10]})
            p["qty"] += qty
            p["cost"] += qty * price_c
        else:
            p = pos.get(code)
            if not p:
                continue
            avg = p["cost"] // p["qty"] if p["qty"] else 0
            p["qty"] -= qty
            p["cost"] -= qty * avg
            cash += qty * price_c
            if p["qty"] == 0:
                pos.pop(code)
                continue
        if f["side"] == "BUY":
            cash -= qty * price_c
    acct.open_wallet(cash, initial, bag)
    with _connect() as conn:
        for code, p in pos.items():
            if p["qty"] <= 0:
                continue
            avg = p["cost"] // p["qty"]
            conn.execute(
                "INSERT INTO positions(bag_id, code, name, quantity, sellable,"
                " avg_cost_cents, bought_on) VALUES(%s,%s,%s,%s,%s,%s,%s)",
                (bag, code, "", p["qty"],
                 p["qty"] if p["bought_on"] < iso else 0, avg, p["bought_on"]),
            )


def _copy_knowledge(bag: int, date: str) -> None:
    """知识随袋:知识文档全量 + 目标日预案 + 全部自选组(不带 archived- 前缀规则,原样)。"""
    with _connect() as conn:
        marks = ",".join(["%s"] * len(KNOWLEDGE_TYPES))
        n = conn.execute(
            f"INSERT INTO documents(doc_type,name,trade_date,ref_id,content,"
            f" created_at,updated_at,meta,bag_id)"
            f" SELECT doc_type,name,trade_date,ref_id,content,created_at,updated_at,meta,%s"
            f" FROM documents WHERE bag_id=0 AND (doc_type IN ({marks})"
            f" OR (doc_type='premarket' AND COALESCE(trade_date,'')=%s))",
            (bag, *KNOWLEDGE_TYPES, date)).rowcount
        conn.execute(
            "INSERT INTO watchlists(bag_id, name, created_at, updated_at)"
            " SELECT %s, name, created_at, updated_at FROM watchlists WHERE bag_id=0", (bag,))
        conn.execute(
            "INSERT INTO watchlist_members(bag_id, list_name, code, name, fields, updated_at)"
            " SELECT %s, list_name, code, name, fields, updated_at"
            " FROM watchlist_members WHERE bag_id=0", (bag,))
    return n
