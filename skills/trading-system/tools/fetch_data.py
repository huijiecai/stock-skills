#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交易系统数据采集工具

为预期驱动交易系统提供轻量级数据采集，直接保存为本地文件。
依赖：tushare（pip install tushare）

使用方法：
    # 设置 Tushare Token（一次性）
    export TUSHARE_TOKEN='your_token'
    
    # 如果使用自定义域名（如 tushare.xyz）
    export TUSHARE_DOMAIN='http://tushare.xyz'
    
    # 采集融捷股份最近30天日线+分钟数据
    python fetch_data.py --code 002192 --days 30 --intraday
    
    # 指定日期范围
    python fetch_data.py --code 002192 --start 2026-03-01 --end 2026-03-27 --intraday
    
    # 采集指定频率的分时数据
    python fetch_data.py --code 002192 --days 7 --intraday --freq 5min
    
    # 采集大盘指数日线
    python fetch_data.py --code 000001 --days 60  # 上证指数
    
    # 采集涨停数据
    python fetch_data.py --limit-up --date 2026-03-27
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


# ─── 配置 ───────────────────────────────────────────────────────────

TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")

# 数据保存根目录
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def get_pro():
    """获取 Tushare pro API 实例"""
    import tushare.pro.client as _client
    
    # 自定义域名（如果使用 tushare.xyz）
    custom_domain = os.environ.get("TUSHARE_DOMAIN", "")
    if custom_domain:
        _client.DataApi._DataApi__http_url = custom_domain
    
    if not TUSHARE_TOKEN:
        print("❌ 请设置 TUSHARE_TOKEN 环境变量")
        print("   export TUSHARE_TOKEN='your_token'")
        if custom_domain:
            print(f"   export TUSHARE_DOMAIN='{custom_domain}'  (已设置)")
        sys.exit(1)
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
    """
    采集日线数据
    
    Returns: {date: {open, high, low, close, pre_close, pct_chg, vol, amount, turnover_rate}, ...}
    """
    pro = get_pro()
    ts_code = get_ts_code(code)
    start = start_date.replace('-', '')
    end = end_date.replace('-', '')
    
    df = pro.daily(
        ts_code=ts_code,
        start_date=start,
        end_date=end,
        fields='ts_code,trade_date,open,high,low,close,pre_close,pct_chg,vol,amount'
    )
    
    if df is None or df.empty:
        return {}
    
    # 同时获取基本面数据
    basic_df = pro.daily_basic(
        ts_code=ts_code,
        start_date=start,
        end_date=end,
        fields='ts_code,trade_date,turnover_rate,turnover_rate_f,pe_ttm,pb,ps_ttm,total_mv,circ_mv'
    )
    
    basic_dict = {}
    if basic_df is not None and not basic_df.empty:
        for _, row in basic_df.iterrows():
            basic_dict[str(row['trade_date'])] = row.to_dict()
    
    result = {}
    for _, row in df.iterrows():
        date_str = str(row['trade_date'])
        date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        basic = basic_dict.get(date_str, {})
        result[date_fmt] = {
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'pre_close': float(row['pre_close']),
            'pct_chg': float(row['pct_chg']),
            'vol': float(row['vol']),           # 成交量（手）
            'amount': float(row['amount']) * 1000,  # 成交额（元）
            'turnover_rate': basic.get('turnover_rate'),
            'pe_ttm': basic.get('pe_ttm'),
            'pb': basic.get('pb'),
            'total_mv': basic.get('total_mv'),
            'circ_mv': basic.get('circ_mv'),
        }
    
    return result


# ─── 分钟数据 ──────────────────────────────────────────────────────

def fetch_intraday(code: str, start_date: str, end_date: str, freq: str = '1min') -> dict:
    """
    采集分钟级数据
    
    注意：需要 Tushare 5000积分权限
    一次最多返回约8000条（约3-4天的1min数据），需要分批
    
    Returns: {date: [{time, open, high, low, close, vol, amount}, ...], ...}
    """
    pro = get_pro()
    ts_code = get_ts_code(code)
    
    from datetime import datetime as dt
    start_dt = dt.strptime(start_date.replace('-', ''), '%Y%m%d')
    end_dt = dt.strptime(end_date.replace('-', ''), '%Y%m%d')
    
    result = {}
    current = start_dt
    
    while current <= end_dt:
        # 每批最多3天（避免超8000条限制）
        batch_end = min(current + timedelta(days=5), end_dt)
        
        start_time = current.strftime('%Y-%m-%d 09:00:00')
        end_time = batch_end.strftime('%Y-%m-%d 15:30:00')
        
        try:
            df = pro.stk_mins(
                ts_code=ts_code,
                freq=freq,
                start_date=start_time,
                end_date=end_time,
                fields='ts_code,trade_time,open,high,low,close,vol,amount'
            )
            
            if df is not None and not df.empty:
                for _, row in df.iterrows():
                    trade_time = str(row['trade_time'])
                    # 提取日期部分
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
            if '权限' in str(e) or 'Permission' in str(e):
                print(f"  ❌ 分钟线接口需要5000积分权限")
                return {}
            print(f"  ❌ 请求失败: {e}")
        
        current = batch_end + timedelta(days=1)
        time.sleep(0.5)  # 避免 API 疲劳
    
    return result


# ─── 涨停数据 ──────────────────────────────────────────────────────

