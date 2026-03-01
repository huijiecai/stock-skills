#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tushare 客户端测试脚本

使用方法：
    # 测试所有方法
    python test_tushare_client.py

    # 测试指定方法
    python test_tushare_client.py --method get_stock_daily --code 000001.SZ
    python test_tushare_client.py --method get_daily_all --date 20260226
    python test_tushare_client.py --method get_trade_calendar --start 20260101 --end 20260228
    python test_tushare_client.py --method get_limit_list --date 20260226
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

# 添加 scripts 目录到路径
script_dir = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(script_dir))

from tushare_client import tushare_client


def test_get_stock_daily(code: str = "000001.SZ", date: str = None):
    """测试获取股票日线数据"""
    print(f"\n📊 测试 get_stock_daily: {code}")
    print("-" * 40)
    
    data = tushare_client.get_stock_daily(code, date)
    
    if data and data.get('items'):
        print(f"✅ 获取到 {len(data['items'])} 条数据")
        for item in data['items'][:3]:  # 显示前3条
            print(f"   {item[1]}: 收盘 {item[5]}, 涨幅 {item[8]:.2f}%")
    else:
        print("❌ 未获取到数据")


def test_get_daily_all(date: str = None):
    """测试批量获取所有股票日线数据"""
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    
    print(f"\n📊 测试 get_daily_all: {date}")
    print("-" * 40)
    
    import time
    start = time.time()
    data = tushare_client.get_daily_all(date)
    elapsed = time.time() - start
    
    if data and data.get('items'):
        print(f"✅ 获取到 {len(data['items'])} 只股票, 耗时 {elapsed:.2f}秒")
    else:
        print("❌ 未获取到数据")


def test_get_index_daily(code: str = "000001.SH"):
    """测试获取指数数据"""
    print(f"\n📊 测试 get_index_daily: {code}")
    print("-" * 40)
    
    data = tushare_client.get_index_daily(code)
    
    if data and data.get('items'):
        item = data['items'][0]
        print(f"✅ {item[1]}: {item[5]:.2f} ({item[8]:+.2f}%)")
    else:
        print("❌ 未获取到数据")


def test_get_trade_calendar(start: str, end: str):
    """测试获取交易日历"""
    print(f"\n📊 测试 get_trade_calendar: {start} ~ {end}")
    print("-" * 40)
    
    dates = tushare_client.get_trade_calendar(start, end)
    
    if dates:
        print(f"✅ 获取到 {len(dates)} 个交易日")
        print(f"   首个: {dates[-1]}")
        print(f"   末个: {dates[0]}")
    else:
        print("❌ 未获取到数据")


def test_get_stock_basic(code: str = "000001.SZ"):
    """测试获取股票基本信息"""
    print(f"\n📊 测试 get_stock_basic: {code}")
    print("-" * 40)
    
    data = tushare_client.get_stock_basic(code)
    
    if data and data.get('items'):
        item = data['items'][0]
        print(f"✅ {item[1]} ({item[0]})")
        print(f"   行业: {item[3]}, 市场: {item[4]}")
    else:
        print("❌ 未获取到数据")


def test_get_limit_list(date: str = None):
    """测试获取涨跌停列表"""
    if not date:
        date = datetime.now().strftime('%Y%m%d')
    
    print(f"\n📊 测试 get_limit_list: {date}")
    print("-" * 40)
    
    data = tushare_client.get_limit_list(date)
    
    if data and data.get('items'):
        items = data['items']
        stats = {}
        for item in items:
            lt = item[3] if len(item) > 3 else '?'
            stats[lt] = stats.get(lt, 0) + 1
        
        print(f"✅ 获取到 {len(items)} 条记录")
        print(f"   涨停(U): {stats.get('U', 0)}, 跌停(D): {stats.get('D', 0)}, 炸板(Z): {stats.get('Z', 0)}")
    else:
        print("❌ 未获取到数据")


def test_all():
    """运行所有测试"""
    print("=" * 50)
    print("Tushare 客户端测试")
    print("=" * 50)
    
    test_get_stock_daily()
    test_get_daily_all("20260226")
    test_get_index_daily()
    test_get_trade_calendar("20260101", "20260228")
    test_get_stock_basic()
    test_get_limit_list("20260226")
    
    print("\n" + "=" * 50)
    print(f"✅ 测试完成，总请求数: {tushare_client._request_count}")
    print("=" * 50)


def main():
    parser = argparse.ArgumentParser(description='Tushare 客户端测试')
    parser.add_argument('--method', type=str, default=None,
                       choices=['get_stock_daily', 'get_daily_all', 'get_index_daily',
                               'get_trade_calendar', 'get_stock_basic', 'get_limit_list'],
                       help='测试指定方法')
    parser.add_argument('--code', type=str, default='000001.SZ',
                       help='股票代码（如 000001.SZ）')
    parser.add_argument('--date', type=str, default=None,
                       help='交易日期（如 20260226）')
    parser.add_argument('--start', type=str, default='20260101',
                       help='开始日期')
    parser.add_argument('--end', type=str, default='20260228',
                       help='结束日期')
    
    args = parser.parse_args()
    
    if args.method:
        # 测试指定方法
        if args.method == 'get_stock_daily':
            test_get_stock_daily(args.code, args.date)
        elif args.method == 'get_daily_all':
            test_get_daily_all(args.date)
        elif args.method == 'get_index_daily':
            test_get_index_daily(args.code)
        elif args.method == 'get_trade_calendar':
            test_get_trade_calendar(args.start, args.end)
        elif args.method == 'get_stock_basic':
            test_get_stock_basic(args.code)
        elif args.method == 'get_limit_list':
            test_get_limit_list(args.date)
    else:
        # 运行所有测试
        test_all()


if __name__ == "__main__":
    main()

# # 运行所有测试
# python test_tushare_client.py

# # 测试指定方法
# python test_tushare_client.py --method get_stock_daily --code 001309.SZ
# python test_tushare_client.py --method get_daily_all --date 20260226
# python test_tushare_client.py --method get_trade_calendar --start 20260201 --end 20260228
# python test_tushare_client.py --method get_limit_list --date 20260226