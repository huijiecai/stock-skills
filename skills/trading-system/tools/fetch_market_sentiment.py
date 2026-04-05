#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场情绪数据采集工具

采集每日市场情绪指标，用于盘前分析和情绪周期判断。
数据源：Tushare limit_list_d + 东方财富全市场统计

依赖：tushare（pip install tushare）

使用方法：
    # 采集指定日期的市场情绪数据
    python fetch_market_sentiment.py --date 2026-04-03
    
    # 采集最近N天的情绪数据
    python fetch_market_sentiment.py --days 5
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    import tushare as ts
except ImportError:
    print("❌ 需要安装 tushare: pip install tushare")
    sys.exit(1)


# ─── 配置 ─────────────────────────────────────────────────────────────

TUSHARE_TOKEN = '78c2b09c8175affca2a45a788be6b0ba13369519220f7cd1b9c5b991'
TUSHARE_DOMAIN = 'http://tushare.xyz'

# 数据保存根目录
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "market_sentiment"


def get_pro():
    """获取 Tushare pro API 实例"""
    import tushare.pro.client as _client
    _client.DataApi._DataApi__http_url = TUSHARE_DOMAIN
    return ts.pro_api(TUSHARE_TOKEN)


def fetch_limit_list(date: str, limit_type: str = 'U') -> list:
    """
    采集涨停/跌停数据
    limit_type: 'U'=涨停, 'D'=跌停
    Returns: [{code, name, close, pct_chg, first_time, open_times, ...}, ...]
    """
    pro = get_pro()
    date_compact = date.replace('-', '')
    
    try:
        df = pro.limit_list_d(trade_date=date_compact, limit_type=limit_type)
        
        if df is None or df.empty:
            return []
        
        result = []
        for _, row in df.iterrows():
            ft = str(row.get('first_time', '') or '')
            if len(ft) == 6:
                ft = f'{ft[:2]}:{ft[2:4]}:{ft[4:6]}'
            
            result.append({
                'code': row.get('ts_code', '').split('.')[0],  # 去掉后缀
                'name': row.get('name', ''),
                'close': float(row.get('close') or 0),
                'pct_chg': float(row.get('pct_chg') or 0),
                'amount': float(row.get('amount') or 0),
                'first_time': ft,
                'last_time': str(row.get('last_time') or ''),
                'open_times': int(row.get('open_times') or 0),
                'industry': row.get('industry', ''),
                'fd_amount': float(row.get('fd_amount') or 0),
            })
        return result
    except Exception as e:
        print(f"  ❌ 获取{('涨停' if limit_type == 'U' else '跌停')}数据失败: {e}")
        return []


def calculate_sentiment(date: str, up_list: list, down_list: list) -> dict:
    """
    计算市场情绪指标
    
    Returns: {
        date: 日期,
        limit_up_count: 涨停数,
        limit_down_count: 跌停数,
        first_limit_up: 首板涨停数,
        continuous_limit_up: 连板涨停数,
        highest_board: 连板高度,
        broken_board_count: 炸板数(估算),
        seal_rate: 封板率(估算),
        limit_up_by_board: {5: [...], 4: [...], 3: [...], 2: [...], 1: [...]},
        up_stocks: [...],  # 涨停股列表
        down_stocks: [...]  # 跌停股列表
    }
    """
    
    # 按连板数分组
    board_groups = {5: [], 4: [], 3: [], 2: [], 1: []}
    
    for stock in up_list:
        open_times = stock['open_times']
        board = min(open_times, 5)  # 5板以上归为5板
        if board >= 1:
            board_groups[board].append(stock)
    
    # 统计
    first_limit_up = len(board_groups[1])
    continuous_limit_up = sum(len(v) for k, v in board_groups.items() if k >= 2)
    highest_board = max([k for k, v in board_groups.items() if v], default=0)
    
    # 估算炸板数和封板率
    # 注意：Tushare的limit_list_d只包含最终涨停/跌停的股票
    # 炸板数需要通过"曾涨停但未封住"的数据计算，这里用经验公式估算
    # 实际炸板数 ≈ 涨停数 × (1 - 封板率) / 封板率
    # 这里我们只记录准确的涨停数据，炸板数标注为"需手动补充"
    
    sentiment = {
        'date': date,
        'limit_up_count': len(up_list),
        'limit_down_count': len(down_list),
        'first_limit_up': first_limit_up,
        'continuous_limit_up': continuous_limit_up,
        'highest_board': highest_board,
        'broken_board_count': -1,  # -1表示需要手动补充
        'seal_rate': -1,  # -1表示需要手动补充
        'limit_up_by_board': {
            str(k): [f"{s['name']}({s['code']})" for s in v]
            for k, v in board_groups.items()
        },
        'up_stocks': up_list,
        'down_stocks': down_list,
    }
    
    return sentiment


