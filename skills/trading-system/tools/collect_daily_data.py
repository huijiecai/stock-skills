#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
盘后数据采集一键脚本

每日盘后执行一次,采集:
1. 市场情绪指标(涨停/跌停/连板)
2. 概念板块涨幅排行
3. 盯盘股数据(分时+日线+资金流向)
4. 指数数据(分时+日线)

使用方法:
    # 采集今天的数据
    python collect_daily_data.py
    
    # 采集指定日期
    python collect_daily_data.py --date 2026-04-03
    
    # 只采集市场情绪
    python collect_daily_data.py --sentiment-only
    
    # 只采集概念排行
    python collect_daily_data.py --concept-rank-only
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

# 导入现有脚本的函数
sys.path.insert(0, str(Path(__file__).parent))


def collect_market_sentiment(date: str):
    """采集市场情绪指标"""
    print(f"\n{'='*60}")
    print(f"📊 第一部分: 市场情绪指标")
    print(f"{'='*60}")
    
    try:
        from fetch_market_sentiment import fetch_sentiment
        sentiment = fetch_sentiment(date)
        return sentiment
    except Exception as e:
        print(f"❌ 市场情绪采集失败: {e}")
        return None


def collect_concept_rank(top_n: int = 50):
    """采集概念板块排行"""
    print(f"\n{'='*60}")
    print(f"📊 第二部分: 概念板块涨幅排行Top{top_n}")
    print(f"{'='*60}")
    
    try:
        from fetch_concept_rank import fetch_concept_rank, save_concept_rank, print_rank_table
        
        # 涨幅榜
        print("\n🔴 涨幅榜:")
        up_concepts = fetch_concept_rank(top_n, 'asc')
        if up_concepts:
            print_rank_table(up_concepts[:10])  # 只打印Top10
            save_concept_rank(up_concepts, 'asc')
        
        time.sleep(1)
        
        # 跌幅榜
        print("\n🟢 跌幅榜:")
        down_concepts = fetch_concept_rank(top_n, 'desc')
        if down_concepts:
            print_rank_table(down_concepts[:10])  # 只打印Bottom10
            save_concept_rank(down_concepts, 'desc')
        
        return up_concepts, down_concepts
    except Exception as e:
        print(f"❌ 概念板块排行采集失败: {e}")
        return None, None


def collect_watchlist_data(watchlist: list, indices: list):
    """采集盯盘股和指数数据"""
    print(f"\n{'='*60}")
    print(f"📊 第三部分: 盯盘股和指数数据")
    print(f"{'='*60}")
    
    try:
        from fetch_adata_data import fetch_watchlist, fetch_indices
        
        # 盯盘股
        if watchlist:
            fetch_watchlist(watchlist)
        
        # 指数
        if indices:
            fetch_indices(indices)
    except Exception as e:
        print(f"❌ 盯盘股数据采集失败: {e}")


def main():
    parser = argparse.ArgumentParser(description='盘后数据采集一键脚本')
    parser.add_argument('--date', type=str, help='指定日期（YYYY-MM-DD），默认今天')
    parser.add_argument('--watchlist', type=str, nargs='+', 
                        default=['002192', '000722', '600726'],
                        help='盯盘股列表')
    parser.add_argument('--indices', type=str, nargs='+',
                        default=['000001', '399001', '399006'],
                        help='指数列表')
    parser.add_argument('--concept-top', type=int, default=50, help='概念板块排行TopN')
    parser.add_argument('--sentiment-only', action='store_true', help='只采集市场情绪')
    parser.add_argument('--concept-rank-only', action='store_true', help='只采集概念排行')
    
    args = parser.parse_args()
    
    # 日期
    date = args.date or datetime.now().strftime('%Y-%m-%d')
    
    print(f"\n{'='*60}")
    print(f"🚀 盘后数据采集")
    print(f"日期: {date}")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    
    # 1. 市场情绪
    if not args.concept_rank_only:
        sentiment = collect_market_sentiment(date)
    
    # 2. 概念板块排行
    if not args.sentiment_only:
        up_concepts, down_concepts = collect_concept_rank(args.concept_top)
    
    # 3. 盯盘股数据
    if not args.sentiment_only and not args.concept_rank_only:
        collect_watchlist_data(args.watchlist, args.indices)
    
    print(f"\n{'='*60}")
    print(f"🎉 采集完成!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
