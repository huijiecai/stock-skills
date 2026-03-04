#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同花顺概念数据采集脚本

支持采集：
1. 概念列表 (concept_list)
2. 概念成分股 (members)
3. 概念日行情 (daily)
4. 个股热榜 (hot_rank)
5. 涨跌停榜单 (limit_list)
6. 全部数据 (all)

使用方法：
    python collect_ths_data.py --method concept_list
    python collect_ths_data.py --method members
    python collect_ths_data.py --method daily --start 2026-03-01 --end 2026-03-02
    python collect_ths_data.py --method hot_rank --start 2026-03-01 --end 2026-03-02
    python collect_ths_data.py --method hot_rank --is-new Y
    python collect_ths_data.py --method limit_list --start 2026-03-01 --end 2026-03-02
    python collect_ths_data.py --method limit_list --limit-type 连扳池
    python collect_ths_data.py --method all --days 60
"""

import argparse
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 添加 tushare_client 模块路径
skills_path = project_root / 'skills' / 'dragon-stock-trading' / 'scripts'
sys.path.insert(0, str(skills_path))

from tushare_client import tushare_client


class THSDataCollector:
    """同花顺数据采集器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.tushare = tushare_client
        self._ensure_tables()
    
    def _date_to_tushare(self, date_str: str) -> str:
        """转换日期格式：2026-03-01 -> 20260301"""
        return date_str.replace('-', '')
    
    def _tushare_to_date(self, ts_date: str) -> str:
        """转换日期格式：20260301 -> 2026-03-01"""
        if len(ts_date) == 8:
            return f"{ts_date[:4]}-{ts_date[4:6]}-{ts_date[6:8]}"
        return ts_date
    
    def _ensure_tables(self):
        """确保表存在"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # ths_concept - 概念列表
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ths_concept (
                ts_code TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                concept_type TEXT,
                component_count INTEGER,
                list_date TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # ths_concept_member - 成分股
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ths_concept_member (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                concept_code TEXT NOT NULL,
                concept_name TEXT NOT NULL,
                stock_code TEXT NOT NULL,
                stock_name TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(concept_code, stock_code)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_member_concept ON ths_concept_member(concept_code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_member_stock ON ths_concept_member(stock_code)')
        
        # ths_concept_daily - 日行情
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ths_concept_daily (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                concept_code TEXT NOT NULL,
                concept_name TEXT,
                pre_close REAL,
                open REAL,
                close REAL,
                high REAL,
                low REAL,
                pct_change REAL,
                vol REAL,
                turnover_rate REAL,
                total_mv REAL,
                float_mv REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(trade_date, concept_code)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_concept_daily_date ON ths_concept_daily(trade_date)')
        
        # ths_hot_rank - 个股热榜
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ths_hot_rank (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                rank_time TEXT NOT NULL,
                ts_code TEXT NOT NULL,
                ts_name TEXT,
                rank INTEGER,
                hot REAL,
                pct_change REAL,
                current_price REAL,
                concept TEXT,
                rank_reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(trade_date, rank_time, ts_code)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ths_hot_rank_date ON ths_hot_rank(trade_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ths_hot_rank_stock ON ths_hot_rank(ts_code)')
        
        # ths_limit_list - 涨跌停榜单
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ths_limit_list (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_date TEXT NOT NULL,
                ts_code TEXT NOT NULL,
                ts_name TEXT,
                price REAL,
                pct_chg REAL,
                limit_type TEXT NOT NULL,
                tag TEXT,
                status TEXT,
                lu_desc TEXT,
                open_num INTEGER,
                first_lu_time TEXT,
                last_lu_time TEXT,
                limit_order REAL,
                limit_amount REAL,
                lu_limit_order REAL,
                turnover_rate REAL,
                turnover REAL,
                free_float REAL,
                sum_float REAL,
                limit_up_suc_rate REAL,
                market_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(trade_date, ts_code, limit_type)
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ths_limit_date ON ths_limit_list(trade_date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ths_limit_stock ON ths_limit_list(ts_code)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_ths_limit_type ON ths_limit_list(limit_type)')
        
        conn.commit()
        conn.close()
    
    def collect_concept_list(self) -> int:
        """采集概念列表"""
        print("📊 采集同花顺概念列表...")
        
        try:
            data = self.tushare.get_ths_concept_list()
            
            if not data or not data.get('items'):
                print("⚠️ 未获取到概念数据")
                return 0
            
            items = data['items']
            print(f"  获取到 {len(items)} 条概念数据")
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            count = 0
            for item in items:
                try:
                    # fields: ts_code, name, type, component_count, list_date
                    ts_code = item[0]
                    name = item[1]
                    concept_type = item[2] if len(item) > 2 else None
                    component_count = item[3] if len(item) > 3 else None
                    list_date = self._tushare_to_date(item[4]) if len(item) > 4 and item[4] else None
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO ths_concept
                        (ts_code, name, concept_type, component_count, list_date, updated_at)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (ts_code, name, concept_type, component_count, list_date))
                    count += 1
                except Exception as e:
                    print(f"  插入失败 {item[0]}: {e}")
            
            conn.commit()
            conn.close()
            
            print(f"✅ 概念列表采集完成，共 {count} 条")
            return count
            
        except Exception as e:
            print(f"❌ 采集概念列表失败: {e}")
            return 0
    
    def collect_members(self) -> int:
        """采集概念成分股"""
        print("📊 采集概念成分股...")
        
        # 先获取概念列表
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT ts_code, name FROM ths_concept')
        concepts = cursor.fetchall()
        conn.close()
        
        if not concepts:
            print("⚠️ 请先采集概念列表")
            return 0
        
        print(f"  共 {len(concepts)} 个概念需要采集")
        
        total_count = 0
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for i, (concept_code, concept_name) in enumerate(concepts):
            try:
                print(f"  [{i+1}/{len(concepts)}] 采集 {concept_name} ({concept_code})...", end='')
                
                data = self.tushare.get_ths_concept_member(concept_code)
                
                if not data or not data.get('items'):
                    print(" 无数据")
                    continue
                
                items = data['items']
                count = 0
                for item in items:
                    try:
                        # item: [ts_code, stock_code, stock_name]
                        stock_code = item[1].replace('.SZ', '').replace('.SH', '').replace('.BJ', '') if len(item) > 1 else None
                        stock_name = item[2] if len(item) > 2 else None
                        
                        if not stock_code:
                            continue
                        
                        cursor.execute('''
                            INSERT OR REPLACE INTO ths_concept_member
                            (concept_code, concept_name, stock_code, stock_name, updated_at)
                            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ''', (concept_code, concept_name, stock_code, stock_name))
                        count += 1
                    except Exception:
                        pass
                
                conn.commit()
                total_count += count
                print(f" {count} 只股票")
                
                time.sleep(0.1)
                
            except Exception as e:
                print(f" 失败: {e}")
        
        conn.close()
        print(f"✅ 成分股采集完成，共 {total_count} 条")
        return total_count
    
    def collect_daily(self, start_date: str, end_date: str) -> int:
        """采集概念日行情"""
        print(f"📊 采集概念日行情 ({start_date} ~ {end_date})...")
        
        # 获取交易日列表
        trading_dates = self.tushare.get_trade_calendar(
            self._date_to_tushare(start_date),
            self._date_to_tushare(end_date)
        )
        
        if not trading_dates:
            print("⚠️ 未获取到交易日历")
            return 0
        
        print(f"  共 {len(trading_dates)} 个交易日")
        
        total_count = 0
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for trade_date in trading_dates:
            print(f"  采集 {trade_date}...", end='')
            
            try:
                data = self.tushare.get_ths_concept_daily(trade_date=trade_date)
                
                if data and data.get('items'):
                    items = data['items']
                    count = 0
                    for item in items:
                        try:
                            # fields: ts_code,trade_date,pre_close,open,close,high,low,pct_change,vol,turnover_rate,total_mv,float_mv
                            cursor.execute('''
                                INSERT OR REPLACE INTO ths_concept_daily
                                (trade_date, concept_code, concept_name, pre_close, open, close, high, low,
                                 pct_change, vol, turnover_rate, total_mv, float_mv)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                self._tushare_to_date(item[1]),  # trade_date
                                item[0],  # concept_code
                                None,  # concept_name
                                item[2] if len(item) > 2 else None,
                                item[3] if len(item) > 3 else None,
                                item[4] if len(item) > 4 else None,
                                item[5] if len(item) > 5 else None,
                                item[6] if len(item) > 6 else None,
                                item[7] if len(item) > 7 else None,
                                item[8] if len(item) > 8 else None,
                                item[9] if len(item) > 9 else None,
                                item[10] if len(item) > 10 else None,
                                item[11] if len(item) > 11 else None,
                            ))
                            count += 1
                        except Exception:
                            pass
                    
                    conn.commit()
                    total_count += count
                    print(f" {count} 条")
                else:
                    print(" 无数据")
                
            except Exception as e:
                print(f" 失败: {e}")
            
            time.sleep(0.1)
        
        conn.close()
        print(f"✅ 概念日行情采集完成，共 {total_count} 条")
        return total_count
    
    def collect_hot_rank(self, start_date: str = None, end_date: str = None, 
                         is_new: str = 'N') -> int:
        """采集个股热榜"""
        print(f"📊 采集个股热榜 (is_new={is_new})...")
        
        total_count = 0
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if is_new == 'Y':
            # 采集最新数据
            print("  采集最新热榜数据...", end='')
            try:
                data = self.tushare.get_ths_hot_rank(is_new='Y')
                
                if data and data.get('items'):
                    items = data['items']
                    today = datetime.now().strftime('%Y-%m-%d')
                    rank_time = datetime.now().strftime('%H:%M:%S')
                    
                    count = 0
                    for item in items:
                        try:
                            cursor.execute('''
                                INSERT OR REPLACE INTO ths_hot_rank
                                (trade_date, rank_time, ts_code, ts_name, rank, hot, 
                                 pct_change, current_price, concept, rank_reason)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                today,
                                rank_time,
                                item[1],  # ts_code
                                item[2] if len(item) > 2 else None,
                                item[3] if len(item) > 3 else None,
                                item[4] if len(item) > 4 else None,
                                item[5] if len(item) > 5 else None,
                                item[6] if len(item) > 6 else None,
                                item[7] if len(item) > 7 else None,
                                item[8] if len(item) > 8 else None,
                            ))
                            count += 1
                        except Exception:
                            pass
                    
                    conn.commit()
                    total_count += count
                    print(f" {count} 条")
                else:
                    print(" 无数据")
                    
            except Exception as e:
                print(f" 失败: {e}")
        
        elif start_date and end_date:
            # 获取交易日列表
            trading_dates = self.tushare.get_trade_calendar(
                self._date_to_tushare(start_date),
                self._date_to_tushare(end_date)
            )
            
            if not trading_dates:
                print("⚠️ 未获取到交易日历")
                return 0
            
            for trade_date in trading_dates:
                print(f"  采集 {trade_date}...", end='')
                
                try:
                    data = self.tushare.get_ths_hot_rank(trade_date=trade_date)
                    
                    if data and data.get('items'):
                        items = data['items']
                        count = 0
                        for item in items:
                            try:
                                cursor.execute('''
                                    INSERT OR REPLACE INTO ths_hot_rank
                                    (trade_date, rank_time, ts_code, ts_name, rank, hot, 
                                     pct_change, current_price, concept, rank_reason)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (
                                    self._tushare_to_date(item[0]),
                                    "15:00:00",
                                    item[1],
                                    item[2] if len(item) > 2 else None,
                                    item[3] if len(item) > 3 else None,
                                    item[4] if len(item) > 4 else None,
                                    item[5] if len(item) > 5 else None,
                                    item[6] if len(item) > 6 else None,
                                    item[7] if len(item) > 7 else None,
                                    item[8] if len(item) > 8 else None,
                                ))
                                count += 1
                            except Exception:
                                pass
                        
                        conn.commit()
                        total_count += count
                        print(f" {count} 条")
                    else:
                        print(" 无数据")
                        
                except Exception as e:
                    print(f" 失败: {e}")
                
                time.sleep(0.1)
        
        conn.close()
        print(f"✅ 个股热榜采集完成，共 {total_count} 条")
        return total_count
    
    def collect_limit_list(self, start_date: str = None, end_date: str = None,
                           limit_type: str = '涨停池') -> int:
        """采集涨跌停榜单"""
        print(f"📊 采集涨跌停榜单 (limit_type={limit_type})...")
        
        if not start_date or not end_date:
            print("⚠️ 请指定日期范围")
            return 0
        
        # 获取交易日列表
        trading_dates = self.tushare.get_trade_calendar(
            self._date_to_tushare(start_date),
            self._date_to_tushare(end_date)
        )
        
        if not trading_dates:
            print("⚠️ 未获取到交易日历")
            return 0
        
        print(f"  共 {len(trading_dates)} 个交易日")
        
        total_count = 0
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        for trade_date in trading_dates:
            print(f"  采集 {trade_date}...", end='')
            
            try:
                data = self.tushare.get_ths_limit_list(trade_date=trade_date, limit_type=limit_type)
                
                if data and data.get('items'):
                    items = data['items']
                    count = 0
                    for item in items:
                        try:
                            cursor.execute('''
                                INSERT OR REPLACE INTO ths_limit_list
                                (trade_date, ts_code, ts_name, price, pct_chg, limit_type,
                                 tag, status, lu_desc, open_num, first_lu_time, last_lu_time,
                                 limit_order, limit_amount, lu_limit_order, turnover_rate,
                                 turnover, free_float, sum_float, limit_up_suc_rate, market_type)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ''', (
                                self._tushare_to_date(item[0]),
                                item[1],
                                item[2] if len(item) > 2 else None,
                                item[3] if len(item) > 3 else None,
                                item[4] if len(item) > 4 else None,
                                item[5] if len(item) > 5 else limit_type,
                                item[6] if len(item) > 6 else None,
                                item[7] if len(item) > 7 else None,
                                item[8] if len(item) > 8 else None,
                                item[9] if len(item) > 9 else None,
                                item[10] if len(item) > 10 else None,
                                item[11] if len(item) > 11 else None,
                                item[12] if len(item) > 12 else None,
                                item[13] if len(item) > 13 else None,
                                item[14] if len(item) > 14 else None,
                                item[15] if len(item) > 15 else None,
                                item[16] if len(item) > 16 else None,
                                item[17] if len(item) > 17 else None,
                                item[18] if len(item) > 18 else None,
                                item[19] if len(item) > 19 else None,
                                item[20] if len(item) > 20 else None,
                            ))
                            count += 1
                        except Exception:
                            pass
                    
                    conn.commit()
                    total_count += count
                    print(f" {count} 条")
                else:
                    print(" 无数据")
                    
            except Exception as e:
                print(f" 失败: {e}")
            
            time.sleep(0.1)
        
        conn.close()
        print(f"✅ 涨跌停榜单采集完成，共 {total_count} 条")
        return total_count
    
    def collect_all(self, days: int = 60) -> Dict[str, int]:
        """采集全部数据"""
        print(f"🚀 开始采集全部数据（最近 {days} 天）...")
        
        results = {}
        
        # 1. 概念列表
        results['concept_list'] = self.collect_concept_list()
        time.sleep(0.5)
        
        # 2. 成分股
        results['members'] = self.collect_members()
        time.sleep(0.5)
        
        # 计算日期范围
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # 3. 概念日行情
        results['daily'] = self.collect_daily(start_date, end_date)
        time.sleep(0.5)
        
        # 4. 个股热榜
        results['hot_rank'] = self.collect_hot_rank(start_date, end_date)
        time.sleep(0.5)
        
        # 5. 涨停池
        results['limit_list_up'] = self.collect_limit_list(start_date, end_date, '涨停池')
        time.sleep(0.5)
        
        # 6. 连扳池
        results['limit_list_ladder'] = self.collect_limit_list(start_date, end_date, '连扳池')
        time.sleep(0.5)
        
        # 7. 炸板池
        results['limit_list_broken'] = self.collect_limit_list(start_date, end_date, '炸板池')
        time.sleep(0.5)
        
        # 8. 跌停池
        results['limit_list_down'] = self.collect_limit_list(start_date, end_date, '跌停池')
        
        print("\n" + "=" * 50)
        print("📊 采集汇总：")
        for key, count in results.items():
            print(f"  - {key}: {count} 条")
        print("=" * 50)
        
        return results


def main():
    """命令行入口"""
    parser = argparse.ArgumentParser(description='同花顺概念数据采集工具')
    parser.add_argument('--method', type=str, required=True,
                        choices=['concept_list', 'members', 'daily', 'hot_rank', 'limit_list', 'all'],
                        help='采集方法')
    parser.add_argument('--start', type=str, help='开始日期 (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='结束日期 (YYYY-MM-DD)')
    parser.add_argument('--days', type=int, default=60, help='采集最近 N 天的数据（默认60天）')
    parser.add_argument('--is-new', type=str, default='N', choices=['Y', 'N'],
                        help='热榜专用：Y=最新数据（22:30更新），N=盘中数据')
    parser.add_argument('--limit-type', type=str, default='涨停池',
                        choices=['涨停池', '连扳池', '炸板池', '跌停池'],
                        help='板单类别（默认：涨停池）')
    
    args = parser.parse_args()
    
    # 数据库路径
    db_path = project_root / 'data' / 'dragon_stock.db'
    
    # 创建采集器
    collector = THSDataCollector(str(db_path))
    
    # 执行采集
    if args.method == 'concept_list':
        collector.collect_concept_list()
    
    elif args.method == 'members':
        collector.collect_members()
    
    elif args.method == 'daily':
        if not args.start or not args.end:
            print("⚠️ 请指定 --start 和 --end 参数")
            sys.exit(1)
        collector.collect_daily(args.start, args.end)
    
    elif args.method == 'hot_rank':
        if args.is_new == 'Y':
            collector.collect_hot_rank(is_new='Y')
        elif args.start and args.end:
            collector.collect_hot_rank(args.start, args.end)
        else:
            print("⚠️ 请指定 --is-new Y 或 --start/--end 参数")
            sys.exit(1)
    
    elif args.method == 'limit_list':
        if not args.start or not args.end:
            print("⚠️ 请指定 --start 和 --end 参数")
            sys.exit(1)
        collector.collect_limit_list(args.start, args.end, args.limit_type)
    
    elif args.method == 'all':
        collector.collect_all(args.days)


if __name__ == '__main__':
    main()
