#!/usr/bin/env python3
"""
离线 Bootstrap：从现有 stock 库 (backend 模块) 迁移基础信息到 jstock
适用场景：
    - 首次初始化时东方财富限流/IP封禁
    - 快速拉起基础 stock_info / concept_info 列表

只迁移列表数据（stock_info, concept_info），不迁移日K
日K 数据仍然通过 eastmoney 或 ths 采集器自己采
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
from config import DB_CONFIG

SOURCE_DB = {**DB_CONFIG, "dbname": "stock"}  # 源库


def migrate_stock_info():
    src = psycopg2.connect(**SOURCE_DB)
    dst = psycopg2.connect(**DB_CONFIG)
    try:
        with src.cursor() as s, dst.cursor() as d:
            # 源表字段: stock_code, stock_name, industry, list_date, market
            s.execute("SELECT stock_code, stock_name, market FROM stock_info "
                      "WHERE stock_code IS NOT NULL ORDER BY stock_code")
            rows = s.fetchall()
            if not rows:
                print("  源 stock_info 无数据")
                return 0
            # 映射 market -> exchange
            def _ex(code, mk):
                if mk: return mk.lower()[:2]
                if code.startswith("6") or code.startswith("688"): return "sh"
                if code.startswith("4") or code.startswith("8") or code.startswith("9"): return "bj"
                return "sz"

            data = [(c, n, _ex(c, m)) for c, n, m in rows]
            d.executemany("""
                INSERT INTO stock_info (code, name, exchange) VALUES (%s, %s, %s)
                ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, exchange=EXCLUDED.exchange
            """, data)
        dst.commit()
        print(f"✅ stock_info: 迁移 {len(rows)} 只")
        return len(rows)
    finally:
        src.close(); dst.close()


def migrate_concept_info():
    src = psycopg2.connect(**SOURCE_DB)
    dst = psycopg2.connect(**DB_CONFIG)
    try:
        with src.cursor() as s, dst.cursor() as d:
            s.execute("SELECT concept_code, concept_name, component_count "
                      "FROM concept_info_east WHERE concept_code IS NOT NULL")
            rows = s.fetchall()
            if not rows:
                print("  源 concept_info_east 无数据")
                return 0
            d.executemany("""
                INSERT INTO concept_info (code, name, stock_count) VALUES (%s, %s, %s)
                ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, stock_count=EXCLUDED.stock_count
            """, [(c, n, cnt or 0) for c, n, cnt in rows])
        dst.commit()
        print(f"✅ concept_info: 迁移 {len(rows)} 个")
        return len(rows)
    finally:
        src.close(); dst.close()


if __name__ == "__main__":
    print("🔄 从 stock 库迁移基础信息到 jstock")
    print("-" * 50)
    migrate_stock_info()
    migrate_concept_info()
    print("-" * 50)
    print("完成")
