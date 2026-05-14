#!/usr/bin/env python3
"""
jstock 量化数据中心 - 初始化脚本
首次运行，拉取全量基础数据 + 近30天日K

使用方法：
    python scripts/init_db.py              # 全量采集
    python scripts/init_db.py --stocks-only  # 仅股票日K
    python scripts/init_db.py --concepts-only # 仅概念日K
"""
import sys
import time
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
import psycopg2.extras
from config import DB_CONFIG, RETENTION_DAYS, INDICES
from collector import EastmoneyClient


class InitDB:
    def __init__(self):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.client = EastmoneyClient()

    def close(self):
        self.conn.close()

    # ─── 股票列表 ───

    def collect_stock_info(self):
        """采集全A股列表 → stock_info"""
        print("📊 采集全A股列表...", end=" ", flush=True)
        stocks = self.client.get_stock_list()
        if not stocks:
            print("❌ 无数据")
            return

        with self.conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, """
                INSERT INTO stock_info (code, name, exchange)
                VALUES %s
                ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, exchange=EXCLUDED.exchange
            """, [(s["code"], s["name"], s["exchange"]) for s in stocks])
        self.conn.commit()
        print(f"✅ {len(stocks)} 只")

    # ─── 概念列表 ───

    def collect_concept_info(self):
        """采集概念板块列表 → concept_info"""
        print("📊 采集概念列表...", end=" ", flush=True)
        concepts = self.client.get_concept_list()
        if not concepts:
            print("❌ 无数据")
            return

        with self.conn.cursor() as cur:
            psycopg2.extras.execute_values(cur, """
                INSERT INTO concept_info (code, name, stock_count)
                VALUES %s
                ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, stock_count=EXCLUDED.stock_count
            """, [(c["code"], c["name"], c["stock_count"]) for c in concepts])
        self.conn.commit()
        print(f"✅ {len(concepts)} 个")

    # ─── 日K采集 ───

    def collect_daily_kline(self, code: str, tp: str = "stock", name: str = ""):
        """采集单个标的日K并入库"""
        try:
            rows = self.client.get_daily_kline(code, tp, days=RETENTION_DAYS)
            if not rows:
                return 0
            
            with self.conn.cursor() as cur:
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
            self.conn.commit()
            return len(rows)
        except Exception as e:
            print(f"\n  ⚠️ {code} {name} 采集失败: {e}")
            self.conn.rollback()
            return 0

    def collect_stocks_daily(self):
        """采集全市场个股日K"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT code, name, exchange FROM stock_info ORDER BY exchange, code")
            stocks = cur.fetchall()

        total = len(stocks)
        print(f"📊 采集个股日K (共{total}只)...")
        
        ok = fail = 0
        start = time.time()
        for i, (code, name, exchange) in enumerate(stocks):
            n = self.collect_daily_kline(code, "stock", name)
            if n > 0:
                ok += 1
            else:
                fail += 1
            # 每100只汇报进度
            if (i + 1) % 100 == 0:
                elapsed = time.time() - start
                eta = elapsed / (i + 1) * (total - i - 1)
                print(f"  [{i+1}/{total}] {ok}成功 {fail}失败 | "
                      f"耗时{elapsed:.0f}s 预计剩余{eta:.0f}s")
        elapsed = time.time() - start
        print(f"✅ 个股日K完成: {ok}成功 {fail}失败 | 总耗时{elapsed:.1f}s")

    def collect_indices_daily(self):
        """采集主要指数日K"""
        print("📊 采集指数日K...")
        for code, name in INDICES:
            n = self.collect_daily_kline(code, "index", name)
            print(f"  {name}({code}): {n} 天")

    def collect_concepts_daily(self, limit: int = None):
        """采集概念板块日K"""
        with self.conn.cursor() as cur:
            cur.execute("SELECT code, name FROM concept_info ORDER BY stock_count DESC")
            concepts = cur.fetchall()

        if limit:
            concepts = concepts[:limit]

        total = len(concepts)
        print(f"📊 采集概念日K (共{total}个)...")
        
        ok = fail = 0
        start = time.time()
        for i, (code, name) in enumerate(concepts):
            n = self.collect_daily_kline(code, "concept", name)
            if n > 0:
                ok += 1
            else:
                fail += 1
            if (i + 1) % 50 == 0:
                elapsed = time.time() - start
                eta = elapsed / (i + 1) * (total - i - 1)
                print(f"  [{i+1}/{total}] {ok}成功 {fail}失败 | "
                      f"耗时{elapsed:.0f}s 预计剩余{eta:.0f}s")
        elapsed = time.time() - start
        print(f"✅ 概念日K完成: {ok}成功 {fail}失败 | 总耗时{elapsed:.1f}s")

    # ─── 交易日历 ───

    def generate_trade_calendar(self):
        """从 daily_k 表推导交易日历"""
        print("📅 生成交易日历...", end=" ", flush=True)
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO trade_cal (trade_date, is_trade)
                SELECT DISTINCT trade_date, TRUE
                FROM daily_k
                WHERE trade_date NOT IN (SELECT trade_date FROM trade_cal)
                ORDER BY trade_date
            """)
            n = cur.rowcount
        self.conn.commit()
        print(f"✅ {n} 天")

    # ─── 滚动清理 ───

    def clean_old_data(self):
        """清理超过保留期的数据"""
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM daily_k WHERE trade_date < CURRENT_DATE - %s", (RETENTION_DAYS,))
            d = cur.rowcount
            cur.execute("DELETE FROM minute_k WHERE dt < CURRENT_DATE - %s", (RETENTION_DAYS,))
            m = cur.rowcount
        self.conn.commit()
        if d or m:
            print(f"🗑️  滚动清理: 日K {d} 条, 分钟K {m} 条")

    # ─── 全量 ───

    def run_all(self):
        """运行全量初始化"""
        print("=" * 55)
        print("🚀 jstock 量化数据中心 - 初始化")
        print("=" * 55)

        t0 = time.time()

        # 1. 基础信息
        self.collect_stock_info()
        self.collect_concept_info()

        # 2. 日K
        self.collect_indices_daily()
        self.collect_concepts_daily()
        self.collect_stocks_daily()

        # 3. 交易日历
        self.generate_trade_calendar()

        # 4. 清理
        self.clean_old_data()

        # 统计
        with self.conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM stock_info")
            sc = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM concept_info")
            cc = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM daily_k")
            dk = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM trade_cal")
            tc = cur.fetchone()[0]

        elapsed = time.time() - t0
        print(f"\n{'=' * 55}")
        print(f"✅ 初始化完成!")
        print(f"  股票: {sc} 只 | 概念: {cc} 个")
        print(f"  日K: {dk} 条 | 交易日: {tc} 天")
        print(f"  总耗时: {elapsed:.1f}s ({elapsed/60:.1f}分钟)")
        print(f"{'=' * 55}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="jstock 数据初始化")
    parser.add_argument("--stocks-only", action="store_true", help="仅股票日K")
    parser.add_argument("--concepts-only", action="store_true", help="仅概念日K")
    parser.add_argument("--concept-limit", type=int, default=None, help="概念数量限制")
    args = parser.parse_args()

    init = InitDB()
    try:
        if args.stocks_only:
            init.collect_stock_info()
            init.collect_stocks_daily()
            init.generate_trade_calendar()
        elif args.concepts_only:
            init.collect_concept_info()
            init.collect_concepts_daily(args.concept_limit)
        else:
            init.run_all()
    finally:
        init.close()
