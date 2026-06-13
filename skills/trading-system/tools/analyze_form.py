#!/usr/bin/env python3
# ⚠️ K 线形态分析 astock 未直接覆盖，本脚本仍可用；调用前建议先用 `astock query kline <code> --freq daily --json` 拉 K 线。
#    优先级详见 SKILL.md 「数据采集工具」章节。
"""分析候选个股K线形态"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "stocks"
stocks = {
    '600118': '中国卫星', '600879': '航天电子', '603308': '应流股份',
    '002407': '多氟多', '600549': '厦门钨业', '600487': '亨通光电',
    '002384': '东山精密', '600105': '永鼎股份', '603220': '中贝通信',
    '600986': '浙文互联', '601138': '工业富联', '600343': '航天动力',
    '002465': '海格通信', '601698': '中国卫通', '002151': '北斗星通',
}

header = f"{'代码':8s} {'名称':8s} {'收盘':>8s} {'5日':>7s} {'10日':>8s} {'20日':>8s} {'20日高':>8s} {'回撤':>7s} {'振幅':>6s} {'趋势':6s}"
print(header)
print('-' * 100)

results = []
for code, name in stocks.items():
    fp = DATA / code / "daily.json"
    if not fp.exists():
        continue
    with open(fp) as f:
        data = json.load(f)

    dates = sorted(data.keys())
    if len(dates) < 20:
        continue

    closes = [data[d]['close'] for d in dates]
    highs = [data[d]['high'] for d in dates]
    lows = [data[d]['low'] for d in dates]
    changes = [data[d].get('change_pct', 0) for d in dates]

    latest = closes[-1]
    high_20d = max(highs[-20:])

    chg_5d = (latest / closes[-6] - 1) * 100
    chg_10d = (latest / closes[-11] - 1) * 100
    chg_20d = (latest / closes[-21] - 1) * 100

    drawdown = (latest / high_20d - 1) * 100

    # 近5日平均振幅
    avg_range = sum((highs[-i] - lows[-i]) / closes[-i - 1] * 100 for i in range(1, 6)) / 5

    # 均线
    ma5 = sum(closes[-5:]) / 5
    ma10 = sum(closes[-10:]) / 10
    ma20 = sum(closes[-20:]) / 20

    if ma5 > ma10 > ma20:
        trend = '多头↑'
    elif ma5 > ma10:
        trend = '偏多'
    elif ma5 < ma10 < ma20:
        trend = '空头↓'
    else:
        trend = '震荡'

    # 流畅度: 近10日中阳线天数(涨>1%) vs 阴线天数
    up_days_10 = sum(1 for c in changes[-10:] if c > 1)
    down_days_10 = sum(1 for c in changes[-10:] if c < -1)

    # 最近5天的走势描述
    recent_5 = [f"{c:+.1f}" for c in changes[-5:]]

    results.append({
        'code': code, 'name': name, 'latest': latest,
        'chg_5d': chg_5d, 'chg_10d': chg_10d, 'chg_20d': chg_20d,
        'drawdown': drawdown, 'avg_range': avg_range, 'trend': trend,
        'ma5': ma5, 'ma10': ma10, 'ma20': ma20, 'high_20d': high_20d,
        'up_days_10': up_days_10, 'down_days_10': down_days_10,
        'recent_5': recent_5,
    })

    print(f"{code:8s} {name:8s} {latest:>8.2f} {chg_5d:>+6.1f}% {chg_10d:>+7.1f}% {chg_20d:>+7.1f}% {high_20d:>8.2f} {drawdown:>+6.1f}% {avg_range:>5.1f}% {trend:6s}")

print()
print("=" * 100)
print()
print("🔍 符合条件: 走得流畅(多头/偏多) + 回撤不大(<10%) + 20日有涨幅")
print()

matched = []
for r in sorted(results, key=lambda x: x['chg_20d'], reverse=True):
    if r['trend'] in ('多头↑', '偏多') and r['drawdown'] > -10 and r['chg_20d'] > 0:
        flag = '⚡' if r['trend'] == '多头↑' and r['drawdown'] > -5 else '✅'
        matched.append(r)
        print(f"  {flag} {r['code']} {r['name']:8s}")
        print(f"     收盘{r['latest']:.2f} | 20日高点{r['high_20d']:.2f} | 回撤{r['drawdown']:+.1f}%")
        print(f"     5日{r['chg_5d']:+.1f}% | 10日{r['chg_10d']:+.1f}% | 20日{r['chg_20d']:+.1f}%")
        print(f"     均线{r['trend']} | MA5={r['ma5']:.2f} > MA10={r['ma10']:.2f} > MA20={r['ma20']:.2f}")
        print(f"     近5日涨跌: {' '.join(r['recent_5'])}%")
        print(f"     近10日: {r['up_days_10']}天涨>1% / {r['down_days_10']}天跌>1% | 日均振幅{r['avg_range']:.1f}%")
        print()

if not matched:
    print("  ⚠️ 无个股同时满足多头+低回撤+正涨幅")
    print()
    print("  退而求其次，列出偏多或震荡中回撤最小的：")
    for r in sorted(results, key=lambda x: x['drawdown'], reverse=True)[:5]:
        print(f"    {r['code']} {r['name']:8s} 收{r['latest']:.2f} 回撤{r['drawdown']:+.1f}% 趋势{r['trend']} 近5日:{' '.join(r['recent_5'])}%")
