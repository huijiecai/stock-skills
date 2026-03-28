#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易系统数据采集工具

为预期驱动交易系统提供轻量级数据采集，直接保存为本地文件。
依赖：tushare（pip install tushare）

使用方法：
    # 采集融捷股份最近30天日线+分钟数据
    python fetch_data.py --code 002192 --days 30 --intraday

    # 指定日期范围
    python fetch_data.py --code 002192 --start 2026-03-01 --end 2026-03-27 --intraday

    # 采集指定频率的分时数据
    python fetch_data.py --code 002192 --days 7 --intraday --freq 5min

    # 采集大盘指数日线
    python fetch_data.py --code 000001 --days 60  # 上证指数

    # 采集涨停数据（含首封时间、行业、炸板次数）
    python fetch_data.py --limit-up --date 2026-03-27

    # 采集跌停数据
    python fetch_data.py --limit-up --date 2026-03-27 --type D

    # 采集全市场（所有盯盘股 + 指数 + 涨停跌停）一天的数据
    python fetch_data.py --all --date 2026-03-27
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

try:
    import tushare as ts
except ImportError:
    print("❌ 需要安装 tushare: pip install tushare")
    sys.exit(1)


# ─── 配置（写死，无需环境变量）──────────────────────────────────────

TUSHARE_TOKEN = '78c2b09c8175affca2a45a788be6b0ba13369519220f7cd1b9c5b991'
TUSHARE_DOMAIN = 'http://tushare.xyz'

# 数据保存根目录（和脚本同级的上级 data/）
DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# 默认盯盘股列表（代码）
DEFAULT_WATCHLIST = [
    '002192',  # 融捷股份
    '000722',  # 湖南发展
    '600726',  # 华电能源
    '600396',  # 华电辽能
    '000720',  # 新能泰山
    '002361',  # 神剑股份
]

# 指数列表（代码）
DEFAULT_INDICES = ['000001', '399001', '399006']  # 上证 深成 创业板


def get_pro():
    """获取 Tushare pro API 实例"""
    import tushare.pro.client as _client
    _client.DataApi._DataApi__http_url = TUSHARE_DOMAIN
    return ts.pro_api(TUSHARE_TOKEN)


def get_ts_code(code: str) -> str:
    """6位代码 -> Tushare格式（如 002192 -> 002192.SZ）"""
    code = code.strip()
    if '.' in code:
        return code.upper()
    if code.startswith(('6', '9')):
        return f"{code}.SH"
    elif code.startswith(('0', '3', '2')):
        return f"{code}.SZ"
    elif code.startswith('4') or code.startswith('8'):
        return f"{code}.BJ"
    return f"{code}.SZ"


# ─── 日线数据 ──────────────────────────────────────────────────────

def fetch_daily(code: str, start_date: str, end_date: str) -> dict:
    """采集日线数据"""
    pro = get_pro()
    ts_code = get_ts_code(code)
    start = start_date.replace('-', '')
    end = end_date.replace('-', '')

    df = pro.daily(
        ts_code=ts_code, start_date=start, end_date=end,
        fields='ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount'
    )
    if df is None or df.empty:
        return {}

    result = {}
    for _, row in df.iterrows():
        d = str(row['trade_date'])
        date_fmt = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
        result[date_fmt] = {
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'pre_close': float(row['pre_close']),
            'pct_chg': float(row['pct_chg']),
            'vol': float(row['vol']),
            'amount': float(row['amount']) * 1000,
        }
    return result


# ─── 分钟数据 ──────────────────────────────────────────────────────

