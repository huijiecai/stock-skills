#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据格式化工具
将实时数据格式化为适合分析的文本格式
"""

from typing import Dict, Optional
from datetime import datetime


def format_for_analysis(realtime_data: Dict, financial_data: Optional[Dict] = None) -> str:
    """
    将实时数据和财务数据格式化为易读的文本
    
    Args:
        realtime_data: 实时数据字典
        financial_data: 财务数据字典（可选）
        
    Returns:
        格式化后的文本
    """
    if not realtime_data:
        return "无数据"
    
    lines = []
    
    # 基本信息
    lines.append("# 股票基本信息")
    lines.append("")
    lines.append(f"**股票名称**: {realtime_data.get('name', 'N/A')}")
    lines.append(f"**股票代码**: {realtime_data.get('code', 'N/A')}")
    lines.append(f"**所属行业**: {realtime_data.get('industry', 'N/A')}")
    lines.append(f"**上市地点**: {realtime_data.get('market', 'N/A')}")
    lines.append(f"**上市日期**: {_format_date(realtime_data.get('list_date'))}")
    lines.append("")
    
    # 最新行情
    if realtime_data.get('close'):
        lines.append("## 最新行情")
        lines.append("")
        lines.append(f"**交易日期**: {_format_date(realtime_data.get('trade_date'))}")
        lines.append(f"**收盘价**: ¥{realtime_data.get('close', 0):.2f}")
        
        pct_chg = realtime_data.get('pct_chg', 0)
        change_symbol = "📈" if pct_chg > 0 else "📉" if pct_chg < 0 else "➡️"
        lines.append(f"**涨跌幅**: {change_symbol} {pct_chg:+.2f}%")
        
        if realtime_data.get('volume'):
            volume_yi = realtime_data['volume'] / 100  # 手转为万股，再转为亿股
            lines.append(f"**成交量**: {volume_yi:.2f}亿股")
        
        if realtime_data.get('amount'):
            amount_yi = realtime_data['amount'] / 10000  # 千元转为亿元
            lines.append(f"**成交额**: ¥{amount_yi:.2f}亿")
        
        lines.append("")
    
    # 估值指标
    if realtime_data.get('pe_ttm') or realtime_data.get('pb'):
        lines.append("## 估值指标")
        lines.append("")
        
        if realtime_data.get('pe_ttm'):
            lines.append(f"**市盈率(TTM)**: {realtime_data['pe_ttm']:.2f}")
        
        if realtime_data.get('pb'):
            lines.append(f"**市净率**: {realtime_data['pb']:.2f}")
        
        if realtime_data.get('ps_ttm'):
            lines.append(f"**市销率(TTM)**: {realtime_data['ps_ttm']:.2f}")
        
        if realtime_data.get('total_mv'):
            total_mv_yi = realtime_data['total_mv'] / 10000  # 万元转为亿元
            lines.append(f"**总市值**: ¥{total_mv_yi:.2f}亿")
        
        if realtime_data.get('circ_mv'):
            circ_mv_yi = realtime_data['circ_mv'] / 10000
            lines.append(f"**流通市值**: ¥{circ_mv_yi:.2f}亿")
        
        lines.append("")
    
    # 财务数据
    if financial_data:
        lines.append("## 财务数据")
        lines.append("")
        lines.append(f"**报告期**: {_format_date(financial_data.get('period'))}")
        
        if financial_data.get('revenue'):
            revenue_yi = financial_data['revenue'] / 100000000  # 元转为亿元
            lines.append(f"**营业收入**: ¥{revenue_yi:.2f}亿")
        
        if financial_data.get('operate_profit'):
            profit_yi = financial_data['operate_profit'] / 100000000
            lines.append(f"**营业利润**: ¥{profit_yi:.2f}亿")
        
        if financial_data.get('net_profit'):
            net_profit_yi = financial_data['net_profit'] / 100000000
            lines.append(f"**归母净利润**: ¥{net_profit_yi:.2f}亿")
            
            # 计算净利率
            if financial_data.get('revenue') and financial_data['revenue'] > 0:
                net_margin = (financial_data['net_profit'] / financial_data['revenue']) * 100
                lines.append(f"**净利率**: {net_margin:.2f}%")
        
        if financial_data.get('total_assets'):
            assets_yi = financial_data['total_assets'] / 100000000
            lines.append(f"**总资产**: ¥{assets_yi:.2f}亿")
        
        if financial_data.get('total_liab'):
            liab_yi = financial_data['total_liab'] / 100000000
            lines.append(f"**总负债**: ¥{liab_yi:.2f}亿")
            
            # 计算资产负债率
            if financial_data.get('total_assets') and financial_data['total_assets'] > 0:
                debt_ratio = (financial_data['total_liab'] / financial_data['total_assets']) * 100
                lines.append(f"**资产负债率**: {debt_ratio:.2f}%")
        
        if financial_data.get('cashflow_operating'):
            cashflow_yi = financial_data['cashflow_operating'] / 100000000
            lines.append(f"**经营现金流**: ¥{cashflow_yi:.2f}亿")
        
        lines.append("")
    
    # 数据来源说明
    lines.append("---")
    lines.append(f"*数据来源: Tushare Pro | 获取时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    
    return "\n".join(lines)


def _format_date(date_str) -> str:
    """
    格式化日期字符串
    
    Args:
        date_str: 日期字符串（如 20231231）
        
    Returns:
        格式化后的日期（如 2023-12-31）
    """
    if not date_str:
        return "N/A"
    
    date_str = str(date_str)
    if len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str


def main():
    """测试格式化"""
    # 模拟数据
    realtime_data = {
        'name': '贵州茅台',
        'code': '600519',
        'industry': '白酒',
        'market': '主板',
        'list_date': '20010827',
        'trade_date': '20260315',
        'close': 1680.50,
        'change': 25.30,
        'pct_chg': 1.53,
        'volume': 125000,  # 手
        'amount': 2100000,  # 千元
        'pe_ttm': 38.5,
        'pb': 9.2,
        'ps_ttm': 15.3,
        'total_mv': 21100000,  # 万元
        'circ_mv': 21100000,
    }
    
    financial_data = {
        'period': '20231231',
        'revenue': 151500000000,  # 元
        'operate_profit': 78500000000,
        'net_profit': 62700000000,
        'total_assets': 228500000000,
        'total_liab': 23200000000,
        'cashflow_operating': 68500000000,
    }
    
    print(format_for_analysis(realtime_data, financial_data))


if __name__ == "__main__":
    main()
