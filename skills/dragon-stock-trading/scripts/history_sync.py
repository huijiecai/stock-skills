#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史数据同步器
批量同步历史K线数据到本地数据库
"""

import requests
import sqlite3
import os
import time
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from config_loader import config
from itick_client import ItickClient


class HistorySyncer:
    """历史数据同步器"""
    
    def __init__(self, db_path: str = None, api_key: str = None, base_url: str = None):
        self.db_path = db_path or config.get_db_path()
        
        # 使用统一的 itick 客户端
        self.client = ItickClient(api_key, base_url)
        
        # 从配置文件加载涨停阈值
        self.limit_up_threshold = {
            'main': config.get_limit_up_threshold('main_board'),
            'growth': config.get_limit_up_threshold('growth_board'),
            'st': config.get_limit_up_threshold('st_stock')
        }
    
    def _is_limit_up(self, stock_code: str, stock_name: str, change_percent: float) -> bool:
        """判断是否涨停"""
        if stock_name and 'ST' in stock_name:
            return change_percent >= self.limit_up_threshold['st']
        if stock_code.startswith('3') or stock_code.startswith('688'):
            return change_percent >= self.limit_up_threshold['growth']
        return change_percent >= self.limit_up_threshold['main']
    
    def _is_limit_down(self, stock_code: str, stock_name: str, change_percent: float) -> bool:
        """判断是否跌停"""
        if stock_name and 'ST' in stock_name:
            return change_percent <= -self.limit_up_threshold['st']
        if stock_code.startswith('3') or stock_code.startswith('688'):
            return change_percent <= -self.limit_up_threshold['growth']
        return change_percent <= -self.limit_up_threshold['main']
    
    def sync_stock_klines(self, stock_code: str, region: str, start_date: str, end_date: str) -> int:
        """
        同步单只股票的K线数据
        
        Args:
            stock_code: 股票代码
            region: 市场（SH/SZ）
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
        
        Returns:
            成功同步的K线数量
        """
        # 使用 itick 客户端获取K线数据
        klines = self.client.get_stock_kline(stock_code, region, period='day', count=100)
        
        if not klines:
            return 0
        
        # 获取股票名称
        stock_name = self._get_stock_name(stock_code, region)
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            count = 0
            for kline in klines:
                # 解析K线数据
                timestamp = kline.get('t', 0)
                trade_date = datetime.fromtimestamp(timestamp/1000).strftime('%Y-%m-%d')
                
                # 过滤日期范围
                if trade_date < start_date or trade_date > end_date:
                    continue
                
                open_price = kline.get('o', 0)
                high_price = kline.get('h', 0)
                low_price = kline.get('l', 0)
                close_price = kline.get('c', 0)
                volume = kline.get('v', 0)
                turnover = kline.get('a', 0)  # 成交额
                
                # 计算涨跌幅（需要前一日收盘价）
                cursor.execute('''
                SELECT close_price FROM stock_daily 
                WHERE stock_code = ? AND trade_date < ?
                ORDER BY trade_date DESC LIMIT 1
                ''', (stock_code, trade_date))
                
                row = cursor.fetchone()
                pre_close = row[0] if row else open_price
                
                change_amount = close_price - pre_close
                change_percent = change_amount / pre_close if pre_close > 0 else 0
                
                # 判断涨停/跌停
                is_limit_up = 1 if self._is_limit_up(stock_code, stock_name, change_percent) else 0
                is_limit_down = 1 if self._is_limit_down(stock_code, stock_name, change_percent) else 0
                
                # 计算连板天数
                streak_days = self._calculate_streak_days(cursor, stock_code, trade_date, is_limit_up)
                
                # 保存到数据库
                try:
                    cursor.execute('''
                    INSERT OR REPLACE INTO stock_daily 
                    (trade_date, stock_code, stock_name, market, open_price, high_price, 
                     low_price, close_price, pre_close, change_amount, change_percent,
                     volume, turnover, is_limit_up, is_limit_down, streak_days)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        trade_date, stock_code, stock_name, region,
                        open_price, high_price, low_price, close_price,
                        pre_close, change_amount, change_percent,
                        volume, turnover, is_limit_up, is_limit_down, streak_days
                    ))
                    count += 1
                except Exception as e:
                    print(f"❌ 保存 {stock_code} {trade_date} 数据失败: {e}")
            
            conn.commit()
            conn.close()
            
            return count
        
        except Exception as e:
            return 0
    
    def _get_stock_name(self, stock_code: str, region: str) -> str:
        """获取股票名称"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT stock_name FROM stock_info WHERE stock_code = ?', (stock_code,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return row[0]
        
        # 如果本地没有，尝试从API获取
        quote = self.client.get_stock_quote(stock_code, region)
        if quote:
            return quote.get('n', stock_code)
        
        return stock_code
    
    def _calculate_streak_days(self, cursor, stock_code: str, trade_date: str, is_limit_up: int) -> int:
        """计算连板天数"""
        if not is_limit_up:
            return 0
        
        cursor.execute('''
        SELECT trade_date, is_limit_up, streak_days
        FROM stock_daily
        WHERE stock_code = ? AND trade_date < ?
        ORDER BY trade_date DESC
        LIMIT 1
        ''', (stock_code, trade_date))
        
        row = cursor.fetchone()
        if not row:
            return 1
        
        last_trade_date, last_is_limit_up, last_streak_days = row
        
        if last_is_limit_up:
            return last_streak_days + 1
        else:
            return 1
    
    def sync_all_stocks_history(self, stock_list: List[tuple], days: int = 10) -> Dict:
        """
        批量同步多只股票的历史数据
        
        Args:
            stock_list: 股票列表 [(code, name, region), ...]
            days: 同步最近N天数据
        
        Returns:
            同步统计
        """
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        print(f"📅 同步日期范围: {start_date} 至 {end_date}")
        print(f"📊 股票数量: {len(stock_list)}")
        
        total_stocks = len(stock_list)
        success_stocks = 0
        total_klines = 0
        
        for idx, (stock_code, stock_name, region) in enumerate(stock_list, 1):
            # 排除 ST 股票
            if stock_name and 'ST' in stock_name:
                continue
            
            print(f"[{idx}/{total_stocks}] 同步 {stock_name}({stock_code})...", end=' ')
            
            count = self.sync_stock_klines(stock_code, region, start_date, end_date)
            
            if count > 0:
                success_stocks += 1
                total_klines += count
                print(f"✅ {count}条")
            else:
                print("❌ 失败")
            
            # 避免请求过快
            time.sleep(0.1)
        
        stats = {
            'total_stocks': total_stocks,
            'success_stocks': success_stocks,
            'total_klines': total_klines,
            'start_date': start_date,
            'end_date': end_date
        }
        
        print(f"\n✅ 同步完成！")
        print(f"  - 成功股票: {success_stocks}/{total_stocks}")
        print(f"  - K线总数: {total_klines}")
        
        return stats
    
    def get_stock_list_from_db(self) -> List[tuple]:
        """从数据库获取股票列表"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT DISTINCT stock_code, stock_name, market 
        FROM stock_daily 
        ORDER BY stock_code
        ''')
        
        stock_list = cursor.fetchall()
        conn.close()
        
        return stock_list


def main():
    """命令行测试入口"""
    import sys
    from pathlib import Path
    
    script_dir = Path(__file__).resolve().parent
    # 计算项目根目录（需要往上3层）
    project_root = script_dir.parent.parent.parent
    db_path = project_root / "data" / "dragon_stock.db"
    
    if not db_path.exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        return
    
    # 使用配置文件中的设置
    syncer = HistorySyncer(str(db_path))
    
    # 获取要同步的天数
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    
    # 从数据库获取已有股票列表
    stock_list = syncer.get_stock_list_from_db()
    
    if not stock_list:
        print("❌ 数据库中没有股票数据，请先运行 market_fetcher.py 采集当日数据")
        return
    
    print(f"📂 从数据库中找到 {len(stock_list)} 只股票")
    
    # 同步历史数据
    syncer.sync_all_stocks_history(stock_list, days)


if __name__ == "__main__":
    main()
