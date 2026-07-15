#!/usr/bin/env python3
"""
每日盈亏回溯补全脚本
- 从trades.md解析全部交易
- 调用astock查询持仓股票的日K收盘价
- 逐日计算总资产（现金+持仓市值）
- 输出每日盈亏汇总表（markdown格式）
"""

import re
import sys
import json
import subprocess
from pathlib import Path
from collections import defaultdict

ASTOCK = str(Path(__file__).resolve().parents[3] / "astock" / "astock")
TRADES_FILE = Path(__file__).resolve().parent.parent / "data" / "trades.md"
INITIAL_CASH = 100000.0

# 偏差修正
ADJUSTMENTS = [
    ("05-22", -30.0),   # 博迁买入价差
    ("06-01", -3699.0),  # 未记录交易
]

def parse_trades(filepath):
    """从trades.md解析全部交易记录"""
    content = filepath.read_text(encoding="utf-8")
    pattern = re.compile(
        r'\|\s*(\d+)\s*\|\s*(\d{2}-\d{2})\s*\|\s*(买入|卖出|挂单|排板撤销)\s*\|\s*(\S+)\s*\|\s*(\d{6})\s*\|\s*([\d.]+)\s*\|\s*(\d+)\s*\|'
    )
    trades = []
    for m in pattern.finditer(content):
        seq = int(m.group(1))
        date = m.group(2)
        action = m.group(3)
        name = m.group(4).strip()
        code = m.group(5)
        price = float(m.group(6))
        qty = int(m.group(7))
        trades.append((seq, date, action, name, code, price, qty))
    return trades

