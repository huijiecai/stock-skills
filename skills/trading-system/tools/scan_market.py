#!/usr/bin/env python3
# ⚠️ 近期扫描已可由 astock 取代：`astock query limit ladder`
#    但本脚本「近10天多次涨停+形态扫描」逻辑 astock 未覆盖，仍需保留。优先级详见 SKILL.md 「数据采集工具」章节。
"""
全市场扫描：从近10天涨停数据中找出形态好+有预期的主板标的
筛选条件：
1. 近10天涨停≥2次（说明有资金反复关注）
2. 主板标的（000/002/600/601/603）
3. 拉取30天日K线分析形态
"""
import json
import os
import sys
import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timedelta

# 路径
LIMIT_DIR = Path(__file__).resolve().parent.parent / "data" / "limit_list"
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "stocks"

# Tushare配置
TUSHARE_TOKEN = '78c2b09c8175affca2a45a788be6b0ba13369519220f7cd1b9c5b991'
TUSHARE_DOMAIN = 'http://tushare.xyz'


def is_mainboard(code: str) -> bool:
    """判断是否主板可买"""
    c = code.split('.')[0] if '.' in code else code
    return c.startswith(('000', '002', '600', '601', '603'))


def get_6digit(code: str) -> str:
    return code.split('.')[0] if '.' in code else code


def load_limit_data():
    """加载最近的涨停数据，统计每个标的涨停次数"""
    stock_stats = defaultdict(lambda: {
        'name': '', 'dates': [], 'first_times': [], 'pct_chgs': [], 'amounts': []
    })

    files = sorted(LIMIT_DIR.glob("limit-up-*.json"))
    # 取最近10个交易日
    files = files[-10:]
    print(f"📊 扫描 {len(files)} 个交易日的涨停数据")

    for fp in files:
        date_str = fp.stem.replace("limit-up-", "")
        # 格式化日期
        if len(date_str) == 8:
            date_fmt = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
        else:
            date_fmt = date_str

        with open(fp) as f:
            data = json.load(f)

        if isinstance(data, list):
            stocks = data
        elif isinstance(data, dict):
            stocks = data.get('enriched_stocks', data.get('stocks', []))
            if not stocks and 'code' in str(data):
                stocks = [data]
        else:
            continue

        for s in stocks:
            code = s.get('code', s.get('ts_code', ''))
            if not code:
                continue
            code6 = get_6digit(code)
            name = s.get('name', '')

            stock_stats[code6]['name'] = name or stock_stats[code6]['name']
            stock_stats[code6]['dates'].append(date_fmt)
            stock_stats[code6]['first_times'].append(s.get('first_time', ''))
            stock_stats[code6]['pct_chgs'].append(s.get('pct_chg', 0))
            stock_stats[code6]['amounts'].append(s.get('amount', 0))

    return stock_stats


def fetch_daily_tushare(code: str, days: int = 45) -> dict:
    """用Tushare拉日线"""
    try:
        import tushare as ts
        import tushare.pro.client as _client
        _client.DataApi._DataApi__http_url = TUSHARE_DOMAIN
        pro = ts.pro_api(TUSHARE_TOKEN)

        if code.startswith(('6', '9')):
            ts_code = f"{code}.SH"
        else:
            ts_code = f"{code}.SZ"

        end = datetime.now().strftime('%Y%m%d')
        start = (datetime.now() - timedelta(days=days)).strftime('%Y%m%d')

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
                'change_pct': float(row['pct_chg']),
                'volume': float(row['vol']),
                'amount': float(row['amount']) * 1000,
            }
        return result
    except Exception as e:
        return {}


def analyze_form(daily_data: dict) -> dict:
    """分析K线形态"""
    dates = sorted(daily_data.keys())
    if len(dates) < 20:
        return None

    closes = [daily_data[d]['close'] for d in dates]
    highs = [daily_data[d]['high'] for d in dates]
    lows = [daily_data[d]['low'] for d in dates]
    changes = [daily_data[d].get('change_pct', 0) for d in dates]

    latest = closes[-1]
    high_20d = max(highs[-20:])
    low_20d = min(lows[-20:])

    chg_5d = (latest / closes[-6] - 1) * 100
    chg_10d = (latest / closes[-11] - 1) * 100
    chg_20d = (latest / closes[-21] - 1) * 100
    drawdown = (latest / high_20d - 1) * 100

    avg_range = sum((highs[-i] - lows[-i]) / closes[-i - 1] * 100 for i in range(1, 6)) / 5

    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10
    ma20 = sum(closes[-20:]) / 20

    if ma5 > ma10 > ma20:
        trend = '多头'
    elif ma5 > ma10:
        trend = '偏多'
    elif ma5 < ma10 < ma20:
        trend = '空头'
    else:
        trend = '震荡'

    up_days_10 = sum(1 for c in changes[-10:] if c > 1)
    down_days_10 = sum(1 for c in changes[-10:] if c < -1)
    recent_5 = changes[-5:]

    return {
        'latest': latest, 'high_20d': high_20d,
        'chg_5d': chg_5d, 'chg_10d': chg_10d, 'chg_20d': chg_20d,
        'drawdown': drawdown, 'avg_range': avg_range,
        'trend': trend, 'ma5': ma5, 'ma10': ma10, 'ma20': ma20,
        'up_days_10': up_days_10, 'down_days_10': down_days_10,
        'recent_5': recent_5,
    }


