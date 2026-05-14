#!/usr/bin/env python3
"""
jstock 每日增量同步
收盘后运行（推荐 16:30 之后），只采集 T 日当天数据并 UPSERT
相对 init_db.py：
  - 只拉最近 1-2 天（days=2），避免全量
  - 跳过无变化的股票（可选）
  - 末尾触发滚动清理

使用:
    python scripts/daily_sync.py                # 同步今日
    python scripts/daily_sync.py --days 3       # 回补近3天
"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
import psycopg2.extras
from config import DB_CONFIG, RETENTION_DAYS, INDICES
from collector import EastmoneyClient


class DailySync:
    def __init__(self, days: int = 2):
        self.conn = psycopg2.connect(**DB_CONFIG)
        self.client = EastmoneyClient()
        self.days = days  # 回补窗口

    def close(self):
        self.conn.close()

    def _upsert_daily(self, code: str, tp: str, rows: list[dict]) -> int:
        if not rows:
            return 0
        try:
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
            self.conn.rollback()
            print(f"  ⚠️ {code} upsert 失败: {e}")
            return 0

    def sync_stocks(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT code, name FROM stock_info ORDER BY code")
            stocks = cur.fetchall()
        total = len(stocks)
        print(f"🔄 增量同步个股 (共{total}只, 回补{self.days}天)...")

        ok = fail = 0
        start = time.time()
        for i, (code, name) in enumerate(stocks):
            rows = self.client.get_daily_kline(code, "stock", days=self.days)
            n = self._upsert_daily(code, "stock", rows)
            if n > 0:
                ok += 1
            else:
                fail += 1
            if (i + 1) % 200 == 0:
                elapsed = time.time() - start
                eta = elapsed / (i + 1) * (total - i - 1)
                print(f"  [{i+1}/{total}] {ok}成功 {fail}失败 | "
                      f"耗时{elapsed:.0f}s ETA{eta:.0f}s")
        print(f"✅ 个股: {ok}成功 {fail}失败 | 耗时{time.time()-start:.1f}s")

    def sync_concepts(self):
        with self.conn.cursor() as cur:
            cur.execute("SELECT code, name FROM concept_info ORDER BY code")
            concepts = cur.fetchall()
        total = len(concepts)
        print(f"🔄 增量同步概念 (共{total}个, 回补{self.days}天)...")

        ok = fail = 0
        start = time.time()
        for i, (code, name) in enumerate(concepts):
            rows = self.client.get_daily_kline(code, "concept", days=self.days)
            n = self._upsert_daily(code, "concept", rows)
            if n > 0:
                ok += 1
            else:
                fail += 1
            if (i + 1) % 100 == 0:
                elapsed = time.time() - start
                eta = elapsed / (i + 1) * (total - i - 1)
                print(f"  [{i+1}/{total}] {ok}成功 {fail}失败 | "
                      f"耗时{elapsed:.0f}s ETA{eta:.0f}s")
        print(f"✅ 概念: {ok}成功 {fail}失败 | 耗时{time.time()-start:.1f}s")

    def sync_indices(self):
        print(f"🔄 增量同步指数 (回补{self.days}天)...")
        for code, name in INDICES:
            rows = self.client.get_daily_kline(code, "index", days=self.days)
            n = self._upsert_daily(code, "index", rows)
            print(f"  {name}({code}): {n} 天")

    def refresh_trade_cal(self):
        """从 daily_k 补齐交易日历"""
        with self.conn.cursor() as cur:
            cur.execute("""
                INSERT INTO trade_cal (trade_date, is_trade)
                SELECT DISTINCT trade_date, TRUE FROM daily_k
                WHERE trade_date NOT IN (SELECT trade_date FROM trade_cal)
                ORDER BY trade_date
            """)
            n = cur.rowcount
        self.conn.commit()
        if n:
            print(f"📅 补齐交易日历: {n} 天")

    def clean_old(self):
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM daily_k WHERE trade_date < CURRENT_DATE - %s",
                       (RETENTION_DAYS,))
            d = cur.rowcount
            cur.execute("DELETE FROM minute_k WHERE dt < CURRENT_DATE - %s",
                       (RETENTION_DAYS,))
            m = cur.rowcount
        self.conn.commit()
        if d or m:
            print(f"🗑️  清理: 日K -{d}, 分钟K -{m}")

    def run(self):
        print("=" * 55)
        print(f"🚀 jstock 增量同步 (回补 {self.days} 天)")
        print("=" * 55)
        t0 = time.time()
        self.sync_indices()
        self.sync_concepts()
        self.sync_stocks()
        self.refresh_trade_cal()
        self.clean_old()
        print(f"\n✅ 完成，总耗时 {time.time()-t0:.1f}s")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="jstock 每日增量同步")
    parser.add_argument("--days", type=int, default=2, help="回补天数 (默认2)")
    parser.add_argument("--stocks-only", action="store_true")
    parser.add_argument("--concepts-only", action="store_true")
    args = parser.parse_args()

    s = DailySync(days=args.days)
    try:
        if args.stocks_only:
            s.sync_stocks()
        elif args.concepts_only:
            s.sync_concepts()
        else:
            s.run()
    finally:
        s.close()
