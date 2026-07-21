#!/usr/bin/env python3
"""
账户逐笔精算脚本（自动解析trades.md）
- 从trades.md表格自动解析全部交易记录，无需手动维护交易列表
- 逐笔计算现金、持仓均价、已实现盈亏
- 支持偏差修正（历史遗留）
- 输出关键节点总资产回溯

用法：
  python3 scripts/audit_account.py                  # 默认7/13收盘价
  python3 scripts/audit_account.py --close 002185=24.13  # 指定收盘价
  python3 scripts/audit_account.py --date 0709       # 计算到指定日期为止
  python3 scripts/audit_account.py --trades-file replay.md \
    --opening-cash 37640.40 \
    --opening-holding=000829:天音控股:1400:9.02 \
    --opening-realized=18263.40 --no-adjustments
"""

import re
import sys
import os
from pathlib import Path

INITIAL_CASH = 100000.0
TRADES_FILE = Path(__file__).resolve().parent.parent / "data" / "trades.md"

# 历史遗留偏差修正（6/30审计发现）
# 1. 05-22 博迁实际买入价153.30（记录153.00，多花¥30）
# 2. 06-01 一笔¥3,699未记录交易（假设为支出）
ADJUSTMENTS = {
    "博迁买入价差": -30.0,
    "06-01未记录交易": -3699.0,
}


