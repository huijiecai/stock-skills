#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
一键数据导入和采集脚本

功能：
1. 从概念股票池体系文档导入所有股票到后端
2. 采集最近 2 个月的市场数据
3. 采集最近 2 个月的分时数据

使用方法：
    python run_full_collection.py
    
分步执行：
    # 只导入股票池
    python run_full_collection.py --step import
    
    # 只采集市场数据
    python run_full_collection.py --step market --days 60
    
    # 只采集分时数据
    python run_full_collection.py --step intraday --days 60
    
    # 全部执行（默认）
    python run_full_collection.py
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).parent))


def print_header(title: str):
    """打印标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def step_import_stock_pool():
    """Step 1: 导入股票池"""
    print_header("Step 1: 导入股票池到后端数据库")
    
    from import_stock_pool import StockPoolImporter
    
    importer = StockPoolImporter()
    success = importer.run()
    
    if not success:
        raise Exception("股票池导入失败")
    
    print("\n✅ Step 1 完成：股票池导入成功\n")


def step_collect_market_data(days: int = 60):
    """Step 2: 采集市场数据"""
    print_header(f"Step 2: 采集最近 {days} 天的市场数据")
    
    from collect_market_data_optimized import MarketDataCollectorOptimized
    
    # 计算日期范围
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    collector = MarketDataCollectorOptimized()
    collector.collect_range(start_date=start_date, end_date=end_date, force=False)
    
    print(f"\n✅ Step 2 完成：已采集 {days} 天的市场数据\n")


def step_collect_intraday_data(days: int = 60):
    """Step 3: 采集分时数据"""
    print_header(f"Step 3: 采集最近 {days} 天的分时数据")
    
    from collect_intraday_data_optimized import IntradayDataCollectorOptimized
    
    # 计算日期范围
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    collector = IntradayDataCollectorOptimized()
    collector.collect_range(start_date=start_date, end_date=end_date, force=False)
    
    print(f"\n✅ Step 3 完成：已采集 {days} 天的分时数据\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='一键数据导入和采集脚本')
    parser.add_argument('--step', type=str, default='all',
                       choices=['all', 'import', 'market', 'intraday'],
                       help='执行步骤（默认：all 全部执行）')
    parser.add_argument('--days', type=int, default=60,
                       help='采集天数（默认 60 天，约 2 个月）')
    parser.add_argument('--start-date', type=str, default=None,
                       help='开始日期（YYYY-MM-DD），覆盖--days 参数')
    parser.add_argument('--end-date', type=str, default=None,
                       help='结束日期（YYYY-MM-DD），默认为今天')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("  龙头战法 - 数据导入和采集系统")
    print("=" * 70)
    print(f"\n📅 执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔧 执行模式：{args.step}")
    print(f"📊 采集天数：{args.days} 天")
    
    if args.start_date:
        print(f"📅 开始日期：{args.start_date}")
    if args.end_date:
        print(f"📅 结束日期：{args.end_date}")
    
    print("\n" + "=" * 70 + "\n")
    
    try:
        if args.step == 'all':
            # 全部执行
            step_import_stock_pool()
            step_collect_market_data(days=args.days)
            step_collect_intraday_data(days=args.days)
            
        elif args.step == 'import':
            # 只导入股票池
            step_import_stock_pool()
            
        elif args.step == 'market':
            # 只采集市场数据
            days = args.days
            if args.start_date and args.end_date:
                from collect_market_data_optimized import MarketDataCollectorOptimized
                collector = MarketDataCollectorOptimized()
                collector.collect_range(
                    start_date=args.start_date,
                    end_date=args.end_date,
                    force=False
                )
            else:
                step_collect_market_data(days=days)
            
        elif args.step == 'intraday':
            # 只采集分时数据
            days = args.days
            if args.start_date and args.end_date:
                from collect_intraday_data_optimized import IntradayDataCollectorOptimized
                collector = IntradayDataCollectorOptimized()
                collector.collect_range(
                    start_date=args.start_date,
                    end_date=args.end_date,
                    force=False
                )
            else:
                step_collect_intraday_data(days=days)
        
        print("\n" + "=" * 70)
        print("  🎉 全部任务完成！")
        print("=" * 70 + "\n")
        
        return 0
        
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断执行")
        return 1
        
    except Exception as e:
        print(f"\n❌ 执行失败：{e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
