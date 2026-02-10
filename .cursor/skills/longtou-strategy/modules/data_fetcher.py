"""
数据获取模块
负责从akshare和tushare获取股票数据

新架构：优先读取本地缓存，若缓存不存在再调用API
"""

import akshare as ak
import tushare as ts
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time
import os
import sys
import json

# 导入配置
try:
    from .config import TUSHARE_TOKEN
    ts.set_token(TUSHARE_TOKEN)
    pro = ts.pro_api()
except ImportError:
    print("⚠️  警告：未找到modules/config.py，Tushare功能不可用")
    pro = None


class DataFetcher:
    """数据获取器"""
    
    def __init__(self):
        self.today = datetime.now().strftime("%Y%m%d")
        
        # 缓存目录
        current_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(os.path.dirname(current_dir), "data")
        self.today_cache_dir = os.path.join(self.data_dir, self.today)
        
    def _load_cache(self, filename: str) -> Optional[pd.DataFrame]:
        """从缓存加载数据"""
        cache_path = os.path.join(self.today_cache_dir, filename)
        if os.path.exists(cache_path):
            try:
                if filename.endswith('.json'):
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            return pd.DataFrame(data)
                        elif isinstance(data, dict):
                            # stock_concepts.json是特殊格式
                            return data
                return None
            except Exception as e:
                print(f"⚠️  缓存加载失败：{e}")
                return None
        return None
        
    def get_limit_up_stocks(self, date: Optional[str] = None) -> pd.DataFrame:
        """
        获取涨停股票（优先缓存）
        
        Args:
            date: 日期，格式YYYYMMDD，默认今天
            
        Returns:
            DataFrame: 涨停股票列表
        """
        if date is None:
            date = self.today
        
        # 1. 尝试从缓存读取
        df = self._load_cache("limit_up_stocks.json")
        if df is not None and isinstance(df, pd.DataFrame):
            print(f"📦 从缓存读取涨停股票：{len(df)} 只")
            return df
            
        # 2. 缓存不存在，调用API
        try:
            print(f"📊 从API获取 {date} 涨停股票...")
            df = ak.stock_zt_pool_em(date=date)
            
            if df is not None and not df.empty:
                print(f"✅ 获取成功：{len(df)} 只涨停股票")
                return df
            else:
                print("⚠️  今日暂无涨停股票")
                return pd.DataFrame()
                
        except Exception as e:
            print(f"❌ 获取涨停股票失败：{e}")
            return pd.DataFrame()
    
    def get_continuous_limit_up(self, date: Optional[str] = None) -> pd.DataFrame:
        """
        获取连板股票（优先缓存）
        
        Args:
            date: 日期，格式YYYYMMDD，默认今天
            
        Returns:
            DataFrame: 连板股票列表（已按连板数排序）
        """
        if date is None:
            date = self.today
        
        # 1. 尝试从缓存读取
        df = self._load_cache("continuous_limit_up.json")
        if df is not None and isinstance(df, pd.DataFrame):
            print(f"📦 从缓存读取连板股票：{len(df)} 只")
            return df
            
        # 2. 缓存不存在，调用API
        try:
            print(f"📊 从API获取 {date} 连板股票...")
            df = ak.stock_zt_pool_strong_em(date=date)
            
            if df is not None and not df.empty:
                print(f"✅ 获取成功：{len(df)} 只连板股票")
                return df
            else:
                print("⚠️  今日暂无连板股票")
                return pd.DataFrame()
                
        except Exception as e:
            print(f"❌ 获取连板股票失败：{e}")
            return pd.DataFrame()
    
    def get_dragon_tiger_list(self, date: Optional[str] = None) -> pd.DataFrame:
        """
        获取龙虎榜数据
        
        Args:
            date: 日期，格式YYYYMMDD，默认今天
            
        Returns:
            DataFrame: 龙虎榜股票列表
        """
        if date is None:
            date = self.today
            
        try:
            print(f"📊 获取 {date} 龙虎榜...")
            # 格式转换：20250210 -> 2025-02-10
            date_str = f"{date[:4]}-{date[4:6]}-{date[6:]}"
            
            # 添加重试机制
            for retry in range(3):
                try:
                    df = ak.stock_lhb_detail_em(start_date=date_str, end_date=date_str)
                    
                    if df is not None and not df.empty:
                        print(f"✅ 获取成功：{len(df)} 只龙虎榜股票")
                        return df
                    else:
                        print("⚠️  今日龙虎榜暂无数据")
                        return pd.DataFrame()
                except Exception as e:
                    if retry < 2:
                        print(f"⚠️  获取失败，重试 {retry+1}/3...")
                        time.sleep(1)
                    else:
                        raise e
                        
        except Exception as e:
            print(f"⚠️  获取龙虎榜失败：{e}，跳过")
            return pd.DataFrame()
    
    def get_limit_down_count(self, date: Optional[str] = None) -> int:
        """
        获取跌停家数（用于判断市场状态）
        
        Args:
            date: 日期，格式YYYYMMDD，默认昨天
            
        Returns:
            int: 跌停家数
        """
        if date is None:
            # 默认获取昨天的跌停家数
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
            date = yesterday
            
        try:
            print(f"📊 获取 {date} 跌停家数...")
            df = ak.stock_zt_pool_dtgc_em(date=date)
            
            if df is not None and not df.empty:
                count = len(df)
                print(f"✅ 获取成功：{count} 家跌停")
                return count
            else:
                print("✅ 昨日无跌停")
                return 0
                
        except Exception as e:
            print(f"⚠️  获取跌停家数失败：{e}，默认为0")
            return 0
    
    def get_stock_board_concept(self, symbol: str) -> List[str]:
        """
        获取股票概念板块（优先缓存）
        
        Args:
            symbol: 股票代码（如"000001"）
            
        Returns:
            List[str]: 概念列表
        """
        # 1. 尝试从缓存读取
        cache_data = self._load_cache("stock_concepts.json")
        if cache_data is not None and isinstance(cache_data, dict):
            if symbol in cache_data:
                concepts = cache_data[symbol].get('概念', [])
                return concepts
        
        # 2. 缓存不存在，调用API（旧逻辑，但不应该走到这里）
        if pro is None:
            return []
        
        # 添加请求间隔，防止被限流
        time.sleep(0.3)
        
        try:
            # Tushare的股票代码格式：000001.SZ 或 600000.SH
            if symbol.startswith('6'):
                ts_code = f"{symbol}.SH"
            elif symbol.startswith('0') or symbol.startswith('3'):
                ts_code = f"{symbol}.SZ"
            elif symbol.startswith('8') or symbol.startswith('4'):
                ts_code = f"{symbol}.BJ"
            else:
                return []
            
            df = pro.concept_detail(ts_code=ts_code, fields='id,concept_name')
            
            if df is not None and not df.empty:
                concepts = df['concept_name'].tolist()
                return concepts
            
            return []
            
        except Exception as e:
            error_msg = str(e)
            if '频率' in error_msg or 'frequency' in error_msg.lower():
                print(f"\n⚠️  Tushare频率限制，请运行 python scripts/fetch_daily_data.py 拉取缓存")
            return []
    
    def get_stock_individual_info(self, symbol: str) -> Dict:
        """
        获取股票个股信息
        
        Args:
            symbol: 股票代码（如"000001"）
            
        Returns:
            Dict: 股票信息
        """
        try:
            df = ak.stock_individual_info_em(symbol=symbol)
            if df is not None and not df.empty:
                # 转换为字典格式
                info_dict = dict(zip(df['item'], df['value']))
                return info_dict
            return {}
        except Exception as e:
            print(f"⚠️  获取 {symbol} 个股信息失败：{e}")
            return {}
    
    def get_realtime_quotes(self, symbols: List[str]) -> pd.DataFrame:
        """
        获取实时行情
        
        Args:
            symbols: 股票代码列表
            
        Returns:
            DataFrame: 实时行情
        """
        try:
            # akshare 实时行情接口
            df = ak.stock_zh_a_spot_em()
            if df is not None and not df.empty:
                # 筛选指定股票
                df = df[df['代码'].isin(symbols)]
                return df
            return pd.DataFrame()
        except Exception as e:
            print(f"❌ 获取实时行情失败：{e}")
            return pd.DataFrame()


if __name__ == "__main__":
    # 测试代码
    fetcher = DataFetcher()
    
    print("\n=== 测试1: 获取涨停股票 ===")
    limit_up = fetcher.get_limit_up_stocks()
    if not limit_up.empty:
        print(limit_up.head())
    
    print("\n=== 测试2: 获取连板股票 ===")
    continuous = fetcher.get_continuous_limit_up()
    if not continuous.empty:
        print(continuous.head())
    
    print("\n=== 测试3: 获取龙虎榜 ===")
    lhb = fetcher.get_dragon_tiger_list()
    if not lhb.empty:
        print(lhb.head())
    
    print("\n=== 测试4: 获取昨日跌停家数 ===")
    limit_down = fetcher.get_limit_down_count()
    print(f"昨日跌停家数：{limit_down}")