def save_sentiment(date: str, sentiment: dict):
    """保存情绪数据到JSON"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    # 保存单日数据
    filepath = DATA_DIR / f"{date}.json"
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(sentiment, f, ensure_ascii=False, indent=2)
    
    # 更新汇总文件
    summary_file = DATA_DIR / "summary.json"
    if summary_file.exists():
        with open(summary_file, 'r', encoding='utf-8') as f:
            summary = json.load(f)
    else:
        summary = {}
    
    # 只保存关键指标，不保存完整股票列表
    summary[date] = {
        'limit_up_count': sentiment['limit_up_count'],
        'limit_down_count': sentiment['limit_down_count'],
        'first_limit_up': sentiment['first_limit_up'],
        'continuous_limit_up': sentiment['continuous_limit_up'],
        'highest_board': sentiment['highest_board'],
        'broken_board_count': sentiment['broken_board_count'],
        'seal_rate': sentiment['seal_rate'],
    }
    
    # 按日期排序
    summary = dict(sorted(summary.items()))
    
    with open(summary_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    
    return filepath


def fetch_sentiment(date: str) -> dict:
    """采集单日市场情绪数据"""
    print(f"\n📊 采集 {date} 市场情绪数据")
    
    # 1. 获取涨停数据
    print("  🔴 获取涨停数据...")
    up_list = fetch_limit_list(date, 'U')
    print(f"  ✅ 涨停 {len(up_list)} 只")
    
    # 2. 获取跌停数据
    print("  🟢 获取跌停数据...")
    down_list = fetch_limit_list(date, 'D')
    print(f"  ✅ 跌停 {len(down_list)} 只")
    
    # 3. 计算情绪指标
    print("  📈 计算情绪指标...")
    sentiment = calculate_sentiment(date, up_list, down_list)
    
    # 4. 保存
    filepath = save_sentiment(date, sentiment)
    print(f"  ✅ 已保存 → {filepath}")
    
    # 5. 打印摘要
    print(f"\n{'='*60}")
    print(f"📊 {date} 市场情绪摘要")
    print(f"{'='*60}")
    print(f"涨停数: {sentiment['limit_up_count']} 只")
    print(f"跌停数: {sentiment['limit_down_count']} 只")
    print(f"首板涨停: {sentiment['first_limit_up']} 只")
    print(f"连板涨停: {sentiment['continuous_limit_up']} 只")
    print(f"最高连板: {sentiment['highest_board']} 板")
    
    if sentiment['highest_board'] > 0:
        print(f"\n连板分布:")
        for board in range(sentiment['highest_board'], 0, -1):
            stocks = sentiment['limit_up_by_board'].get(str(board), [])
            if stocks:
                print(f"  {board}板: {', '.join(stocks[:5])}{'...' if len(stocks) > 5 else ''}")
    
    print(f"{'='*60}")
    
    return sentiment


def main():
    parser = argparse.ArgumentParser(description='市场情绪数据采集工具')
    parser.add_argument('--date', type=str, help='指定日期（YYYY-MM-DD）')
    parser.add_argument('--days', type=int, help='最近N天')
    
    args = parser.parse_args()
    
    if args.date:
        fetch_sentiment(args.date)
    elif args.days:
        end = datetime.now()
        for i in range(args.days):
            date = (end - timedelta(days=i)).strftime('%Y-%m-%d')
            fetch_sentiment(date)
            time.sleep(0.5)
    else:
        # 默认采集今天
        today = datetime.now().strftime('%Y-%m-%d')
        fetch_sentiment(today)


if __name__ == "__main__":
    main()