def parse_trades_md(filepath):
    """从trades.md解析全部交易记录"""
    content = filepath.read_text(encoding="utf-8")
    
    # 匹配表格行：| # | 日期 | 操作 | 名称 | 代码 | 价格 | 数量 | 金额 | 持仓均价 | 盈亏 | 理由 |
    pattern = re.compile(
        r'\|\s*(\d+)\s*\|\s*(\d{2}-\d{2})\s*\|\s*(买入|卖出|挂单)\s*\|\s*(\S+)\s*\|\s*(\d{6})\s*\|\s*([\d.]+)\s*\|\s*(\d+)\s*\|'
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


def run_audit(
    close_prices=None,
    cutoff_date=None,
    trades_file=TRADES_FILE,
    opening_cash=INITIAL_CASH,
    opening_holdings=None,
    opening_realized_pnl=0.0,
    adjustments=None,
):
    """
    逐笔精算
    close_prices: {code: price} 收盘价字典
    cutoff_date: "MM-DD" 截止日期（只处理到该日期为止的交易）
    """
    if close_prices is None:
        close_prices = {"002185": 24.13}  # 默认7/13收盘
    
    trades = parse_trades_md(trades_file)
    
    if cutoff_date:
        trades = [t for t in trades if t[1] <= cutoff_date]
    
    cash = opening_cash
    holdings = {
        code: dict(holding) for code, holding in (opening_holdings or {}).items()
    }
    realized_pnl = opening_realized_pnl
    realized_pnl_by_stock = {}  # code -> [(date, name, qty, price, avg_before, pnl)]
    
    # 记录关键节点
    snapshots = {}
    
    print("=" * 130)
    print(f"  开始现金: ¥{opening_cash:,.2f}")
    print(f"  交易记录: {trades_file}")
    print(f"  交易笔数: {len(trades)}")
    print("=" * 130)
    header = f"{'#':>3} {'日期':>6} {'操作':>4} {'名称':>8} {'代码':>8} {'价格':>10} {'数量':>6} {'金额':>12} {'现金余额':>14} {'持仓均价':>10} {'本次盈亏':>12}"
    print(header)
    print("-" * 130)
    
    for t in trades:
        seq, date, action, name, code, price, qty = t
        
        if action == "挂单":
            print(f"{seq:>3} {date:>6} {'挂单':>4} {name:>8} {code:>8} {price:>10.2f} {qty:>6} {'—':>12} {'(未成交)':>14} {'—':>10} {'—':>12}")
            continue
        
        if action == "买入":
            amount = -price * qty
            cash += amount
            if code not in holdings:
                holdings[code] = {"name": name, "shares": 0, "total_cost": 0.0}
            h = holdings[code]
            h["total_cost"] += price * qty
            h["shares"] += qty
            avg = h["total_cost"] / h["shares"] if h["shares"] > 0 else 0
            print(f"{seq:>3} {date:>6} {action:>4} {name:>8} {code:>8} {price:>10.2f} {qty:>6} {amount:>12.2f} {cash:>14.2f} {avg:>10.2f} {'—':>12}")
        
        elif action == "卖出":
            amount = price * qty
            cash += amount
            h = holdings[code]
            avg_before = h["total_cost"] / h["shares"]
            cost_portion = avg_before * qty
            pnl = amount - cost_portion
            realized_pnl += pnl
            if code not in realized_pnl_by_stock:
                realized_pnl_by_stock[code] = []
            realized_pnl_by_stock[code].append((date, name, qty, price, avg_before, pnl))
            
            h["total_cost"] -= cost_portion
            h["shares"] -= qty
            if h["shares"] == 0:
                h["total_cost"] = 0.0
                avg_after = 0
            else:
                avg_after = h["total_cost"] / h["shares"]
            print(f"{seq:>3} {date:>6} {action:>4} {name:>8} {code:>8} {price:>10.2f} {qty:>6} {amount:>+12.2f} {cash:>14.2f} {avg_after:>10.2f} {pnl:>+12.2f}")
        
        # 记录关键日期快照
        if date in ("07-09", "07-10", "07-13") and seq == trades[-1][0] or \
           (date == "07-09" and seq == 39) or \
           (date == "07-10" and seq == 42) or \
           (date == "07-13" and seq == 43):
            snapshots[date] = {"cash": cash, "holdings": {c: dict(h) for c, h in holdings.items() if h["shares"] > 0}}
    
    print("-" * 130)
    
    # === 未修正结果 ===
    print(f"\n{'=' * 130}")
    print(f"  按记录价格计算（未修正偏差）")
    print(f"{'=' * 130}")
    print(f"  现金余额:     ¥{cash:,.2f}")
    print(f"  已实现盈亏:   ¥{realized_pnl:,.2f}")
    
    # 当前持仓
    print(f"\n  当前持仓:")
    for code, h in holdings.items():
        if h["shares"] > 0:
            avg = h["total_cost"] / h["shares"]
            print(f"    {h['name']}({code}): {h['shares']}股, 均价¥{avg:.2f}, 总成本¥{h['total_cost']:,.2f}")
    
    # 逐股票已实现盈亏
    print(f"\n  逐股票已实现盈亏:")
    for code, pnls in realized_pnl_by_stock.items():
        name = pnls[0][1]
        total_pnl = sum(p[5] for p in pnls)
        print(f"    {name}({code}): ¥{total_pnl:+,.2f}")
        for p in pnls:
            print(f"      {p[0]}: 卖{p[2]}股@{p[3]:.2f}(均价{p[4]:.2f}) = ¥{p[5]:+,.2f}")
    
    # === 偏差修正 ===
    print(f"\n{'=' * 130}")
    print(f"  偏差修正（6/30审计发现的历史遗留）")
    print(f"{'=' * 130}")
    adj_total = 0
    applied_adjustments = ADJUSTMENTS if adjustments is None else adjustments
    for desc, amount in applied_adjustments.items():
        cash += amount
        adj_total += amount
        print(f"  {desc}: ¥{amount:+,.2f} → 修正后现金: ¥{cash:,.2f}")
    print(f"  偏差修正合计: ¥{adj_total:+,.2f}")
    
    # === 最终结果 ===
    print(f"\n{'=' * 130}")
    print(f"  最终结果")
    print(f"{'=' * 130}")
    print(f"  修正后现金:   ¥{cash:,.2f}")
    
    holdings_value = 0
    for code, h in holdings.items():
        if h["shares"] > 0:
            close = close_prices.get(code, 0)
            if close == 0:
                print(f"  ⚠️ {h['name']}({code}) 无收盘价，请用 --close {code}=XX.XX 指定")
                continue
            mv = close * h["shares"]
            holdings_value += mv
            unrealized = mv - h["total_cost"]
            avg = h["total_cost"] / h["shares"]
            print(f"  {h['name']}({code}): {h['shares']}股 × ¥{close} = ¥{mv:,.2f} (均价¥{avg:.2f}, 浮盈¥{unrealized:+,.2f})")
    
    total_assets = cash + holdings_value
    total_profit = total_assets - INITIAL_CASH
    profit_pct = total_profit / INITIAL_CASH * 100
    
    print(f"\n  持仓市值:     ¥{holdings_value:,.2f}")
    print(f"  总资产:       ¥{total_assets:,.2f}")
    print(f"  累计盈亏:     ¥{total_profit:+,.2f} ({profit_pct:+.2f}%)")
    print(f"  已实现盈亏:   ¥{realized_pnl + adj_total:+,.2f} (逐笔¥{realized_pnl:,.2f} + 偏差修正¥{adj_total:+,.2f})")
    
    # === 关键节点回溯 ===
    print(f"\n{'=' * 130}")
    print(f"  关键节点回溯")
    print(f"{'=' * 130}")
    
    close_map = {
        "07-09": {"002185": 23.73, "000938": 35.44},
        "07-10": {"002185": 25.31},
        "07-13": {"002185": 24.13},
    }
    
    # 重新跑一遍，在每个目标日期的最后一笔交易后记录快照
    cash2 = opening_cash
    holdings2 = {
        code: dict(holding) for code, holding in (opening_holdings or {}).items()
    }
    # 记录每个日期最后一笔交易的序号
    last_trade_per_date = {}
    for t in trades:
        seq, date = t[0], t[1]
        if t[2] != "挂单":
            last_trade_per_date[date] = seq
    
    for t in trades:
        seq, date, action, name, code, price, qty = t
        if action == "挂单":
            continue
        if action == "买入":
            cash2 -= price * qty
            if code not in holdings2:
                holdings2[code] = {"name": name, "shares": 0, "total_cost": 0.0}
            holdings2[code]["total_cost"] += price * qty
            holdings2[code]["shares"] += qty
        elif action == "卖出":
            cash2 += price * qty
            h = holdings2[code]
            cost_portion = (h["total_cost"] / h["shares"]) * qty
            h["total_cost"] -= cost_portion
            h["shares"] -= qty
            if h["shares"] == 0:
                h["total_cost"] = 0
        
        # 该日期最后一笔交易后记录快照
        if date in close_map and last_trade_per_date.get(date) == seq:
            cm = close_map[date]
            mv = sum(cm.get(c, 0) * h["shares"] for c, h in holdings2.items() if h["shares"] > 0)
            # 偏差修正：05-22博迁价差-30, 06-01未记录-3699
            adj = 0
            if date >= "05-22":
                adj -= 30.0
            if date >= "06-01":
                adj -= 3699.0
            cash2_adj = cash2 + adj
            print(f"  {date}收盘: 现金¥{cash2:,.2f}(修正后¥{cash2_adj:,.2f}) + 持仓¥{mv:,.2f} = 总资产¥{cash2_adj+mv:,.2f}")
    
    print(f"\n{'=' * 130}")
    
    return {
        "cash": cash,
        "holdings_value": holdings_value,
        "total_assets": total_assets,
        "total_profit": total_profit,
        "realized_pnl": realized_pnl + adj_total,
    }


if __name__ == "__main__":
    close_prices = {"002185": 24.13}
    cutoff_date = None
    trades_file = TRADES_FILE
    opening_cash = INITIAL_CASH
    opening_holdings = {}
    opening_realized_pnl = 0.0
    adjustments = None
    
    # 解析命令行参数
    args = iter(sys.argv[1:])
    for arg in args:
        if arg.startswith("--close="):
            # --close=002185=24.13,000938=35.44
            close_prices = {}
            for pair in arg[8:].split(","):
                code, price = pair.split("=")
                close_prices[code] = float(price)
        elif arg == "--close":
            close_prices = {}
            for pair in next(args).split(","):
                code, price = pair.split("=")
                close_prices[code] = float(price)
        elif arg.startswith("--date="):
            cutoff_date = arg[7:]
        elif arg == "--date":
            cutoff_date = next(args)
        elif arg.startswith("--trades-file="):
            trades_file = Path(arg[14:]).resolve()
        elif arg == "--trades-file":
            trades_file = Path(next(args)).resolve()
        elif arg.startswith("--opening-cash="):
            opening_cash = float(arg[15:])
        elif arg == "--opening-cash":
            opening_cash = float(next(args))
        elif arg.startswith("--opening-holding="):
            raw_holding = arg[18:]
            code, name, shares, avg = raw_holding.split(":")
            opening_holdings[code] = {
                "name": name,
                "shares": int(shares),
                "total_cost": int(shares) * float(avg),
            }
        elif arg == "--opening-holding":
            code, name, shares, avg = next(args).split(":")
            opening_holdings[code] = {
                "name": name,
                "shares": int(shares),
                "total_cost": int(shares) * float(avg),
            }
        elif arg.startswith("--opening-realized="):
            opening_realized_pnl = float(arg[19:])
        elif arg == "--opening-realized":
            opening_realized_pnl = float(next(args))
        elif arg == "--no-adjustments":
            adjustments = {}

    if cutoff_date and len(cutoff_date) == 4 and cutoff_date.isdigit():
        cutoff_date = f"{cutoff_date[:2]}-{cutoff_date[2:]}"
    
    run_audit(
        close_prices=close_prices,
        cutoff_date=cutoff_date,
        trades_file=trades_file,
        opening_cash=opening_cash,
        opening_holdings=opening_holdings,
        opening_realized_pnl=opening_realized_pnl,
        adjustments=adjustments,
    )
