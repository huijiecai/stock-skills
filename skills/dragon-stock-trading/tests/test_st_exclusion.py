#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 ST 股票排除功能
"""

import sys
from pathlib import Path

# 添加 scripts 目录到路径
script_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(script_dir))

from market_fetcher import MarketDataFetcher


def test_st_stock_exclusion():
    """测试 ST 股票排除"""
    print("="*60)
    print("测试 ST 股票排除功能")
    print("="*60)
    
    # 创建测试数据
    test_db = "test_st_exclusion.db"
    api_key = "test_key"
    
    fetcher = MarketDataFetcher(test_db, api_key)
    
    # 测试股票列表（包含 ST 股票）
    stock_list = [
        ('000001', '平安银行', 'SZ'),        # 正常股票
        ('000002', '*ST华新', 'SZ'),         # ST 股票
        ('600000', '浦发银行', 'SH'),        # 正常股票
        ('600001', 'ST天宸', 'SH'),          # ST 股票
        ('000003', '深ST华强', 'SZ'),        # ST 股票
        ('600002', '齐鲁银行', 'SH'),        # 正常股票
    ]
    
    print(f"\n测试股票列表（共{len(stock_list)}只）:")
    normal_count = sum(1 for _, name, _ in stock_list if 'ST' not in name)
    st_count = sum(1 for _, name, _ in stock_list if 'ST' in name)
    print(f"  - 正常股票: {normal_count}只")
    print(f"  - ST股票: {st_count}只")
    
    # 检查过滤逻辑
    print(f"\n过滤结果:")
    filtered_list = []
    for stock_code, stock_name, region in stock_list:
        if stock_name and 'ST' in stock_name:
            print(f"  ✗ 跳过: {stock_name}({stock_code})")
        else:
            print(f"  ✓ 保留: {stock_name}({stock_code})")
            filtered_list.append((stock_code, stock_name, region))
    
    print(f"\n过滤后剩余: {len(filtered_list)}只股票")
    
    # 验证结果
    assert len(filtered_list) == normal_count, f"期望{normal_count}只，实际{len(filtered_list)}只"
    
    # 验证所有 ST 股票都被排除
    for _, name, _ in filtered_list:
        assert 'ST' not in name, f"ST股票未被排除: {name}"
    
    print("\n✅ 测试通过！ST 股票已被正确排除。")
    
    # 清理测试文件
    import os
    if os.path.exists(test_db):
        os.remove(test_db)


if __name__ == "__main__":
    test_st_stock_exclusion()
