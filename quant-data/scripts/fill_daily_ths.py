#!/usr/bin/env python3
"""
jstock 日K采集（同花顺源）
备用/主力采集路径：当东方财富限流/封禁时使用
- 个股日K: hs_{code} 前缀 (免鉴权)
- 指数日K: zs_{code} 前缀 (免鉴权)
- 概念日K: 需走东方财富（同花顺无免鉴权接口）
- 返回最近 140 天左右历史，本脚本截取最近 N 天入库
"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
import psycopg2.extras
from collector.ths import INDEX_THS_CODE
from config import DB_CONFIG, RETENTION_DAYS
from collector import THSClient


def _upsert_rows(conn, code: str, tp: str, rows: list[dict]) -> int:
    """批量 UPSERT daily_k 行，返回插入行数"""
    if not rows:
        return 0
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(cur, """
            INSERT INTO daily_k (code, trade_date, type, open, high, low, close,
                                 pre_close, change_pct, volume, amount, turnover)
            VALUES %s
            ON CONFLICT (code, trade_date, type) DO UPDATE SET
                open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                close=EXCLUDED.close, pre_close=EXCLUDED.pre_close,
                change_pct=EXCLUDED.change_pct, volume=EXCLUDED.volume,
                amount=EXCLUDED.amount, turnover=EXCLUDED.turnover
        """, [(
            code, r["trade_date"], tp,
            r["open"], r["high"], r["low"], r["close"],
            r["pre_close"], r["change_pct"],
            r["volume"], r["amount"], r.get("turnover", 0)
        ) for r in rows])
    conn.commit()
    return len(rows)


def _compute_preclose(rows: list[dict]):
    """原地计算 pre_close 和 change_pct"""
    for j, r in enumerate(rows):
        r["pre_close"] = r["open"] if j == 0 else rows[j-1]["close"]
        pc = r["pre_close"]
        r["change_pct"] = round((r["close"]-pc)/pc*100, 2) if pc else 0.0


def fill_daily_ths(days: int = 30, delay: float = 0.15, limit: int = None):
    conn = psycopg2.connect(**DB_CONFIG)
    client = THSClient(delay=delay)
    try:
        # ─── 先采指数日K（4 只，秒级） ───
        print("📊 指数日K采集...")
        for std_code, ths_code in INDEX_THS_CODE.items():
            rows = client.get_index_kline(std_code)
            rows = rows[-days:] if len(rows) > days else rows
            _compute_preclose(rows)
            n = _upsert_rows(conn, std_code, "index", rows)
            print(f"  {std_code}: {n} 天")

        # ─── 概念日K（名称匹配 + 同花顺 48_ 接口） ───
        print("\n📊 概念日K采集（同花顺）...")
        with conn.cursor() as cur:
            cur.execute("SELECT code, name FROM concept_info ORDER BY code")
            db_concepts = cur.fetchall()
        concept_ok = concept_fail = 0
        for code, name in db_concepts:
            rows = client.get_concept_kline(name)
            if not rows:
                concept_fail += 1
                continue
            rows = rows[-days:] if len(rows) > days else rows
            _compute_preclose(rows)
            _upsert_rows(conn, code, "concept", rows)
            concept_ok += 1
        print(f"  概念: {concept_ok}成功 {concept_fail}失败 (共{len(db_concepts)})")

        # ─── 个股日K（主力） ───
        with conn.cursor() as cur:
            cur.execute("SELECT code, name FROM stock_info ORDER BY code")
            stocks = cur.fetchall()
        if limit:
            stocks = stocks[:limit]
        total = len(stocks)
        print(f"\n🚀 同花顺日K采集: {total} 个股, 保留最近 {days} 天")
        print("-" * 55)

        ok = fail = 0
        inserted = 0
        start = time.time()
        for i, (code, name) in enumerate(stocks):
            try:
                rows = client.get_history_kline(code, "1d")
                rows = rows[-days:] if len(rows) > days else rows
                if not rows:
                    fail += 1
                    continue
                _compute_preclose(rows)
                _upsert_rows(conn, code, "stock", rows)
                ok += 1
                inserted += len(rows)
            except Exception as e:
                conn.rollback()
                fail += 1
                if fail < 5:
                    print(f"  ⚠️ {code} {name}: {e}")

            if (i + 1) % 100 == 0:
                elapsed = time.time() - start
                eta = elapsed / (i + 1) * (total - i - 1)
                print(f"  [{i+1}/{total}] {ok}成功 {fail}失败 "
                      f"共入库{inserted}行 | {elapsed:.0f}s ETA {eta/60:.1f}min")

        # 补齐交易日历
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO trade_cal (trade_date, is_trade)
                SELECT DISTINCT trade_date, TRUE FROM daily_k
                WHERE trade_date NOT IN (SELECT trade_date FROM trade_cal)
            """)
            cal_n = cur.rowcount
        conn.commit()

        elapsed = time.time() - start
        print("-" * 55)
        print(f"✅ 完成: {ok}成功 {fail}失败 | 入库 {inserted} 行 | "
              f"交易日历 +{cal_n} 天 | 耗时 {elapsed/60:.1f}min")
    finally:
        conn.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="jstock 同花顺日K采集")
    parser.add_argument("--days", type=int, default=RETENTION_DAYS,
                        help=f"保留天数 (默认{RETENTION_DAYS})")
    parser.add_argument("--delay", type=float, default=0.15, help="请求间隔秒")
    parser.add_argument("--limit", type=int, default=None, help="股票数量限制(测试用)")
    args = parser.parse_args()
    fill_daily_ths(days=args.days, delay=args.delay, limit=args.limit)
