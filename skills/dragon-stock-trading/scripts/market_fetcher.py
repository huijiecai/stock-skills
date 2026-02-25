#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据采集器
负责获取全市场股票数据并计算市场情绪指标
"""

import requests
import sqlite3
import os
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import time
from config_loader import config
from itick_client import ItickClient


class MarketDataFetcher:
    """市场数据采集器"""
    
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
        """
        判断是否涨停
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            change_percent: 涨跌幅（小数，如 0.10 表示 10%）
        
        Returns:
            是否涨停
        """
        # ST 股票判断
        if stock_name and 'ST' in stock_name:
            return change_percent >= self.limit_up_threshold['st']
        
        # 创业板（3开头）和科创板（688开头）
        if stock_code.startswith('3') or stock_code.startswith('688'):
            return change_percent >= self.limit_up_threshold['growth']
        
        # 主板和中小板
        return change_percent >= self.limit_up_threshold['main']
    
    def _is_limit_down(self, stock_code: str, stock_name: str, change_percent: float) -> bool:
        """判断是否跌停"""
        # ST 股票判断
        if stock_name and 'ST' in stock_name:
            return change_percent <= -self.limit_up_threshold['st']
        
        # 创业板和科创板
        if stock_code.startswith('3') or stock_code.startswith('688'):
            return change_percent <= -self.limit_up_threshold['growth']
        
        # 主板和中小板
        return change_percent <= -self.limit_up_threshold['main']
    
    def fetch_stock_quote(self, stock_code: str, region: str) -> Optional[Dict]:
        """
        获取单个股票实时行情
        
        Args:
            stock_code: 股票代码
            region: 市场（SH/SZ）
        
        Returns:
            行情数据字典
        """
        return self.client.get_stock_quote(stock_code, region)
    
    def fetch_all_stocks_daily(self, trade_date: str, stock_list: List[tuple]) -> int:
        """
        获取全市场股票日行情
        
        Args:
            trade_date: 交易日期 YYYY-MM-DD
            stock_list: 股票列表 [(code, name, region), ...]
        
        Returns:
            成功保存的股票数量
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        success_count = 0
        total = len(stock_list)
        
        print(f"📊 开始获取 {trade_date} 全市场行情，共 {total} 只股票...")
        
        for idx, (stock_code, stock_name, region) in enumerate(stock_list, 1):
            # 排除 ST 股票
            if stock_name and 'ST' in stock_name:
                continue
            
            # 显示进度
            if idx % 100 == 0:
                print(f"进度: {idx}/{total} ({idx/total*100:.1f}%)")
            
            quote_data = self.fetch_stock_quote(stock_code, region)
            if not quote_data:
                continue
            
            # 解析数据
            close_price = quote_data.get('ld', 0)  # 最新价
            pre_close = quote_data.get('p', 0)     # 昨收
            change_percent = quote_data.get('chp', 0) / 100  # 涨跌幅转为小数
            change_amount = quote_data.get('ch', 0)
            
            # 判断涨停/跌停
            is_limit_up = 1 if self._is_limit_up(stock_code, stock_name, change_percent) else 0
            is_limit_down = 1 if self._is_limit_down(stock_code, stock_name, change_percent) else 0
            
            # 计算连板天数（需要查询历史数据）
            streak_days = self._calculate_streak_days(cursor, stock_code, trade_date, is_limit_up)
            
            # 保存到数据库
            try:
                cursor.execute('''
                INSERT OR REPLACE INTO stock_daily 
                (trade_date, stock_code, stock_name, market, open_price, high_price, 
                 low_price, close_price, pre_close, change_amount, change_percent,
                 volume, turnover, turnover_rate, is_limit_up, is_limit_down, streak_days)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    trade_date, stock_code, stock_name, region,
                    quote_data.get('o', 0),    # 开盘价
                    quote_data.get('h', 0),    # 最高价
                    quote_data.get('l', 0),    # 最低价
                    close_price,
                    pre_close,
                    change_amount,
                    change_percent,
                    quote_data.get('v', 0),    # 成交量
                    quote_data.get('tu', 0),   # 成交额
                    quote_data.get('tr', 0),   # 换手率
                    is_limit_up,
                    is_limit_down,
                    streak_days
                ))
                success_count += 1
            except Exception as e:
                print(f"❌ 保存 {stock_code} 数据失败: {e}")
            
            # 避免请求过快
            time.sleep(0.05)
        
        conn.commit()
        conn.close()
        
        print(f"✅ 完成！成功保存 {success_count}/{total} 只股票数据")
        return success_count
    
    def _calculate_streak_days(self, cursor, stock_code: str, trade_date: str, is_limit_up: int) -> int:
        """
        计算连板天数
        
        Args:
            cursor: 数据库游标
            stock_code: 股票代码
            trade_date: 当前交易日
            is_limit_up: 当日是否涨停
        
        Returns:
            连板天数
        """
        if not is_limit_up:
            return 0
        
        # 查询该股票历史涨停记录
        cursor.execute('''
        SELECT trade_date, is_limit_up, streak_days
        FROM stock_daily
        WHERE stock_code = ? AND trade_date < ?
        ORDER BY trade_date DESC
        LIMIT 10
        ''', (stock_code, trade_date))
        
        rows = cursor.fetchall()
        if not rows:
            return 1  # 首次涨停
        
        # 检查昨日是否涨停
        last_trade_date, last_is_limit_up, last_streak_days = rows[0]
        
        if last_is_limit_up:
            return last_streak_days + 1
        else:
            return 1  # 重新开始连板
    
    def calculate_market_sentiment(self, trade_date: str) -> Dict:
        """
        计算市场情绪指标
        
        Args:
            trade_date: 交易日期
        
        Returns:
            市场情绪数据
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 统计涨停/跌停家数
        cursor.execute('''
        SELECT 
            SUM(CASE WHEN is_limit_up = 1 THEN 1 ELSE 0 END) as limit_up_count,
            SUM(CASE WHEN is_limit_down = 1 THEN 1 ELSE 0 END) as limit_down_count,
            MAX(streak_days) as max_streak,
            SUM(turnover) as total_turnover
        FROM stock_daily
        WHERE trade_date = ?
        ''', (trade_date,))
        
        row = cursor.fetchone()
        limit_up_count = row[0] or 0
        limit_down_count = row[1] or 0
        max_streak = row[2] or 0
        total_turnover = (row[3] or 0) / 100000000  # 转为亿元
        
        # 获取指数数据（需要单独调用 itick API）
        sh_change = self._get_index_change('000001', 'SH')  # 上证指数
        sz_change = self._get_index_change('399001', 'SZ')  # 深证成指
        cy_change = self._get_index_change('399006', 'SZ')  # 创业板指
        
        # 保存到数据库
        cursor.execute('''
        INSERT OR REPLACE INTO market_sentiment
        (trade_date, limit_up_count, limit_down_count, max_streak, 
         sh_index_change, sz_index_change, cy_index_change, total_turnover)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (trade_date, limit_up_count, limit_down_count, max_streak,
              sh_change, sz_change, cy_change, total_turnover))
        
        conn.commit()
        conn.close()
        
        sentiment = {
            'trade_date': trade_date,
            'limit_up_count': limit_up_count,
            'limit_down_count': limit_down_count,
            'max_streak': max_streak,
            'sh_index_change': sh_change,
            'sz_index_change': sz_change,
            'cy_index_change': cy_change,
            'total_turnover': total_turnover
        }
        
        print(f"📊 市场情绪: 涨停 {limit_up_count}家, 跌停 {limit_down_count}家, "
              f"最高连板 {max_streak}板, 成交额 {total_turnover:.2f}亿")
        
        return sentiment
    
    def _get_index_change(self, index_code: str, region: str) -> float:
        """获取指数涨跌幅"""
        data = self.client.get_index_quote(index_code, region)
        if data:
            return data.get('chp', 0) / 100
        return 0.0
    
    def load_stock_list(self, stock_list_file: str = None) -> List[tuple]:
        """
        从 JSON 文件加载关注股票池
        
        Args:
            stock_list_file: 股票列表文件路径，默认为 data/stock_list.json
        
        Returns:
            股票列表 [(code, name, market), ...]
        """
        if stock_list_file is None:
            from pathlib import Path
            script_dir = Path(__file__).resolve().parent
            project_root = script_dir.parent
            stock_list_file = project_root / "data" / "stock_list.json"
        
        import json
        
        try:
            with open(stock_list_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            stocks = data.get('stocks', [])
            stock_list = [
                (stock['code'], stock['name'], stock['market'])
                for stock in stocks
            ]
            
            print(f"✅ 成功加载 {len(stock_list)} 只关注股票")
            return stock_list
            
        except Exception as e:
            print(f"❌ 加载股票列表失败: {e}")
            return []


def main():
    """命令行测试入口"""
    import sys
    from pathlib import Path
    
    # 获取数据库路径和API密钥
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    db_path = project_root / "data" / "dragon_stock.db"
    
    if not db_path.exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        print("请先运行: python db_init.py")
        return
    
    # 使用配置文件中的设置
    fetcher = MarketDataFetcher(str(db_path))
    
    # 使用今天的日期
    today = datetime.now().strftime('%Y-%m-%d')
    
    if len(sys.argv) > 1:
        trade_date = sys.argv[1]
    else:
        trade_date = today
    
    print(f"📅 交易日期: {trade_date}")
    
    # 从 JSON 文件加载关注股票池
    stock_list = fetcher.load_stock_list()
    
    if not stock_list:
        print("❌ 股票列表为空，退出")
        return
    
    # 采集数据
    fetcher.fetch_all_stocks_daily(trade_date, stock_list)
    
    # 计算市场情绪
    fetcher.calculate_market_sentiment(trade_date)


if __name__ == "__main__":
    main()
