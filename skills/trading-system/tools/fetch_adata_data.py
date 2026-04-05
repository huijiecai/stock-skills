#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟看盘数据采集工具（基于 adata，免费无需注册）

用于预期驱动交易系统的模拟看盘功能，每天盘后执行一次。
adata 特点：免费、无需 token、支持当日分时数据

依赖：adata（pip install adata）

使用方法：
    # 获取指定股票的分时数据
    python fetch_adata_data.py --code 002192 --intraday

    # 获取指定股票的日线数据
    python fetch_adata_data.py --code 002192 --daily --days 30

    # 获取指数数据
    python fetch_adata_data.py --index 000001 --intraday
    python fetch_adata_data.py --index 399001 --daily --days 60

    # 获取概念板块数据（日线/分时）
    python fetch_adata_data.py --concept BK0612 --daily
    python fetch_adata_data.py --concept BK0558 --intraday

    # 获取概念板块列表
    python fetch_adata_data.py --concept-list

    # 获取实时行情
    python fetch_adata_data.py --realtime 002192 600519 000001

    # 获取资金流向
    python fetch_adata_data.py --capital 002192

    # 获取股票基础信息
    python fetch_adata_data.py --stock-info 002192

    # 获取股票所属概念
    python fetch_adata_data.py --stock-concepts 002192

    # 获取概念成分股
    python fetch_adata_data.py --concept-constituents BK0612
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import adata
except ImportError:
    print("❌ 需要安装 adata: pip install adata")
    sys.exit(1)


# ─── 配置 ─────────────────────────────────────────────────────────────

# 数据保存根目录
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ─── 数据采集函数 ───────────────────────────────────────────────────────

def fetch_stock_info(code: str) -> dict:
    """
    获取股票基础信息（所属板块：行业+地域+概念）
    返回: {industry: [...], region: str, concepts: [{code, name}, ...]}
    """
    try:
        df = adata.stock.info.get_plate_east(stock_code=code)
        if df is None or df.empty:
            return {}

        result = {
            'stock_code': code,
            'industry': [],
            'region': '',
            'concepts': [],
        }

        for _, row in df.iterrows():
            plate_type = str(row.get('plate_type', ''))
            plate_code = str(row.get('plate_code', ''))
            plate_name = str(row.get('plate_name', ''))

            if plate_type == '行业':
                result['industry'].append({'code': plate_code, 'name': plate_name})
            elif plate_type == '板块':
                result['region'] = plate_name
            elif plate_type == '概念':
                result['concepts'].append({'code': plate_code, 'name': plate_name})

        return result

    except Exception as e:
        print(f"  ❌ 获取股票基础信息失败: {e}")
        return {}


def fetch_stock_shares(code: str) -> dict:
    """
    获取股票股本信息（最新）
    返回: {total_shares, list_a_shares, change_date}
    """
    try:
        df = adata.stock.info.get_stock_shares(stock_code=code)
        if df is None or df.empty:
            return {}

        # 取最新一条
        latest = df.iloc[0]
        return {
            'stock_code': code,
            'total_shares': float(latest.get('total_shares', 0)),
            'list_a_shares': float(latest.get('list_a_shares', 0)),
            'change_date': str(latest.get('change_date', '')),
        }

    except Exception as e:
        print(f"  ❌ 获取股本信息失败: {e}")
        return {}


def fetch_stock_concepts(code: str) -> list:
    """
    获取股票所属概念（含原因）
    返回: [{concept_code, name, reason}, ...]
    """
    try:
        df = adata.stock.info.get_concept_east(stock_code=code)
        if df is None or df.empty:
            return []

        result = []
        for _, row in df.iterrows():
            result.append({
                'concept_code': str(row.get('concept_code', '')),
                'name': str(row.get('name', '')),
                'reason': str(row.get('reason', ''))[:200],  # 截取前200字
                'source': str(row.get('source', '')),
            })
        return result

    except Exception as e:
        print(f"  ❌ 获取股票概念失败: {e}")
        return []