def fetch_intraday(code: str, start_date: str, end_date: str, freq: str = '1min') -> dict:
    """
    采集分钟级数据（个股用 stk_mins，指数用 idx_mins）
    Returns: {date: [{time, open, high, low, close, vol, amount}, ...], ...}
    """
    pro = get_pro()
    ts_code = get_ts_code(code)
    is_index = code in DEFAULT_INDICES

    start_dt = datetime.strptime(start_date.replace('-', ''), '%Y%m%d')
    end_dt = datetime.strptime(end_date.replace('-', ''), '%Y%m%d')
    result = {}
    current = start_dt

    while current <= end_dt:
        batch_end = min(current + timedelta(days=5), end_dt)
        start_time = current.strftime('%Y-%m-%d 09:00:00')
        end_time = batch_end.strftime('%Y-%m-%d 15:30:00')

        try:
            if is_index:
                # 指数用 idx_mins（需要单独开权限）
                df = pro.idx_mins(
                    ts_code=ts_code, freq=freq,
                    start_date=start_time, end_date=end_time,
                    fields='ts_code,trade_time,open,high,low,close,vol,amount'
                )
            else:
                # 个股用 stk_mins
                df = pro.stk_mins(
                    ts_code=ts_code, freq=freq,
                    start_date=start_time, end_date=end_time,
                    fields='ts_code,trade_time,open,high,low,close,vol,amount'
                )

            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    trade_time = str(row['trade_time'])
                    date_part = trade_time[:10]
                    time_part = trade_time[11:]
                    if date_part not in result:
                        result[date_part] = []
                    result[date_part].append({
                        'time': time_part,
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'vol': float(row['vol']),
                        'amount': float(row['amount']) * 1000,
                    })
                print(f"  ✅ {current.strftime('%Y-%m-%d')} ~ {batch_end.strftime('%Y-%m-%d')}: {len(df)} 条")
            else:
                print(f"  ⏭️ {current.strftime('%Y-%m-%d')} ~ {batch_end.strftime('%Y-%m-%d')}: 无数据")

        except Exception as e:
            err = str(e)
            if '权限' in err:
                hint = 'idx_mins' if is_index else 'stk_mins'
                print(f"  ❌ {hint} 接口权限不足")
                return {}
            print(f"  ❌ 请求失败: {e}")

        current = batch_end + timedelta(days=1)
        time.sleep(0.5)

    return result


# ─── 指数分时（腾讯财经备用，免费）──────────────────────────────────

def fetch_index_min_tencent(code: str, date_str: str) -> list:
    """
    从腾讯财经获取指数分时数据（免费，无需token）
    仅支持最近一个交易日的历史分时
    code: 000001 / 399001 / 399006
    Returns: [{time, close, vol, amount}, ...]
    """
    import urllib.request

    prefix = 'sh' if code.startswith('0') else 'sz'
    full_code = f'{prefix}{code}'
    url = f'https://web.ifzq.gtimg.cn/appstock/app/minute/query?_var=min_data&code={full_code}'

    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        text = urllib.request.urlopen(req, timeout=10).read().decode()
        if 'min_data=' in text:
            text = text.split('min_data=', 1)[1]
        data = json.loads(text)
        raw = data['data'][full_code]['data']['data']

        bars = []
        for line in raw:
            parts = line.split(' ')
            bars.append({
                'time': f'{parts[0][:2]}:{parts[0][2:4]}',
                'close': float(parts[1]),
                'vol': float(parts[2]),
                'amount': float(parts[3]),
            })
        return bars
    except Exception as e:
        print(f"  ❌ 腾讯财经接口失败: {e}")
        return []


# ─── 涨停/跌停数据 ────────────────────────────────────────────────