def query_kline(code, from_date, to_date):
    """调用astock查询日K线，分月查询避免30条限制，返回 {date: close_price}"""
    # 分月查询
    months = [
        ("20260401", "20260430"),
        ("20260501", "20260531"),
        ("20260601", "20260630"),
        ("20260701", "20260703"),
    ]
    result_map = {}
    for m_from, m_to in months:
        if m_from < from_date or m_to > to_date:
            continue
        cmd = [ASTOCK, "query", "kline", code, "--from", m_from, "--to", m_to, "--json"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(f"  ⚠️ 查询 {code} {m_from}~{m_to} 失败: {result.stderr[:100]}")
            continue
        try:
            data = json.loads(result.stdout)
            for item in data:
                result_map[item["trade_date"]] = item["close"]
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  ⚠️ 解析 {code} {m_from}~{m_to} 失败: {e}")
    return result_map

def get_trading_days(close_maps):
    """从所有K线数据中收集交易日列表"""
    days = set()
    for code, m in close_maps.items():
        for d in m:
            days.add(d)
    return sorted(days)

def fmt_date(date_str):
    """2026-04-08 -> 04-08"""
    return date_str[5:]

def apply_adjustments(cash, date_str):
    """应用偏差修正"""
    date_md = date_str[5:]  # MM-DD
    for adj_date, adj_amount in ADJUSTMENTS:
        if date_md >= adj_date:
            cash += adj_amount
    return cash

def main():
    trades = parse_trades(TRADES_FILE)
    print(f"解析到 {len(trades)} 笔交易")
    
    # 收集所有涉及到的股票代码
    all_codes = set(t[4] for t in trades if t[2] in ("买入", "卖出"))
    print(f"涉及股票: {all_codes}")
    
    # 查询所有股票的日K线（04-01到07-03）
    print("\n查询日K线数据...")
    close_maps = {}
    for code in sorted(all_codes):
        print(f"  查询 {code}...", end=" ")
        close_maps[code] = query_kline(code, "20260401", "20260703")
        # 过滤只保留04-01以后的数据
        close_maps[code] = {d: p for d, p in close_maps[code].items() if d >= "2026-04-01"}
        n = len(close_maps[code])
        print(f"{n} 条记录")
    
    # 获取交易日列表
    all_days = get_trading_days(close_maps)
    print(f"\n交易日总数: {len(all_days)}")
    
    # 过滤需要补全的日期范围
    # Gap 1: 04-02到06-08
    # Gap 2: 06-10到07-02（排除已有06-16）
    # 计算所有交易日（04-01到07-02），用精算值替换整个缺口
    target_days = [d for d in all_days if "04-01" <= fmt_date(d) <= "07-02"]
    gap_days = target_days
    
    print(f"需要补全的交易日: {len(gap_days)}")
    
    if not gap_days:
        print("无需要补全的日期")
        return
    
    # 逐日计算
    # 先处理到gap开始之前的所有交易，获得初始状态
    first_gap_day = gap_days[0]
    first_gap_md = fmt_date(first_gap_day)
    
    # 处理所有在gap之前发生的交易
    pre_trades = [t for t in trades if t[1] < first_gap_md]
    
    cash = INITIAL_CASH
    holdings = {}  # code -> {name, shares, total_cost}
    
    for t in pre_trades:
        seq, date, action, name, code, price, qty = t
        if action in ("挂单", "排板撤销"):
            continue
        if action == "买入":
            cash -= price * qty
            if code not in holdings:
                holdings[code] = {"name": name, "shares": 0, "total_cost": 0.0}
            holdings[code]["total_cost"] += price * qty
            holdings[code]["shares"] += qty
        elif action == "卖出":
            cash += price * qty
            if code in holdings:
                h = holdings[code]
                avg = h["total_cost"] / h["shares"] if h["shares"] > 0 else 0
                h["total_cost"] -= avg * qty
                h["shares"] -= qty
                if h["shares"] == 0:
                    h["total_cost"] = 0.0
    
    # 应用偏差修正到gap开始前
    cash_adj = apply_adjustments(cash, first_gap_day)
    
    # 计算gap前最后一个交易日的总资产作为期初
    # 找gap前最后一个交易日
    pre_days = [d for d in all_days if d < first_gap_day]
    if pre_days:
        last_pre_day = pre_days[-1]
        # 重新计算到这一天
        last_pre_md = fmt_date(last_pre_day)
        cash_pre = INITIAL_CASH
        holdings_pre = {}
        for t in trades:
            if t[1] > last_pre_md:
                break
            seq, date, action, name, code, price, qty = t
            if action in ("挂单", "排板撤销"):
                continue
            if action == "买入":
                cash_pre -= price * qty
                if code not in holdings_pre:
                    holdings_pre[code] = {"name": name, "shares": 0, "total_cost": 0.0}
                holdings_pre[code]["total_cost"] += price * qty
                holdings_pre[code]["shares"] += qty
            elif action == "卖出":
                cash_pre += price * qty
                if code in holdings_pre:
                    h = holdings_pre[code]
                    avg = h["total_cost"] / h["shares"] if h["shares"] > 0 else 0
                    h["total_cost"] -= avg * qty
                    h["shares"] -= qty
                    if h["shares"] == 0:
                        h["total_cost"] = 0.0
        
        cash_pre_adj = apply_adjustments(cash_pre, last_pre_day)
        holdings_value_pre = 0
        for code, h in holdings_pre.items():
            if h["shares"] > 0:
                close = close_maps.get(code, {}).get(last_pre_day, 0)
                holdings_value_pre += close * h["shares"]
        prev_total = cash_pre_adj + holdings_value_pre
    else:
        prev_total = INITIAL_CASH
    
    print(f"\n期初总资产（{fmt_date(pre_days[-1]) if pre_days else '初始'}）: ¥{prev_total:,.2f}")
    
    # 现在逐日处理gap期间
    # 需要按交易日顺序处理，每个交易日可能有交易
    results = []
    
    # 重新从头开始追踪，但这次逐日处理
    cash2 = INITIAL_CASH
    holdings2 = {}
    # 先处理到gap前
    for t in trades:
        if t[1] >= first_gap_md:
            break
        seq, date, action, name, code, price, qty = t
        if action in ("挂单", "排板撤销"):
            continue
        if action == "买入":
            cash2 -= price * qty
            if code not in holdings2:
                holdings2[code] = {"name": name, "shares": 0, "total_cost": 0.0}
            holdings2[code]["total_cost"] += price * qty
            holdings2[code]["shares"] += qty
        elif action == "卖出":
            cash2 += price * qty
            if code in holdings2:
                h = holdings2[code]
                avg = h["total_cost"] / h["shares"] if h["shares"] > 0 else 0
                h["total_cost"] -= avg * qty
                h["shares"] -= qty
                if h["shares"] == 0:
                    h["total_cost"] = 0.0
    
    # 按日期分组gap期间的交易
    gap_trades_by_date = defaultdict(list)
    for t in trades:
        md = t[1]
        if first_gap_md <= md <= "07-02":
            gap_trades_by_date[md].append(t)
    
    prev_total_adj = prev_total
    
    for day in gap_days:
        md = fmt_date(day)
        
        # 处理当天的交易
        day_trades = gap_trades_by_date.get(md, [])
        trade_desc_parts = []
        
        for t in day_trades:
            seq, date, action, name, code, price, qty = t
            if action in ("挂单", "排板撤销"):
                if action == "排板撤销":
                    trade_desc_parts.append(f"迪哲排板撤销")
                continue
            if action == "买入":
                cash2 -= price * qty
                if code not in holdings2:
                    holdings2[code] = {"name": name, "shares": 0, "total_cost": 0.0}
                holdings2[code]["total_cost"] += price * qty
                holdings2[code]["shares"] += qty
                trade_desc_parts.append(f"买入{name}")
            elif action == "卖出":
                cash2 += price * qty
                if code in holdings2:
                    h = holdings2[code]
                    avg = h["total_cost"] / h["shares"] if h["shares"] > 0 else 0
                    pnl = price * qty - avg * qty
                    h["total_cost"] -= avg * qty
                    h["shares"] -= qty
                    if h["shares"] == 0:
                        h["total_cost"] = 0.0
                    pnl_pct = pnl / (avg * qty) * 100 if avg > 0 else 0
                    trade_desc_parts.append(f"卖出{name}({pnl:+.0f})")
        
        # 应用偏差修正
        cash2_adj = apply_adjustments(cash2, day)
        
        # 计算持仓市值
        holdings_value = 0
        for code, h in holdings2.items():
            if h["shares"] > 0:
                close = close_maps.get(code, {}).get(day, 0)
                if close == 0:
                    # 尝试最近的价格
                    stock_days = sorted(close_maps.get(code, {}).keys())
                    for sd in reversed(stock_days):
                        if sd <= day:
                            close = close_maps[code][sd]
                            break
                holdings_value += close * h["shares"]
        
        total_assets = cash2_adj + holdings_value
        day_pnl = total_assets - prev_total_adj
        day_pct = day_pnl / prev_total_adj * 100 if prev_total_adj > 0 else 0
        cum_pct = (total_assets - INITIAL_CASH) / INITIAL_CASH * 100
        
        if trade_desc_parts:
            desc = "/".join(trade_desc_parts)
        else:
            desc = "无操作"
        
        results.append({
            "date": md,
            "open_total": prev_total_adj,
            "close_total": total_assets,
            "pnl": day_pnl,
            "pct": day_pct,
            "desc": desc,
            "cum_pct": cum_pct,
        })
        
        prev_total_adj = total_assets
    
    # 输出结果
    print(f"\n{'='*120}")
    print(f"  每日盈亏回溯结果（{fmt_date(gap_days[0])} ~ {fmt_date(gap_days[-1])}）")
    print(f"{'='*120}")
    print(f"{'日期':>8} {'期初总资产':>14} {'期末总资产':>14} {'当日盈亏':>10} {'收益率':>8} {'操作':<30} {'累计收益率':>10}")
    print("-" * 120)
    
    for r in results:
        print(f"{r['date']:>8} {r['open_total']:>14,.2f} {r['close_total']:>14,.2f} {r['pnl']:>+10,.2f} {r['pct']:>+7.2f}% {r['desc']:<30} {r['cum_pct']:>+9.2f}%")
    
    # 输出markdown表格行
    print(f"\n{'='*120}")
    print("Markdown表格行（可直接插入trades.md）:")
    print(f"{'='*120}")
    for r in results:
        pnl_str = f"{r['pnl']:+,.2f}" if r['pnl'] != 0 else "0"
        pnl_pct_str = f"{r['pct']:+.2f}%" if r['pnl'] != 0 else "0.00%"
        print(f"| {r['date']} | {r['open_total']:,.2f} | {r['close_total']:,.2f} | {pnl_str} | {pnl_pct_str} | {r['desc']} | {r['cum_pct']:+.2f}% |")


if __name__ == "__main__":
    main()
