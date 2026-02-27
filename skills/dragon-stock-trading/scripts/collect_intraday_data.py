#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分时数据采集器 - 采集股票池中股票的分时行情

使用场景：
1. 每日收盘后采集当天所有股票池股票的分时数据
2. 用于龙头战法分析：涨停时机、封板强度、资金流向

注意事项：
- 需要 Tushare 5000 积分权限
- 调用频次：200次/分钟，需要限流
- 150只股票预计耗时 45秒
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import time

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from market_data_client import MarketDataClient
from backend_client import backend_client  # 使用全局实例


class IntradayDataCollector:
    """分时数据采集器"""
    
    def __init__(self):
        self.market_client = MarketDataClient()
        self.backend_client = backend_client  # 使用全局后端客户端实例
        self.request_count = 0
        self.start_time = time.time()
    
    def _rate_limit(self):
        """
        限流：200次/分钟
        每次请求后检查，如果超过限制则等待
        """
        self.request_count += 1
        elapsed = time.time() - self.start_time
        
        # 每分钟最多200次
        if self.request_count >= 200 and elapsed < 60:
            sleep_time = 60 - elapsed
            print(f"  ⏱️  达到限流上限，等待 {sleep_time:.1f} 秒...")
            time.sleep(sleep_time)
            self.request_count = 0
            self.start_time = time.time()
    
    def collect(self, date: str, force: bool = False):
        """
        采集指定日期的分时数据（支持增量采集）
        
        Args:
            date: 交易日期（YYYY-MM-DD）
            force: 是否强制重新采集（即使已存在）
        """
        print(f"\n{'='*60}")
        print(f"📅 开始采集分时数据: {date}")
        if force:
            print(f"🔄 强制重新采集模式")
        print(f"{'='*60}\n")
        
        # 获取股票池
        stocks = self.backend_client.get_all_stocks()
        print(f"📊 股票池总数: {len(stocks)} 只\n")
        
        success_count = 0
        failed_count = 0
        skipped_count = 0
        total_records = 0
        
        for i, stock in enumerate(stocks, 1):
            code = stock['code']
            name = stock.get('name', '')
            market = stock['market']
            
            # 跳过 ST 股票
            if 'ST' in name.upper():
                print(f"  [{i}/{len(stocks)}] ⚠️  跳过ST股票: {code} {name}")
                skipped_count += 1
                continue
            
            # 检查是否已存在数据（除非强制采集）
            if not force:
                exists = self.backend_client.get_stock_intraday_existence(code, date)
                if exists:
                    print(f"  [{i}/{len(stocks)}] ⏭️  跳过已存在: {code} {name}")
                    skipped_count += 1
                    continue
            
            try:
                # 限流
                self._rate_limit()
                
                # 获取分时数据
                intraday_data = self.market_client.get_stock_intraday(
                    code, market, date
                )
                
                if not intraday_data:
                    print(f"  [{i}/{len(stocks)}] ⚠️  {code} {name} - 无分时数据")
                    failed_count += 1
                    continue
                
                # 通过后端 API 保存
                result = self.backend_client.save_intraday_data(
                    date, code, intraday_data
                )
                
                records = len(intraday_data)
                total_records += records
                success_count += 1
                
                print(f"  [{i}/{len(stocks)}] ✅ {code} {name} - {records} 条数据")
                
            except Exception as e:
                print(f"  [{i}/{len(stocks)}] ❌ {code} {name} - 失败: {e}")
                failed_count += 1
        
        print(f"\n{'='*60}")
        print(f"✅ 采集完成")
        print(f"{'='*60}")
        print(f"  成功: {success_count} 只")
        print(f"  失败: {failed_count} 只")
        print(f"  跳过: {skipped_count} 只")
        print(f"  总记录数: {total_records} 条")
        print(f"{'='*60}\n")


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='分时数据采集器')
    parser.add_argument('date', nargs='?', default=datetime.now().strftime('%Y-%m-%d'),
                       help='交易日期 (YYYY-MM-DD)，默认为今天')
    parser.add_argument('-f', '--force', action='store_true',
                       help='强制重新采集（即使数据已存在）')
    
    args = parser.parse_args()
    
    collector = IntradayDataCollector()
    collector.collect(args.date, force=args.force)


if __name__ == "__main__":
    main()
