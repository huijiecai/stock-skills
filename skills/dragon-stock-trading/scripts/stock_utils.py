#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票工具函数 - 统一的股票相关判断逻辑

提供股票代码相关的公共判断函数，确保各脚本逻辑一致
"""


def get_board_type(code: str) -> str:
    """
    根据股票代码判断板块类型
    
    Args:
        code: 股票代码（6位数字）
        
    Returns:
        板块类型：主板/创业板/科创板/北交所
    """
    if code.startswith('688'):
        return '科创板'
    elif code.startswith('300') or code.startswith('301'):
        return '创业板'
    elif code.startswith('8') or code.startswith('4'):
        return '北交所'
    else:
        return '主板'


def get_market(code: str) -> str:
    """
    根据股票代码判断市场
    
    Args:
        code: 股票代码（6位数字）
        
    Returns:
        市场代码：SH/SZ
    """
    if code.startswith(('6', '5')):
        return 'SH'
    else:
        return 'SZ'


def get_ts_code(code: str) -> str:
    """
    根据股票代码生成 Tushare 格式的代码
    
    Args:
        code: 股票代码（6位数字）
        
    Returns:
        Tushare 格式代码：如 000001.SZ
    """
    return f"{code}.{get_market(code)}"


def get_limit_rate(code: str) -> float:
    """
    根据股票代码获取涨跌停幅度
    
    Args:
        code: 股票代码（6位数字）
        
    Returns:
        涨跌停幅度：0.10/0.20/0.30
    """
    if code.startswith('688') or code.startswith('300') or code.startswith('301'):
        return 0.20  # 科创板/创业板
    elif code.startswith('8') or code.startswith('4'):
        return 0.30  # 北交所
    else:
        return 0.10  # 主板


def get_limit_prices(pre_close: float, code: str) -> tuple:
    """
    根据昨收价和股票代码计算涨跌停价格
    
    Args:
        pre_close: 昨收价
        code: 股票代码
        
    Returns:
        (涨停价, 跌停价)
    """
    limit_rate = get_limit_rate(code)
    limit_up = round(pre_close * (1 + limit_rate), 2)
    limit_down = round(pre_close * (1 - limit_rate), 2)
    return limit_up, limit_down


def is_limit_up(close: float, pre_close: float, code: str, tolerance: float = 0.01) -> bool:
    """
    判断是否涨停
    
    Args:
        close: 收盘价
        pre_close: 昨收价
        code: 股票代码
        tolerance: 容差（默认0.01元）
        
    Returns:
        是否涨停
    """
    if pre_close <= 0:
        return False
    limit_up, _ = get_limit_prices(pre_close, code)
    return close >= limit_up - tolerance


def is_limit_down(close: float, pre_close: float, code: str, tolerance: float = 0.01) -> bool:
    """
    判断是否跌停
    
    Args:
        close: 收盘价
        pre_close: 昨收价
        code: 股票代码
        tolerance: 容差（默认0.01元）
        
    Returns:
        是否跌停
    """
    if pre_close <= 0:
        return False
    _, limit_down = get_limit_prices(pre_close, code)
    return close <= limit_down + tolerance