def main():
    # Step 1: 统计涨停
    stock_stats = load_limit_data()

    # Step 2: 筛选主板+多次涨停
    candidates = []
    for code, info in stock_stats.items():
        if not is_mainboard(code):
            continue
        count = len(info['dates'])
        if count >= 2:
            candidates.append((code, info, count))

    candidates.sort(key=lambda x: x[2], reverse=True)
    print(f"✅ 主板标的涨停≥2次: {len(candidates)} 只")
    print()

    # Step 3: 拉K线+分析形态
    results = []
    total = len(candidates)
    for i, (code, info, count) in enumerate(candidates):
        # 先检查本地缓存
        local_fp = DATA_DIR / code / "daily.json"
        daily = None
        if local_fp.exists():
            with open(local_fp) as f:
                daily = json.load(f)
            if len(daily) < 20:
                daily = None

        if daily is None:
            daily = fetch_daily_tushare(code, 45)
            if daily:
                # 保存
                save_dir = DATA_DIR / code
                save_dir.mkdir(parents=True, exist_ok=True)
                with open(save_dir / "daily.json", 'w') as f:
                    json.dump(daily, f, ensure_ascii=False, indent=2)
                time.sleep(0.3)

        if not daily:
            continue

        form = analyze_form(daily)
        if form is None:
            continue

        form['code'] = code
        form['name'] = info['name']
        form['limit_count'] = count
        form['limit_dates'] = info['dates']
        results.append(form)

        if (i + 1) % 20 == 0:
            print(f"  进度: {i+1}/{total}")

    print(f"\n📊 成功分析 {len(results)} 只")
    print()

    # Step 4: 筛选形态好的
    print("=" * 120)
    print("🔍 全市场筛选: 多头排列 + 回撤<8% + 20日涨幅>5% + 近10天涨停≥2次")
    print("=" * 120)
    print()

    header = f"{'代码':8s} {'名称':10s} {'涨停次':>5s} {'收盘':>8s} {'5日':>7s} {'10日':>7s} {'20日':>7s} {'回撤':>6s} {'振幅':>5s} {'趋势':5s} {'近5日涨跌':20s}"
    print(header)
    print("-" * 120)

    matched = []
    for r in sorted(results, key=lambda x: (-x['limit_count'], x['drawdown']), reverse=False):
        if r['trend'] in ('多头',) and r['drawdown'] > -8 and r['chg_20d'] > 5:
            matched.append(r)
            recent = " ".join(f"{c:+.1f}" for c in r['recent_5'])
            print(f"{r['code']:8s} {r['name']:10s} {r['limit_count']:>5d} {r['latest']:>8.2f} {r['chg_5d']:>+6.1f}% {r['chg_10d']:>+6.1f}% {r['chg_20d']:>+6.1f}% {r['drawdown']:>+5.1f}% {r['avg_range']:>4.1f}% {r['trend']:5s} {recent}")

    print()
    print(f"共 {len(matched)} 只符合条件")
    print()

    # 额外：列出偏多但回撤小的（分歧中的）
    print("=" * 120)
    print("🔍 补充: 偏多/震荡 + 回撤<5% + 20日涨幅>10%（分歧但扛住的）")
    print("=" * 120)
    print()
    print(header)
    print("-" * 120)

    extra = []
    for r in sorted(results, key=lambda x: x['drawdown'], reverse=True):
        if r['code'] in [m['code'] for m in matched]:
            continue
        if r['trend'] in ('偏多', '震荡') and r['drawdown'] > -5 and r['chg_20d'] > 10:
            extra.append(r)
            recent = " ".join(f"{c:+.1f}" for c in r['recent_5'])
            print(f"{r['code']:8s} {r['name']:10s} {r['limit_count']:>5d} {r['latest']:>8.2f} {r['chg_5d']:>+6.1f}% {r['chg_10d']:>+6.1f}% {r['chg_20d']:>+6.1f}% {r['drawdown']:>+5.1f}% {r['avg_range']:>4.1f}% {r['trend']:5s} {recent}")

    print()
    print(f"共 {len(extra)} 只补充")


if __name__ == "__main__":
    main()
