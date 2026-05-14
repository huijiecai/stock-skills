"""
jstock 量化数据查询 API
统一 HTTP 接口：外部应用只需访问本服务，不直连行情源
端口: 8100 (与 backend 的 8000 错开)
"""
import sys
from pathlib import Path
from datetime import date
from typing import Optional
from contextlib import contextmanager

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import DB_CONFIG

app = FastAPI(
    title="jstock Quant Data API",
    version="0.1.0",
    description="A股量化数据服务：stock / concept / index 统一出口",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@contextmanager
def get_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


def rows_to_dict(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


# ─────── 基础信息 ───────

@app.get("/api/stock/list")
def list_stocks(exchange: Optional[str] = None, limit: int = 5000):
    """股票列表"""
    sql = "SELECT code, name, exchange FROM stock_info"
    params = []
    if exchange:
        sql += " WHERE exchange = %s"
        params.append(exchange)
    sql += " ORDER BY exchange, code LIMIT %s"
    params.append(limit)
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return {"total": cur.rowcount, "data": rows_to_dict(cur)}


@app.get("/api/concept/list")
def list_concepts(limit: int = 1000):
    """概念板块列表"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT code, name, stock_count FROM concept_info "
            "ORDER BY stock_count DESC LIMIT %s", (limit,))
        return {"total": cur.rowcount, "data": rows_to_dict(cur)}


@app.get("/api/stock/{code}")
def stock_info(code: str):
    """单股信息"""
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute("SELECT code, name, exchange FROM stock_info WHERE code=%s", (code,))
        rows = rows_to_dict(cur)
        if not rows:
            raise HTTPException(404, f"stock {code} not found")
        return rows[0]


# ─────── 日K ───────

@app.get("/api/daily/{code}")
def daily_kline(
    code: str,
    type: str = Query("stock", pattern="^(stock|index|concept)$"),
    start: Optional[date] = None,
    end: Optional[date] = None,
    limit: int = 100,
):
    """日K线 （stock / index / concept 统一）"""
    sql = ("SELECT code, trade_date, type, open, high, low, close, pre_close, "
           "change_pct, volume, amount, turnover "
           "FROM daily_k WHERE code=%s AND type=%s")
    params: list = [code, type]
    if start:
        sql += " AND trade_date >= %s"
        params.append(start)
    if end:
        sql += " AND trade_date <= %s"
        params.append(end)
    sql += " ORDER BY trade_date DESC LIMIT %s"
    params.append(limit)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        data = rows_to_dict(cur)
    data.reverse()  # 按日期升序返回
    return {"code": code, "type": type, "total": len(data), "data": data}


# ─────── 分钟K ───────

@app.get("/api/minute/{code}")
def minute_kline(
    code: str,
    type: str = Query("stock", pattern="^(stock|index|concept)$"),
    freq: str = Query("1m", pattern="^(1m|5m|15m|30m|60m)$"),
    date_: Optional[date] = Query(None, alias="date"),
    limit: int = 500,
):
    """分钟K / 分时"""
    sql = ("SELECT code, dt, freq, type, open, high, low, close, "
           "volume, amount, avg_price "
           "FROM minute_k WHERE code=%s AND type=%s AND freq=%s")
    params: list = [code, type, freq]
    if date_:
        sql += " AND dt::date = %s"
        params.append(date_)
    sql += " ORDER BY dt DESC LIMIT %s"
    params.append(limit)

    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        data = rows_to_dict(cur)
    data.reverse()
    return {"code": code, "type": type, "freq": freq, "total": len(data), "data": data}


# ─────── 交易日历 ───────

@app.get("/api/trade_cal")
def trade_cal(start: Optional[date] = None, end: Optional[date] = None):
    """交易日历"""
    sql = "SELECT trade_date, is_trade FROM trade_cal WHERE 1=1"
    params: list = []
    if start:
        sql += " AND trade_date >= %s"
        params.append(start)
    if end:
        sql += " AND trade_date <= %s"
        params.append(end)
    sql += " ORDER BY trade_date"
    with get_conn() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return {"total": cur.rowcount, "data": rows_to_dict(cur)}


# ─────── 健康检查 & 统计 ───────

@app.get("/health")
def health():
    try:
        with get_conn() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(500, f"db error: {e}")


@app.get("/stats")
def stats():
    """库内数据概况"""
    with get_conn() as conn, conn.cursor() as cur:
        result = {}
        for tbl in ("stock_info", "concept_info", "trade_cal", "daily_k", "minute_k"):
            cur.execute(f"SELECT COUNT(*) FROM {tbl}")
            result[tbl] = cur.fetchone()[0]
        # 最新日期
        cur.execute("SELECT MAX(trade_date), MIN(trade_date) FROM daily_k")
        mx, mn = cur.fetchone()
        result["daily_k_range"] = {"min": str(mn) if mn else None,
                                   "max": str(mx) if mx else None}
    return result


@app.get("/")
def root():
    return {
        "service": "jstock",
        "version": "0.1.0",
        "docs": "/docs",
        "endpoints": [
            "/api/stock/list", "/api/concept/list", "/api/stock/{code}",
            "/api/daily/{code}", "/api/minute/{code}", "/api/trade_cal",
            "/stats", "/health",
        ],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