def fetch_limit_list(date: str, limit_type: str = 'U') -> list:
    """
    采集涨停/跌停数据
    limit_type: 'U'=涨停, 'D'=跌停
    Returns: [{code, name, close, pct_chg, industry, first_time, open_times, ...}, ...]
    """
    pro = get_pro()
    date_compact = date.replace('-', '')

    df = pro.limit_list_d(trade_date=date_compact, limit_type=limit_type)

    if df is None or df.empty:
        return []

    result = []
    for _, row in df.iterrows():
        # 解析 first_time
        ft = str(row.get('first_time', ''))
        if len(ft) == 6:
            ft = f'{ft[:2]}:{ft[2:4]}:{ft[4:6]}'

        result.append({
            'code': row.get('ts_code', ''),
            'name': row.get('name', ''),
            'close': float(row.get('close', 0)),
            'pct_chg': float(row.get('pct_chg', 0)),
            'amount': float(row.get('amount', 0)),
            'limit_amount': float(row.get('limit_amount', 0)),
            'first_time': ft,
            'last_time': row.get('last_time', ''),
            'open_times': int(row.get('open_times', 0) or 0),
            'industry': row.get('industry', ''),
            'fd_amount': float(row.get('fd_amount', 0)),
        })
    return result


# ─── 保存 ──────────────────────────────────────────────────────────

def save_data(code: str, data_type: str, data):
    """保存数据到本地 JSON 文件"""
    if isinstance(data, list):
        # 涨停跌停等列表数据，不合并
        save_dir = DATA_DIR / code
        save_dir.mkdir(parents=True, exist_ok=True)
        filepath = save_dir / f"{data_type}.json"
    else:
        save_dir = DATA_DIR / code
        save_dir.mkdir(parents=True, exist_ok=True)
        filepath = save_dir / f"{data_type}.json"

        # 日线/分时数据，合并已有文件
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                existing = json.load(f)
            if isinstance(existing, dict) and isinstance(data, dict):
                existing.update(data)
                data = existing

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return filepath


# ─── 全量采集（一天）──────────────────────────────────────────────

def fetch_all(date: str, watchlist: list = None):
    """采集一天的全量数据：盯盘股日线+分时 + 涨停 + 跌停 + 指数"""
    if watchlist is None:
        watchlist = DEFAULT_WATCHLIST

    print(f"{'='*60}")
    print(f"📊 全量采集: {date}")
    print(f"盯盘股: {watchlist}")
    print(f"{'='*60}")

    # 1. 涨停数据
    print(f"\n🔴 涨停数据...")
    up_list = fetch_limit_list(date, 'U')
    if up_list:
        fp = save_data(f"limit-up-{date.replace('-', '')}", 'limit_up', up_list)
        print(f"✅ 涨停 {len(up_list)} 只 → {fp}")
    else:
        print("⚠️ 无涨停数据")

    # 2. 跌停数据
    print(f"\n🟢 跌停数据...")
    down_list = fetch_limit_list(date, 'D')
    if down_list:
        fp = save_data(f"limit-down-{date.replace('-', '')}", 'limit_down', down_list)
        print(f"✅ 跌停 {len(down_list)} 只 → {fp}")
    else:
        print("⚠️ 无跌停数据")

    # 3. 盯盘股日线+分时
    print(f"\n📈 盯盘股数据...")
    for code in watchlist:
        ts_code = get_ts_code(code)
        print(f"\n  --- {code} ({ts_code}) ---")

        # 日线
        daily = fetch_daily(code, date, date)
        if daily:
            save_data(code, 'daily', daily)
            d = list(daily.values())[0]
            print(f"  📅 日线: {d['close']:.2f} ({d['pct_chg']:+.2f}%)")

        # 分时
        intraday = fetch_intraday(code, date, date)
        if intraday:
            fp = save_data(code, 'intraday_1min', intraday)
            total = sum(len(v) for v in intraday.values())
            print(f"  ⏱️ 分时: {total} 条 → {fp}")

    # 4. 指数（优先 Tushare idx_mins，失败则用腾讯）
    print(f"\n📊 指数数据...")
    for code in DEFAULT_INDICES:
        name = {'000001': '上证指数', '399001': '深证成指', '399006': '创业板指'}[code]
        print(f"\n  --- {name} ({code}) ---")

        # 日线
        daily = fetch_daily(code, date, date)
        if daily:
            save_data(code, 'daily', daily)
            d = list(daily.values())[0]
            print(f"  📅 日线: {d['close']:.2f} ({d['pct_chg']:+.2f}%)")

        # 分时（Tushare idx_mins）
        intraday = fetch_intraday(code, date, date)
        if intraday:
            fp = save_data(code, 'intraday_1min', intraday)
            total = sum(len(v) for v in intraday.values())
            print(f"  ⏱️ 分时(tushare): {total} 条")
        else:
            # 备用：腾讯财经（仅最近一个交易日）
            print(f"  ⚠️ Tushare idx_mins 权限不足，尝试腾讯财经...")
            bars = fetch_index_min_tencent(code, date)
            if bars:
                # 腾讯返回 close/vol/amount，补齐格式
                full_bars = []
                for b in bars:
                    full_bars.append({
                        'time': b['time'],
                        'open': b['close'],  # 腾讯分时只有 close
                        'high': b['close'],
                        'low': b['close'],
                        'close': b['close'],
                        'vol': b['vol'],
                        'amount': b['amount'],
                    })
                fp = save_data(code, 'intraday_1min_tencent', {date: full_bars})
                print(f"  ⏱️ 分时(腾讯): {len(full_bars)} 条 → {fp}")
            else:
                print(f"  ❌ 指数分时获取失败")

    print(f"\n{'='*60}")
    print("🎉 全量采集完成！")