def fetch_limit_up(date: str) -> list:
    """
    采集指定日期的涨停数据
    
    Returns: [{code, name, close, pct_chg, amount, industry, ...}, ...]
    """
    pro = get_pro()
    date_compact = date.replace('-', '')
    
    # 涨停板数据
    df = pro.limit_list_d(
        trade_date=date_compact,
        limit_type='U',  # 涨停
    )
    
    if df is None or df.empty:
        return []
    
    result = []
    for _, row in df.iterrows():
        result.append({
            'code': row.get('ts_code', ''),
            'name': row.get('name', ''),
            'close': float(row.get('close', 0)),
            'pct_chg': float(row.get('pct_chg', 0)),
            'amount': float(row.get('amount', 0)),
            'limit_amount': float(row.get('limit_amount', 0)),  # 封单金额
            'first_time': row.get('first_time', ''),           # 首次封板时间
            'last_time': row.get('last_time', ''),             # 最后封板时间
            'open_times': int(row.get('open_times', 0)),        # 打开次数
            'industry': row.get('industry', ''),
            'fd_amount': float(row.get('fd_amount', 0)),        # 封单资金
        })
    
    return result


# ─── 指数数据 ──────────────────────────────────────────────────────

def fetch_index_daily(code: str = '000001', start_date: str = None, end_date: str = None) -> dict:
    """
    采集指数日线数据
    
    常用指数代码：
    - 000001: 上证指数
    - 399001: 深证成指
    - 399006: 创业板指
    - 399005: 中小板指
    """
    pro = get_pro()
    
    if end_date is None:
        end_date = datetime.now().strftime('%Y%m%d')
    else:
        end_date = end_date.replace('-', '')
    if start_date is None:
        start_date = (datetime.now() - timedelta(days=60)).strftime('%Y%m%d')
    else:
        start_date = start_date.replace('-', '')
    
    df = pro.index_daily(
        ts_code=f"{code}.SH" if code.startswith('0') else f"{code}.SZ",
        start_date=start_date,
        end_date=end_date,
        fields='ts_code,trade_date,open,high,low,close,pct_chg,vol,amount'
    )
    
    if df is None or df.empty:
        return {}
    
    result = {}
    for _, row in df.iterrows():
        date_str = str(row['trade_date'])
        date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        result[date_fmt] = {
            'open': float(row['open']),
            'high': float(row['high']),
            'low': float(row['low']),
            'close': float(row['close']),
            'pct_chg': float(row['pct_chg']),
            'vol': float(row['vol']),
            'amount': float(row['amount']) * 1000,
        }
    
    return result


# ─── 保存 ──────────────────────────────────────────────────────────

def save_data(code: str, data_type: str, data: dict):
    """保存数据到本地 JSON 文件"""
    save_dir = DATA_DIR / code
    save_dir.mkdir(parents=True, exist_ok=True)
    
    filepath = save_dir / f"{data_type}.json"
    
    # 如果文件已存在，合并数据
    if filepath.exists() and data_type in ('daily', 'intraday'):
        with open(filepath, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        existing.update(data)
        data = existing
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return filepath


# ─── 主流程 ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='交易系统数据采集工具')
    parser.add_argument('--code', type=str, help='股票代码（如 002192）')
    parser.add_argument('--days', type=int, default=30, help='最近N天（默认30）')
    parser.add_argument('--start', type=str, help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--intraday', action='store_true', help='同时采集分钟数据')
    parser.add_argument('--freq', type=str, default='1min', choices=['1min', '5min', '15min', '30min', '60min'], help='分钟数据频率（默认1min）')
    parser.add_argument('--limit-up', action='store_true', help='采集涨停数据')
    parser.add_argument('--date', type=str, help='指定日期（涨停数据用）')
    parser.add_argument('--index', action='store_true', help='采集指数数据')
    
    args = parser.parse_args()
    
    # 计算日期范围
    if args.start:
        start = args.start
        end = args.end or datetime.now().strftime('%Y-%m-%d')
    else:
        end = datetime.now().strftime('%Y-%m-%d')
        start = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
    
    if args.limit_up:
        date = args.date or datetime.now().strftime('%Y-%m-%d')
        print(f"📊 采集涨停数据: {date}")
        data = fetch_limit_up(date)
        if data:
            filepath = save_data(f"limit-up-{date.replace('-', '')}", 'limit_up', data)
            print(f"✅ 保存 {len(data)} 只涨停股 → {filepath}")
        else:
            print("⚠️ 无涨停数据")
        return
    
    if not args.code:
        parser.error("请指定 --code 或 --limit-up")
    
    code = args.code.strip()
    ts_code = get_ts_code(code)
    print(f"📊 采集 {ts_code} 数据")
    print(f"📅 范围: {start} ~ {end}")
    print("=" * 50)
    
    # 日线
    print("\n📈 采集日线数据...")
    daily = fetch_daily(code, start, end)
    if daily:
        filepath = save_data(code, 'daily', daily)
        print(f"✅ {len(daily)} 天日线 → {filepath}")
    else:
        print("⚠️ 无日线数据")
    
    # 分钟数据
    if args.intraday:
        print(f"\n⏱️ 采集分钟数据（{args.freq}）...")
        intraday = fetch_intraday(code, start, end, args.freq)
        if intraday:
            filepath = save_data(code, f'intraday_{args.freq}', intraday)
            total_bars = sum(len(v) for v in intraday.values())
            print(f"✅ {len(intraday)} 天 {total_bars} 条 → {filepath}")
        else:
            print("⚠️ 无分钟数据")
    
    print("\n🎉 采集完成！")


if __name__ == "__main__":
    main()