def fetch_concept_constituents(concept_code: str) -> list:
    """
    获取概念板块成分股
    concept_code: 概念代码（如 BK0612）
    返回: [{stock_code, short_name}, ...]
    """
    try:
        df = adata.stock.info.concept_constituent_east(concept_code=concept_code)
        if df is None or df.empty:
            return []

        result = []
        for _, row in df.iterrows():
            result.append({
                'stock_code': str(row.get('stock_code', '')),
                'short_name': str(row.get('short_name', '')),
            })
        return result

    except Exception as e:
        print(f"  ❌ 获取概念成分股失败: {e}")
        return []


def fetch_stock_intraday(code: str) -> dict:
    """
    获取个股当日分时数据
    返回: {date: [{time, price, change_pct, volume, amount}, ...]}
    """
    try:
        df = adata.stock.market.get_market_min(stock_code=code)
        if df is None or df.empty:
            return {}

        # 提取日期
        date_str = str(df['trade_time'].iloc[0])[:10]

        bars = []
        for _, row in df.iterrows():
            trade_time = str(row['trade_time'])
            time_part = trade_time[11:16] if len(trade_time) >= 16 else trade_time[-5:]
            bars.append({
                'time': time_part,
                'price': float(row['price']),
                'change': float(row.get('change', 0)),
                'change_pct': float(row.get('change_pct', 0)),
                'volume': float(row.get('volume', 0)),
                'amount': float(row.get('amount', 0)),
                'avg_price': float(row.get('avg_price', 0)),
            })

        return {date_str: bars}

    except Exception as e:
        print(f"  ❌ 获取分时失败: {e}")
        return {}


def fetch_index_intraday(code: str) -> dict:
    """
    获取指数当日分时数据
    返回: {date: [{time, price, change_pct, volume, amount}, ...]}
    """
    try:
        df = adata.stock.market.get_market_index_min(index_code=code)
        if df is None or df.empty:
            return {}

        date_str = str(df['trade_time'].iloc[0])[:10]

        bars = []
        for _, row in df.iterrows():
            trade_time = str(row['trade_time'])
            time_part = trade_time[11:16] if len(trade_time) >= 16 else trade_time[-5:]
            bars.append({
                'time': time_part,
                'price': float(row['price']),
                'change': float(row.get('change', 0)),
                'change_pct': float(row.get('change_pct', 0)),
                'volume': float(row.get('volume', 0)),
                'amount': float(row.get('amount', 0)),
            })

        return {date_str: bars}

    except Exception as e:
        print(f"  ❌ 获取指数分时失败: {e}")
        return {}


def fetch_stock_daily(code: str, days: int = 30) -> dict:
    """
    获取个股日线数据
    返回: {date: {open, high, low, close, volume, amount, change_pct}, ...}
    """
    try:
        df = adata.stock.market.get_market(
            stock_code=code,
            k_type=1,  # 日K
        )
        if df is None or df.empty:
            return {}

        # 取最近N天
        if len(df) > days:
            df = df.tail(days)

        result = {}
        for _, row in df.iterrows():
            trade_date = str(row['trade_date'])
            result[trade_date] = {
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row['volume']),
                'amount': float(row['amount']),
                'change_pct': float(row.get('change_pct', 0)),
                'change': float(row.get('change', 0)),
                'turnover_ratio': float(row.get('turnover_ratio', 0)),
                'pre_close': float(row.get('pre_close', 0)),
            }

        return result

    except Exception as e:
        print(f"  ❌ 获取日线失败: {e}")
        return {}


def fetch_index_daily(code: str, days: int = 60) -> dict:
    """
    获取指数日线数据
    返回: {date: {open, high, low, close, volume, change_pct}, ...}
    """
    try:
        df = adata.stock.market.get_market_index(
            index_code=code,
            k_type=1,
        )
        if df is None or df.empty:
            return {}

        if len(df) > days:
            df = df.tail(days)

        result = {}
        for _, row in df.iterrows():
            trade_date = str(row['trade_date'])
            result[trade_date] = {
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row['volume']),
                'amount': float(row.get('amount', 0)),
                'change_pct': float(row.get('change_pct', 0)),
                'change': float(row.get('change', 0)),
            }

        return result

    except Exception as e:
        print(f"  ❌ 获取指数日线失败: {e}")
        return {}