# ─── 主流程 ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='交易系统数据采集工具')
    parser.add_argument('--code', type=str, help='股票/指数代码（如 002192）')
    parser.add_argument('--days', type=int, default=30, help='最近N天（默认30）')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--intraday', action='store_true', help='同时采集分钟数据')
    parser.add_argument('--freq', type=str, default='1min', choices=['1min','5min','15min','30min','60min'])
    parser.add_argument('--limit-up', action='store_true', help='采集涨停/跌停数据')
    parser.add_argument('--type', type=str, default='U', choices=['U','D'], help='U=涨停 D=跌停')
    parser.add_argument('--date', type=str, help='指定日期')
    parser.add_argument('--all', action='store_true', help='全量采集（盯盘股+涨停+指数）')
    parser.add_argument('--watchlist', type=str, nargs='+', help='自定义盯盘股列表')

    args = parser.parse_args()

    if args.all:
        date = args.date or datetime.now().strftime('%Y-%m-%d')
        wl = args.watchlist or DEFAULT_WATCHLIST
        fetch_all(date, wl)
        return

    if args.limit_up:
        date = args.date or datetime.now().strftime('%Y-%m-%d')
        label = '涨停' if args.type == 'U' else '跌停'
        print(f"📊 采集{label}数据: {date}")
        data = fetch_limit_list(date, args.type)
        if data:
            tag = 'limit-up' if args.type == 'U' else 'limit-down'
            filepath = save_data(f"{tag}-{date.replace('-', '')}", f'limit_{args.type.lower()}', data)
            print(f"✅ {label} {len(data)} 只 → {filepath}")
        else:
            print("⚠️ 无数据")
        return

    if not args.code:
        parser.error("请指定 --code / --limit-up / --all")

    code = args.code.strip()
    ts_code = get_ts_code(code)
    end = args.end or datetime.now().strftime('%Y-%m-%d')
    start = args.start or (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')

    print(f"📊 采集 {ts_code} | {start} ~ {end}")

    # 日线
    daily = fetch_daily(code, start, end)
    if daily:
        filepath = save_data(code, 'daily', daily)
        print(f"✅ 日线 {len(daily)} 天 → {filepath}")

    # 分钟数据
    if args.intraday:
        print(f"⏱️ 分钟数据（{args.freq}）...")
        intraday = fetch_intraday(code, start, end, args.freq)
        if intraday:
            filepath = save_data(code, f'intraday_{args.freq}', intraday)
            total = sum(len(v) for v in intraday.values())
            print(f"✅ {len(intraday)} 天 {total} 条 → {filepath}")

    print("🎉 完成！")


if __name__ == "__main__":
    main()
