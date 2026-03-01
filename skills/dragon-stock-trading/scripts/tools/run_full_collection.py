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

# 添加脚本目录到路径（上级目录，因为依赖模块在 scripts/ 下）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ==================== 直接导入模块级别实例 ====================
from import_stock_pool import stock_pool_importer
from collect_market_data import market_collector
from collect_intraday_data import intraday_collector
from collect_auction_data import auction_collector


def print_header(title: str):
    """打印标题"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def step_import_stock_pool():
    """Step 1: 导入股票池"""
    print_header("Step 1: 导入股票池到后端数据库")
    
    success = stock_pool_importer.run()
    
    if not success:
        raise Exception("股票池导入失败")
    
    print("\n✅ Step 1 完成：股票池导入成功\n")


def step_collect_market_data(days: int = 60, force: bool = False, start_date: str = None, end_date: str = None):
    """Step 2: 采集市场数据"""
    print_header(f"Step 2: 采集市场数据{'（强制模式）' if force else ''}")
    
    # 计算日期范围
    if not start_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    print(f"📅 采集范围：{start_date} ~ {end_date}")
    
    market_collector.collect_range(start_date=start_date, end_date=end_date, force=force)
    
    print(f"\n✅ Step 2 完成：市场数据采集完成\n")


def step_collect_intraday_data(days: int = 60, force: bool = False, start_date: str = None, end_date: str = None):
    """Step 3: 采集分时数据"""
    print_header(f"Step 3: 采集分时数据{'（强制模式）' if force else ''}")
    
    # 计算日期范围
    if not start_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    print(f"📅 采集范围：{start_date} ~ {end_date}")
    
    intraday_collector.collect_range(start_date=start_date, end_date=end_date, force=force)
    
    print(f"\n✅ Step 3 完成：分时数据采集完成\n")


def step_collect_auction_data(days: int = 60, force: bool = False, start_date: str = None, end_date: str = None):
    """Step 4: 采集竞价数据"""
    print_header(f"Step 4: 采集竞价数据{'（强制模式）' if force else ''}")
    
    # 计算日期范围
    if not start_date:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    print(f"📅 采集范围：{start_date} ~ {end_date}")
    
    auction_collector.collect_range(start_date=start_date, end_date=end_date, force=force)
    
    print(f"\n✅ Step 4 完成：竞价数据采集完成\n")


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description='一键数据导入和采集脚本')
    parser.add_argument('--step', type=str, default='all',
                       choices=['all', 'import', 'market', 'intraday', 'auction'],
                       help='执行步骤（默认：all 全部执行）')
    parser.add_argument('--days', type=int, default=60,
                       help='采集天数（默认 60 天，约 2 个月）')
    parser.add_argument('--start-date', type=str, default=None,
                       help='开始日期（YYYY-MM-DD），覆盖--days 参数')
    parser.add_argument('--end-date', type=str, default=None,
                       help='结束日期（YYYY-MM-DD），默认为今天')
    parser.add_argument('--force', action='store_true',
                       help='强制重新采集（即使数据已存在）')
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("  龙头战法 - 数据导入和采集系统")
    print("=" * 70)
    print(f"\n📅 执行时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔧 执行模式：{args.step}")
    print(f"📊 采集天数：{args.days} 天")
    if args.force:
        print(f"🔄 强制模式：是（重新采集已存在的数据）")
    
    if args.start_date:
        print(f"📅 开始日期：{args.start_date}")
    if args.end_date:
        print(f"📅 结束日期：{args.end_date}")
    
    print("\n" + "=" * 70 + "\n")
    
    try:
        if args.step == 'all':
            # 全部执行
            step_import_stock_pool()
            step_collect_market_data(
                days=args.days, 
                force=args.force,
                start_date=args.start_date,
                end_date=args.end_date
            )
            step_collect_intraday_data(
                days=args.days, 
                force=args.force,
                start_date=args.start_date,
                end_date=args.end_date
            )
            step_collect_auction_data(
                days=args.days,
                force=args.force,
                start_date=args.start_date,
                end_date=args.end_date
            )
            
        elif args.step == 'import':
            # 只导入股票池
            step_import_stock_pool()
            
        elif args.step == 'market':
            # 只采集市场数据
            step_collect_market_data(
                days=args.days,
                force=args.force,
                start_date=args.start_date,
                end_date=args.end_date
            )
            
        elif args.step == 'intraday':
            # 只采集分时数据
            step_collect_intraday_data(
                days=args.days,
                force=args.force,
                start_date=args.start_date,
                end_date=args.end_date
            )
            
        elif args.step == 'auction':
            # 只采集竞价数据
            step_collect_auction_data(
                days=args.days,
                force=args.force,
                start_date=args.start_date,
                end_date=args.end_date
            )
        
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