def fetch_realtime(code_list: list) -> list:
    """
    获取实时行情
    返回: [{code, name, price, change, change_pct, volume, amount}, ...]
    """
    try:
        df = adata.stock.market.list_market_current(code_list=code_list)
        if df is None or df.empty:
            return []

        result = []
        for _, row in df.iterrows():
            result.append({
                'code': str(row['stock_code']),
                'name': str(row.get('short_name', '')),
                'price': float(row['price']),
                'change': float(row.get('change', 0)),
                'change_pct': float(row.get('change_pct', 0)),
                'volume': float(row.get('volume', 0)),
                'amount': float(row.get('amount', 0)),
            })

        return result

    except Exception as e:
        print(f"❌ 获取实时行情失败: {e}")
        return []


def fetch_capital_flow(code: str) -> list:
    """
    获取个股资金流向（历史日度）
    返回: [{date, main_net_inflow, retail_net_inflow, ...}, ...]
    """
    try:
        df = adata.stock.market.get_capital_flow(stock_code=code)
        if df is None or df.empty:
            return []

        result = []
        for _, row in df.iterrows():
            result.append({
                'date': str(row.get('trade_date', '')),
                'main_net_inflow': float(row.get('main_net_inflow', 0)),
                'retail_net_inflow': float(row.get('retail_net_inflow', 0)),
                'net_inflow': float(row.get('net_inflow', 0)),
            })

        return result

    except Exception as e:
        print(f"❌ 获取资金流向失败: {e}")
        return []


def fetch_concept_list() -> list:
    """
    获取概念板块列表（同花顺）
    返回: [{index_code, name, concept_code, source}, ...]
    """
    try:
        df = adata.stock.info.all_concept_code_ths()
        if df is None or df.empty:
            return []

        result = []
        for _, row in df.iterrows():
            result.append({
                'index_code': str(row.get('index_code', '')),
                'name': str(row.get('name', '')),
                'concept_code': str(row.get('concept_code', '')),
                'source': str(row.get('source', '同花顺')),
            })

        return result

    except Exception as e:
        print(f"❌ 获取概念列表失败: {e}")
        return []


def fetch_concept_daily(index_code: str) -> dict:
    """
    获取概念板块日线数据（东方财富）
    index_code: 概念代码，如 'BK0612'（锂电池）
    返回: {date: {open, high, low, close, volume, change_pct}, ...}
    """
    try:
        df = adata.stock.market.get_market_concept_east(index_code=index_code, k_type=1)
        if df is None or df.empty:
            return {}

        result = {}
        for _, row in df.iterrows():
            trade_date = str(row['trade_date'])
            result[trade_date] = {
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                'volume': float(row.get('volume', 0)),
                'amount': float(row.get('amount', 0)),
                'change': float(row.get('change', 0)),
                'change_pct': float(row.get('change_pct', 0)),
            }

        return result

    except Exception as e:
        print(f"❌ 获取概念日线失败: {e}")
        return {}


def fetch_concept_intraday(index_code: str) -> dict:
    """
    获取概念板块当日分时数据（东方财富）
    index_code: 概念代码，如 'BK0612'（锂电池）
    返回: {date: [{time, price, change_pct, volume, amount}, ...]}
    """
    try:
        df = adata.stock.market.get_market_concept_min_east(index_code=index_code)
        if df is None or df.empty:
            return {}

        date_str = str(df['trade_time'].iloc[0])[:10]

        bars = []
        for _, row in df.iterrows():
            trade_time = str(row['trade_time'])
            time_part = trade_time[11:16] if len(trade_time) >= 16 else trade_time[-5:]
            bars.append({
                'time': time_part,
                'price': float(row['price']),
                'change': float(row.get('change', 0)),
                'change_pct': float(row.get('change_pct', 0)),
                'volume': float(row.get('volume', 0)),
                'amount': float(row.get('amount', 0)),
                'avg_price': float(row.get('avg_price', 0)),
            })

        return {date_str: bars}

    except Exception as e:
        print(f"❌ 获取概念分时失败: {e}")
        return {}


