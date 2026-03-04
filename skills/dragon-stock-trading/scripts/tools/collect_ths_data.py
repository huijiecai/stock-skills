#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同花顺数据采集器

功能：
1. 采集同花顺概念列表
2. 采集概念成分股
3. 采集概念日行情
4. 采个股热榜
5. 采集涨跌停榜单（连板天梯）

使用方法：
    # 采集概念列表
    python collect_ths_data.py --method concept_list
    
    # 采集概念成分股
    python collect_ths_data.py --method members
    
    # 采集概念日行情
    python collect_ths_data.py --method daily --start 2026-03-01 --end 2026-03-02
    
    # 采集个股热榜
    python collect_ths_data.py --method hot_rank --start 2026-03-01 --end 2026-03-02
    
    # 采集涨跌停榜单
    python collect_ths_data.py --method limit_list --start 2026-03-01 --end 2026-03-02
    
    # 采集全部数据
    python collect_ths_data.py --method all --days 60
"""

import sys
import sqlite3
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tushare_client import tushare_client


class ThsDataCollector:
    """同花顺数据采集器"""
    
    def __init__(self, db_path: str = None):
        self._setup_logging()
        
        # 数据库路径
        if db_path:
            self.db_path = db_path
        else:
            # 从 tools 目录往上找到项目根目录
            # tools -> scripts -> dragon-stock-trading -> skills -> stock (project root)
            project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
            self.db_path = str(project_root / "data" / "dragon_stock.db")
        
        self.logger.info(f"数据库路径: {self.db_path}")
    
    def _setup_logging(self):
        """配置日志"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        self.logger = logging.getLogger(__name__)
    
    def _get_conn(self):
        """获取数据库连接"""
        return sqlite3.connect(self.db_path)
    
    def _date_to_tushare(self, date_str: str) -> str:
        """转换日期格式：2026-03-01 -> 20260301"""
        return date_str.replace('-', '')
    
    def _tushare_to_date(self, ts_date: str) -> str:
        """转换日期格式：20260301 -> 2026-03-01"""
        if len(ts_date) == 8:
            return f"{ts_date[:4]}-{ts_date[4:6]}-{ts_date[6:8]}"
        return ts_date
    
    # ==================== 概念列表 ====================
    
    def collect_concept_list(self) -> int:
        """
        采集概念列表
        
        Returns:
            插入记录数
        """
        self.logger.info("📥 开始采集概念列表...")
        
        data = tushare_client.get_ths_concept_list()
        if not data or not data.get('items'):
            self.logger.warning("未获取到概念列表数据")
            return 0
        
        items = data['items']
        self.logger.info(f"获取到 {len(items)} 条概念数据")
        
        conn = self._get_conn()
        cursor = conn.cursor()
        
        count = 0
        for item in items:
            try:
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
                self.logger.warning(f"插入概念 {item[0]} 失败: {e}")
        
        conn.commit()
        conn.close()
        
        self.logger.info(f"✅ 概念列表采集完成，插入 {count} 条记录")
        return count
    
    # ==================== 概念成分股 ====================
    
    def collect_members(self) -> int:
        """
        采集所有概念的成分股
        
        Returns:
            插入记录数
        """
        self.logger.info("📥 开始采集概念成分股...")
        
        # 先获取概念列表
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT ts_code, name FROM ths_concept")
        concepts = cursor.fetchall()
        conn.close()
        
        if not concepts:
            self.logger.warning("概念列表为空，请先采集概念列表")
            return 0
        
        self.logger.info(f"共有 {len(concepts)} 个概念需要采集")
        
        total_count = 0
        for i, (concept_code, concept_name) in enumerate(concepts):
            self.logger.info(f"[{i+1}/{len(concepts)}] 采集 {concept_name}...")
            
            data = tushare_client.get_ths_concept_member(concept_code)
            if not data or not data.get('items'):
                self.logger.warning(f"未获取到 {concept_name} 的成分股")
                time.sleep(0.1)
                continue
            
            items = data['items']
            
            conn = self._get_conn()
            cursor = conn.cursor()
            
            for item in items:
                try:
                    # item: [concept_ts_code, stock_code, stock_name]
                    stock_code = item[1].replace('.SZ', '').replace('.SH', '').replace('.BJ', '') if len(item) > 1 else None
                    stock_name = item[2] if len(item) > 2 else None
                    
                    if not stock_code:
                        continue
                    
                    cursor.execute('''
                        INSERT OR REPLACE INTO ths_concept_member 
                        (concept_code, concept_name, stock_code, stock_name, updated_at)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (concept_code, concept_name, stock_code, stock_name))
                    
                    total_count += 1
                except Exception as e:
                    self.logger.warning(f"插入成分股失败: {e}")
            
            conn.commit()
            conn.close()
            
            time.sleep(0.1)  # 避免请求过快
        
        self.logger.info(f"✅ 成分股采集完成，插入 {total_count} 条记录")
        return total_count
    
    # ==================== 概念日行情 ====================
    
    def collect_concept_daily(self, start_date: str, end_date: str) -> int:
        """
        采集概念日行情
        
        Args:
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            
        Returns:
            插入记录数
        """
        self.logger.info(f"📥 开始采集概念日行情 ({start_date} ~ {end_date})...")
        
        # 获取交易日列表
        trading_dates = tushare_client.get_trade_calendar(
            self._date_to_tushare(start_date),
            self._date_to_tushare(end_date)
        )
        
        if not trading_dates:
            self.logger.warning("未获取到交易日历")
            return 0
        
        self.logger.info(f"共有 {len(trading_dates)} 个交易日")
        
        total_count = 0
        for trade_date in trading_dates:
            self.logger.info(f"采集 {trade_date}...")
            
            data = tushare_client.get_ths_concept_daily(trade_date=trade_date)
            if not data or not data.get('items'):
                self.logger.warning(f"未获取到 {trade_date} 的数据")
                time.sleep(0.1)
                continue
            
            items = data['items']
            
            conn = self._get_conn()
            cursor = conn.cursor()
            
            for item in items:
                try:
                    # fields: ts_code,trade_date,pre_close,open,close,high,low,pct_change,vol,turnover_rate,total_mv,float_mv
                    cursor.execute('''
                        INSERT OR REPLACE INTO ths_concept_daily 
                        (trade_date, concept_code, concept_name, pre_close, open, close, high, low, 
                         pct_change, vol, turnover_rate, total_mv, float_mv, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (
                        self._tushare_to_date(item[1]),  # trade_date
                        item[0],  # concept_code
                        None,  # concept_name (API不返回，需要关联查询)
                        item[2] if len(item) > 2 else None,  # pre_close
                        item[3] if len(item) > 3 else None,  # open
                        item[4] if len(item) > 4 else None,  # close
                        item[5] if len(item) > 5 else None,  # high
                        item[6] if len(item) > 6 else None,  # low
                        item[7] if len(item) > 7 else None,  # pct_change
                        item[8] if len(item) > 8 else None,  # vol
                        item[9] if len(item) > 9 else None,  # turnover_rate
                        item[10] if len(item) > 10 else None,  # total_mv
                        item[11] if len(item) > 11 else None,  # float_mv
                    ))
                    
                    total_count += 1
                except Exception as e:
                    self.logger.warning(f"插入数据失败: {e}")
            
            conn.commit()
            conn.close()
            
            time.sleep(0.1)
        
        self.logger.info(f"✅ 概念日行情采集完成，插入 {total_count} 条记录")
        return total_count
    
    # ==================== 个股热榜 ====================
    
    def collect_hot_rank(self, start_date: str = None, end_date: str = None, 
                         is_new: str = 'N') -> int:
        """
        采集个股热榜
        
        Args:
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            is_new: 是否最新（Y=最新数据22:30更新，N=盘中数据）
            
        Returns:
            插入记录数
        """
        self.logger.info(f"📥 开始采集个股热榜...")
        
        if start_date and end_date:
            # 按日期范围采集
            trading_dates = tushare_client.get_trade_calendar(
                self._date_to_tushare(start_date),
                self._date_to_tushare(end_date)
            )
        else:
            # 采集最新
            trading_dates = [datetime.now().strftime('%Y%m%d')]
        
        if not trading_dates:
            self.logger.warning("未获取到交易日历")
            return 0
        
        total_count = 0
        for trade_date in trading_dates:
            self.logger.info(f"采集 {trade_date}...")
            
            data = tushare_client.get_ths_hot_rank(trade_date=trade_date, is_new=is_new)
            if not data or not data.get('items'):
                self.logger.warning(f"未获取到 {trade_date} 的热榜数据")
                time.sleep(0.1)
                continue
            
            items = data['items']
            
            conn = self._get_conn()
            cursor = conn.cursor()
            
            for item in items:
                try:
                    # fields: trade_date,ts_code,ts_name,rank,hot,pct_change,current_price,concept,rank_reason
                    cursor.execute('''
                        INSERT OR REPLACE INTO ths_hot_rank 
                        (trade_date, rank_time, ts_code, ts_name, rank, hot, pct_change, 
                         current_price, concept, rank_reason, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (
                        self._tushare_to_date(item[0]),  # trade_date
                        "22:30:00" if is_new == 'Y' else "15:00:00",  # rank_time
                        item[1],  # ts_code
                        item[2] if len(item) > 2 else None,  # ts_name
                        item[3] if len(item) > 3 else None,  # rank
                        item[4] if len(item) > 4 else None,  # hot
                        item[5] if len(item) > 5 else None,  # pct_change
                        item[6] if len(item) > 6 else None,  # current_price
                        item[7] if len(item) > 7 else None,  # concept
                        item[8] if len(item) > 8 else None,  # rank_reason
                    ))
                    
                    total_count += 1
                except Exception as e:
                    self.logger.warning(f"插入数据失败: {e}")
            
            conn.commit()
            conn.close()
            
            time.sleep(0.1)
        
        self.logger.info(f"✅ 个股热榜采集完成，插入 {total_count} 条记录")
        return total_count
    
    # ==================== 涨跌停榜单 ====================
    
    def collect_limit_list(self, start_date: str, end_date: str, 
                           limit_type: str = '涨停池') -> int:
        """
        采集涨跌停榜单
        
        Args:
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            limit_type: 板单类别（涨停池/连扳池/炸板池/跌停池）
            
        Returns:
            插入记录数
        """
        self.logger.info(f"📥 开始采集涨跌停榜单 ({limit_type})...")
        
        # 获取交易日列表
        trading_dates = tushare_client.get_trade_calendar(
            self._date_to_tushare(start_date),
            self._date_to_tushare(end_date)
        )
        
        if not trading_dates:
            self.logger.warning("未获取到交易日历")
            return 0
        
        self.logger.info(f"共有 {len(trading_dates)} 个交易日")
        
        total_count = 0
        for trade_date in trading_dates:
            self.logger.info(f"采集 {trade_date}...")
            
            data = tushare_client.get_ths_limit_list(trade_date=trade_date, limit_type=limit_type)
            if not data or not data.get('items'):
                self.logger.warning(f"未获取到 {trade_date} 的数据")
                time.sleep(0.1)
                continue
            
            items = data['items']
            
            conn = self._get_conn()
            cursor = conn.cursor()
            
            for item in items:
                try:
                    # fields: trade_date,ts_code,ts_name,price,pct_chg,limit_type,tag,status,lu_desc,
                    #         open_num,first_lu_time,last_lu_time,limit_order,limit_amount,lu_limit_order,
                    #         turnover_rate,turnover,free_float,sum_float,limit_up_suc_rate,market_type
                    cursor.execute('''
                        INSERT OR REPLACE INTO ths_limit_list 
                        (trade_date, ts_code, ts_name, price, pct_chg, limit_type, tag, status, 
                         lu_desc, open_num, first_lu_time, last_lu_time, limit_order, limit_amount, 
                         lu_limit_order, turnover_rate, turnover, free_float, sum_float, 
                         limit_up_suc_rate, market_type, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ''', (
                        self._tushare_to_date(item[0]),  # trade_date
                        item[1],  # ts_code
                        item[2] if len(item) > 2 else None,  # ts_name
                        item[3] if len(item) > 3 else None,  # price
                        item[4] if len(item) > 4 else None,  # pct_chg
                        item[5] if len(item) > 5 else limit_type,  # limit_type
                        item[6] if len(item) > 6 else None,  # tag
                        item[7] if len(item) > 7 else None,  # status
                        item[8] if len(item) > 8 else None,  # lu_desc
                        item[9] if len(item) > 9 else None,  # open_num
                        item[10] if len(item) > 10 else None,  # first_lu_time
                        item[11] if len(item) > 11 else None,  # last_lu_time
                        item[12] if len(item) > 12 else None,  # limit_order
                        item[13] if len(item) > 13 else None,  # limit_amount
                        item[14] if len(item) > 14 else None,  # lu_limit_order
                        item[15] if len(item) > 15 else None,  # turnover_rate
                        item[16] if len(item) > 16 else None,  # turnover
                        item[17] if len(item) > 17 else None,  # free_float
                        item[18] if len(item) > 18 else None,  # sum_float
                        item[19] if len(item) > 19 else None,  # limit_up_suc_rate
                        item[20] if len(item) > 20 else None,  # market_type
                    ))
                    
                    total_count += 1
                except Exception as e:
                    self.logger.warning(f"插入数据失败: {e}")
            
            conn.commit()
            conn.close()
            
            time.sleep(0.1)
        
        self.logger.info(f"✅ 涨跌停榜单采集完成，插入 {total_count} 条记录")
        return total_count


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='同花顺数据采集器')
    parser.add_argument('--method', type=str, default='all',
                        choices=['concept_list', 'members', 'daily', 'hot_rank', 'limit_list', 'all'],
                        help='采集方法')
    parser.add_argument('--start', type=str, default=None,
                        help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, default=None,
                        help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--days', type=int, default=60,
                        help='采集最近 N 天的数据（默认 60 天）')
    parser.add_argument('--is-new', type=str, default='N',
                        choices=['Y', 'N'],
                        help='热榜专用：Y=最新数据（22:30更新），N=盘中数据')
    parser.add_argument('--limit-type', type=str, default='涨停池',
                        choices=['涨停池', '连扳池', '炸板池', '跌停池'],
                        help='涨跌停榜单类型')
    
    args = parser.parse_args()
    
    # 计算日期范围
    if args.start:
        start_date = args.start
        end_date = args.end if args.end else datetime.now().strftime('%Y-%m-%d')
    else:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
    
    collector = ThsDataCollector()
    
    try:
        if args.method == 'concept_list' or args.method == 'all':
            collector.collect_concept_list()
        
        if args.method == 'members' or args.method == 'all':
            collector.collect_members()
        
        if args.method == 'daily' or args.method == 'all':
            collector.collect_concept_daily(start_date, end_date)
        
        if args.method == 'hot_rank' or args.method == 'all':
            collector.collect_hot_rank(start_date, end_date, args.is_new)
        
        if args.method == 'limit_list' or args.method == 'all':
            for lt in ['涨停池', '连扳池', '炸板池', '跌停池']:
                collector.collect_limit_list(start_date, end_date, lt)
        
        print("\n🎉 采集任务完成！")
        
    except KeyboardInterrupt:
        print("\n⚠️ 用户中断采集")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 采集失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
