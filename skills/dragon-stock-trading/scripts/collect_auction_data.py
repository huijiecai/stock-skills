#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
竞价数据批量采集器

功能：
1. 批量采集指定日期范围的竞价数据（仅股票池中的股票）
2. 支持跳过已存在的数据

使用方法：
    # 采集最近60天的竞价数据
    python collect_auction_data.py --days 60
    
    # 采集指定日期范围
    python collect_auction_data.py --start 2026-01-01 --end 2026-02-28
    
    # 强制重新采集
    python collect_auction_data.py --days 30 --force
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tushare_client import tushare_client
from backend_client import backend_client
from market_data_client import get_auction_data


class AuctionDataCollector:
    """竞价数据采集器"""
    
    def __init__(self):
        pass
    
    def get_trading_dates(self, start_date: str, end_date: str) -> list:
        """获取交易日列表"""
        import time
        for attempt in range(5):
            dates = tushare_client.get_trade_calendar(start_date, end_date)
            if dates:
                print(f"获取到 {len(dates)} 个交易日")
                return dates
            if attempt < 4:
                print(f"交易日历 API 调用失败，重试 {attempt + 2}/5...")
                time.sleep(2)
        raise RuntimeError(f"交易日历 API 调用失败")
    
    def collect_range(self, start_date: str, end_date: str, force: bool = False):
        """
        批量采集竞价数据（仅股票池中的股票）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            force: 是否强制重新采集
        """
        # 获取股票池列表
        all_stocks = backend_client.get_all_stocks()
        stock_codes = [s['code'] for s in all_stocks]
        
        print("=" * 60)
        print("竞价数据批量采集器")
        print("=" * 60)
        print(f"\n📅 采集范围：{start_date} ~ {end_date}")
        print(f"📊 股票池：{len(stock_codes)} 只")
        print(f"🔄 强制模式：{'是' if force else '否'}")
        print("=" * 60 + "\n")
        
        # 获取交易日列表
        trading_dates = self.get_trading_dates(start_date, end_date)
        
        success_count = 0
        skip_count = 0
        
        for date in trading_dates:
            # 检查是否已存在
            if not force and backend_client.check_auction_exists(date):
                print(f"  {date}: ⏭️ 已存在")
                skip_count += 1
                continue
            
            try:
                # 获取竞价数据（仅股票池中的股票）
                auction_data = get_auction_data(date, stock_codes)
                
                if not auction_data:
                    print(f"  {date}: ⚠️ 无数据")
                    continue
                
                # 保存到后端
                result = backend_client.save_auction_data(date, auction_data)
                
                if result.get('success'):
                    print(f"  {date}: ✅ {len(auction_data)} 只股票")
                    success_count += 1
                else:
                    print(f"  {date}: ❌ 保存失败")
                
                # 避免API疲劳
                import time
                time.sleep(0.3)
                
            except Exception as e:
                print(f"  {date}: ❌ 错误: {e}")
        
        print(f"\n{'=' * 60}")
        print(f"✅ 采集完成！成功：{success_count} 天，跳过：{skip_count} 天")
        print("=" * 60 + "\n")


# 模块级单例
auction_collector = AuctionDataCollector()


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='竞价数据批量采集器')
    parser.add_argument('--days', type=int, default=60,
                       help='采集最近 N 天的数据（默认 60 天）')
    parser.add_argument('--start', type=str, default=None,
                       help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, default=None,
                       help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--force', action='store_true',
                       help='强制重新采集')
    
    args = parser.parse_args()
    
    # 计算日期范围
    if args.start:
        start_date = args.start
        end_date = args.end if args.end else datetime.now().strftime('%Y-%m-%d')
    else:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
    
    # 执行采集
    try:
        auction_collector.collect_range(start_date, end_date, args.force)
        print("\n🎉 采集任务成功完成！")
        sys.exit(0)
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断采集")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 采集失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