# ─── 保存函数 ───────────────────────────────────────────────────────────

def save_data(code: str, data_type: str, data, category: str = None):
    """保存数据到本地 JSON 文件
    
    Args:
        code: 代码（股票代码/指数代码/概念代码）
        data_type: 数据类型（daily/intraday_1min等）
        data: 数据内容
        category: 数据分类（stocks/indices/concepts），自动推断
    """
    # 自动推断分类
    if category is None:
        if code.startswith(('000', '399', '899')):
            category = 'indices'
        elif code.startswith(('BK', '886')):
            category = 'concepts'
        else:
            category = 'stocks'
    
    save_dir = DATA_DIR / category / code
    save_dir.mkdir(parents=True, exist_ok=True)
    filepath = save_dir / f"{data_type}.json"

    # 如果是字典且文件存在，合并数据
    if isinstance(data, dict) and filepath.exists():
        with open(filepath, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        if isinstance(existing, dict):
            existing.update(data)
            data = existing

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return filepath


# ─── 批量采集 ───────────────────────────────────────────────────────────

def fetch_watchlist(watchlist: list):
    """获取盯盘股今日全量数据（必须传入股票列表）"""
    if not watchlist:
        print("❌ 错误: 必须传入股票列表")
        return

    print(f"{'='*60}")
    print(f"📊 获取盯盘股今日数据")
    print(f"股票列表: {watchlist}")
    print(f"{'='*60}")

    for code in watchlist:
        print(f"\n--- {code} ---")

        # 分时数据
        intraday = fetch_stock_intraday(code)
        if intraday:
            fp = save_data(code, 'intraday_1min', intraday)
            total = sum(len(v) for v in intraday.values())
            date = list(intraday.keys())[0]
            print(f"  ✅ 分时: {total} 条 ({date}) → {fp}")
        else:
            print(f"  ⚠️ 分时: 无数据")

        # 日线数据（最近30天）
        daily = fetch_stock_daily(code, days=30)
        if daily:
            fp = save_data(code, 'daily', daily)
            print(f"  ✅ 日线: {len(daily)} 天 → {fp}")
        else:
            print(f"  ⚠️ 日线: 无数据")

        # 资金流向
        capital = fetch_capital_flow(code)
        if capital:
            fp = save_data(code, 'capital_flow', capital)
            print(f"  ✅ 资金流向: {len(capital)} 天 → {fp}")
        else:
            print(f"  ⚠️ 资金流向: 无数据")


def fetch_indices(indices: list):
    """获取指数数据（必须传入指数列表）"""
    if not indices:
        print("❌ 错误: 必须传入指数列表")
        return

    print(f"\n{'='*60}")
    print(f"📈 获取指数数据")
    print(f"{'='*60}")

    for code in indices:
        print(f"\n--- 指数 {code} ---")

        # 分时数据
        intraday = fetch_index_intraday(code)
        if intraday:
            fp = save_data(code, 'intraday_1min', intraday)
            total = sum(len(v) for v in intraday.values())
            date = list(intraday.keys())[0]
            print(f"  ✅ 分时: {total} 条 ({date}) → {fp}")
        else:
            print(f"  ⚠️ 分时: 无数据")

        # 日线数据
        daily = fetch_index_daily(code, days=60)
        if daily:
            fp = save_data(code, 'daily', daily)
            print(f"  ✅ 日线: {len(daily)} 天 → {fp}")
        else:
            print(f"  ⚠️ 日线: 无数据")


# ─── 主流程 ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='模拟看盘数据采集工具（基于 adata，免费）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 获取指定股票分时
  python fetch_adata_data.py --code 002192 --intraday

  # 获取指定股票日线（最近30天）
  python fetch_adata_data.py --code 002192 --daily

  # 获取指数分时
  python fetch_adata_data.py --index 000001 --intraday

  # 获取实时行情
  python fetch_adata_data.py --realtime 002192 600519

  # 获取批量股票数据
  python fetch_adata_data.py --watch 002192 000722 600726

  # 获取批量指数数据
  python fetch_adata_data.py --indices 000001 399001 399006
        """
    )

    parser.add_argument('--code', type=str, help='股票代码（如 002192）')
    parser.add_argument('--index', type=str, help='指数代码（如 000001）')
    parser.add_argument('--intraday', action='store_true', help='获取分时数据')
    parser.add_argument('--daily', action='store_true', help='获取日线数据')
    parser.add_argument('--days', type=int, default=30, help='日线天数（默认30）')
    parser.add_argument('--realtime', type=str, nargs='+', help='获取实时行情')
    parser.add_argument('--capital', type=str, help='获取资金流向')
    parser.add_argument('--concept', type=str, help='获取概念板块数据（东方财富代码，如 BK0612）')
    parser.add_argument('--concept-list', action='store_true', help='获取概念板块列表')
    parser.add_argument('--concept-constituents', type=str, metavar='CODE', help='获取概念成分股（如 BK0612）')
    parser.add_argument('--stock-info', type=str, metavar='CODE', help='获取股票基础信息（行业+地域+概念）')
    parser.add_argument('--stock-concepts', type=str, metavar='CODE', help='获取股票所属概念（含原因）')
    parser.add_argument('--stock-shares', type=str, metavar='CODE', help='获取股票股本信息')
    parser.add_argument('--watch', type=str, nargs='+', help='批量获取股票数据')
    parser.add_argument('--indices', type=str, nargs='+', help='批量获取指数数据')

    args = parser.parse_args()

    # 股票基础信息
    if args.stock_info:
        code = args.stock_info
        print(f"📊 获取股票基础信息: {code}")
        data = fetch_stock_info(code)
        if data:
            print(f"  行业: {[i['name'] for i in data.get('industry', [])]}")
            print(f"  地域: {data.get('region', '')}")
            print(f"  概念数量: {len(data.get('concepts', []))}")
            fp = save_data(code, 'stock_info', data)
            print(f"✅ 已保存 → {fp}")
        else:
            print("  ⚠️ 无数据")
        return

    # 股票所属概念
    if args.stock_concepts:
        code = args.stock_concepts
        print(f"📊 获取股票所属概念: {code}")
        data = fetch_stock_concepts(code)
        if data:
            print(f"✅ 共 {len(data)} 个概念")
            for d in data[:5]:
                print(f"  {d['concept_code']}: {d['name']}")
            fp = save_data(code, 'stock_concepts', data)
            print(f"✅ 已保存 → {fp}")
        else:
            print("  ⚠️ 无数据")
        return

    # 股票股本信息
    if args.stock_shares:
        code = args.stock_shares
        print(f"📊 获取股票股本信息: {code}")
        data = fetch_stock_shares(code)
        if data:
            print(f"  总股本: {data.get('total_shares', 0):,.0f}")
            print(f"  流通股本: {data.get('list_a_shares', 0):,.0f}")
            fp = save_data(code, 'stock_shares', data)
            print(f"✅ 已保存 → {fp}")
        else:
            print("  ⚠️ 无数据")
        return

    # 概念成分股
    if args.concept_constituents:
        concept_code = args.concept_constituents
        print(f"📊 获取概念成分股: {concept_code}")
        data = fetch_concept_constituents(concept_code)
        if data:
            print(f"✅ 共 {len(data)} 只股票")
            for d in data[:10]:
                print(f"  {d['stock_code']}: {d['short_name']}")
            # 保存到概念目录
            fp = save_data(concept_code, 'constituents', data, category='concepts')
            print(f"✅ 已保存 → {fp}")
        else:
            print("  ⚠️ 无数据")
        return

    # 批量股票数据
    if args.watch:
        fetch_watchlist(args.watch)
        return

    # 批量指数数据
    if args.indices:
        fetch_indices(args.indices)
        return

    # 实时行情
    if args.realtime:
        codes = args.realtime
        print(f"📊 获取实时行情: {codes}")
        data = fetch_realtime(codes)
        if data:
            for d in data:
                print(f"  {d['code']} {d['name']}: {d['price']:.2f} ({d['change_pct']:+.2f}%)")
        else:
            print("  ⚠️ 无数据")
        return

    # 资金流向
    if args.capital:
        code = args.capital
        print(f"📊 获取资金流向: {code}")
        data = fetch_capital_flow(code)
        if data:
            for d in data[-5:]:
                print(f"  {d['date']}: 主力净流入 {d['main_net_inflow']:.0f}")
            fp = save_data(code, 'capital_flow', data)
            print(f"✅ 已保存 → {fp}")
        else:
            print("  ⚠️ 无数据")
        return

    # 概念板块列表
    if args.concept_list:
        print(f"📊 获取概念板块列表")
        data = fetch_concept_list()
        if data:
            print(f"✅ 共 {len(data)} 个概念")
            for d in data[:10]:
                print(f"  {d['index_code']}: {d['name']}")
            # 保存到 concepts 目录
            concept_dir = DATA_DIR / 'concepts'
            concept_dir.mkdir(parents=True, exist_ok=True)
            fp = concept_dir / 'concept_list.json'
            with open(fp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"✅ 已保存 → {fp}")
        else:
            print("  ⚠️ 无数据")
        return

    # 概念板块数据
    if args.concept:
        index_code = args.concept
        print(f"📊 获取概念板块数据: {index_code}")

        if args.intraday:
            data = fetch_concept_intraday(index_code)
            if data:
                fp = save_data(index_code, 'intraday_1min', data, category='concepts')
                total = sum(len(v) for v in data.values())
                date = list(data.keys())[0]
                print(f"✅ 分时: {total} 条 ({date}) → {fp}")
            else:
                print("⚠️ 无数据")

        if args.daily:
            data = fetch_concept_daily(index_code)
            if data:
                fp = save_data(index_code, 'daily', data, category='concepts')
                print(f"✅ 日线: {len(data)} 天 → {fp}")
            else:
                print("⚠️ 无数据")

        # 默认获取日线+分时
        if not args.intraday and not args.daily:
            intraday = fetch_concept_intraday(index_code)
            daily = fetch_concept_daily(index_code)
            if intraday:
                fp = save_data(index_code, 'intraday_1min', intraday, category='concepts')
                total = sum(len(v) for v in intraday.values())
                date = list(intraday.keys())[0]
                print(f"✅ 分时: {total} 条 ({date}) → {fp}")
            if daily:
                fp = save_data(index_code, 'daily', daily, category='concepts')
                print(f"✅ 日线: {len(daily)} 天 → {fp}")

        return

    # 指数数据
    if args.index:
        code = args.index
        print(f"📊 获取指数数据: {code}")

        if args.intraday:
            data = fetch_index_intraday(code)
            if data:
                fp = save_data(code, 'intraday_1min', data)
                total = sum(len(v) for v in data.values())
                print(f"✅ 分时: {total} 条 → {fp}")
            else:
                print("⚠️ 无数据")

        if args.daily:
            data = fetch_index_daily(code, args.days)
            if data:
                fp = save_data(code, 'daily', data)
                print(f"✅ 日线: {len(data)} 天 → {fp}")
            else:
                print("⚠️ 无数据")

        return

    # 个股数据
    if args.code:
        code = args.code
        print(f"📊 获取股票数据: {code}")

        if args.intraday:
            data = fetch_stock_intraday(code)
            if data:
                fp = save_data(code, 'intraday_1min', data)
                total = sum(len(v) for v in data.values())
                date = list(data.keys())[0]
                print(f"✅ 分时: {total} 条 ({date}) → {fp}")
            else:
                print("⚠️ 无数据")

        if args.daily:
            data = fetch_stock_daily(code, args.days)
            if data:
                fp = save_data(code, 'daily', data)
                print(f"✅ 日线: {len(data)} 天 → {fp}")
            else:
                print("⚠️ 无数据")

        return

    # 无参数时显示帮助并提示常用命令
    print("\n📖 常用命令:")
    print("  python fetch_adata_data.py --watch          # 获取盯盘股数据")
    print("  python fetch_adata_data.py --concept-list   # 获取概念列表")
    print("  python fetch_adata_data.py --concept BK0612 # 获取锂电池板块数据")
    print("  python fetch_adata_data.py --all            # 获取全量数据")
    print()
    parser.print_help()


if __name__ == "__main__":
    main()
