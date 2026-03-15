#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速测试脚本
验证 investment-analysis scripts 的所有功能
"""

import sys
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from realtime_data import get_stock_realtime_data, get_stock_financial_data
from stock_formatter import format_for_analysis


def test_single_stock():
    """测试单个股票数据获取"""
    print("\n" + "="*60)
    print("测试1: 单个股票数据获取")
    print("="*60)
    
    code = '600519'  # 贵州茅台
    print(f"\n获取股票: {code}")
    
    # 获取数据
    realtime = get_stock_realtime_data(code)
    financial = get_stock_financial_data(code)
    
    if realtime:
        print(f"✅ 实时数据获取成功")
        print(f"   名称: {realtime['name']}")
        print(f"   行业: {realtime['industry']}")
        print(f"   PE(TTM): {realtime.get('pe_ttm', 'N/A')}")
        print(f"   市值: {realtime.get('total_mv', 0) / 10000:.2f}亿")
    else:
        print(f"❌ 实时数据获取失败")
        return False
    
    if financial:
        print(f"✅ 财务数据获取成功")
        print(f"   报告期: {financial['period']}")
        print(f"   营收: {financial.get('revenue', 0) / 100000000:.2f}亿")
        print(f"   净利润: {financial.get('net_profit', 0) / 100000000:.2f}亿")
    else:
        print(f"❌ 财务数据获取失败")
    
    return True


def test_format():
    """测试数据格式化"""
    print("\n" + "="*60)
    print("测试2: 数据格式化")
    print("="*60)
    
    code = '000858'  # 五粮液
    print(f"\n获取并格式化: {code}")
    
    realtime = get_stock_realtime_data(code)
    financial = get_stock_financial_data(code)
    
    if realtime:
        markdown = format_for_analysis(realtime, financial)
        print("\n" + "-"*60)
        print(markdown)
        print("-"*60)
        print("✅ 格式化成功")
        return True
    else:
        print("❌ 格式化失败")
        return False


def test_batch():
    """测试批量获取"""
    print("\n" + "="*60)
    print("测试3: 批量获取白酒龙头数据")
    print("="*60)
    
    # 白酒龙头
    stocks = [
        ('600519', '贵州茅台'),
        ('000858', '五粮液'),
        ('000568', '泸州老窖'),
    ]
    
    results = []
    for code, expected_name in stocks:
        print(f"\n获取: {expected_name} ({code})...", end=" ")
        data = get_stock_realtime_data(code)
        if data:
            results.append({
                'name': data['name'],
                'code': code,
                'pe_ttm': data.get('pe_ttm', 'N/A'),
                'pb': data.get('pb', 'N/A'),
                'total_mv': data.get('total_mv', 0) / 10000,
            })
            print(f"✅ {data['name']}")
        else:
            print(f"❌ 失败")
    
    if results:
        print("\n" + "-"*60)
        print(f"{'公司':<12} {'代码':<10} {'PE(TTM)':<10} {'PB':<10} {'市值(亿)':<12}")
        print("-"*60)
        for r in results:
            print(f"{r['name']:<12} {r['code']:<10} {r['pe_ttm']:<10} {r['pb']:<10} {r['total_mv']:<12.2f}")
        print("-"*60)
        print(f"✅ 批量获取成功 ({len(results)}/{len(stocks)})")
        return True
    else:
        print("❌ 批量获取失败")
        return False


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("Investment Analysis Scripts 完整测试")
    print("="*60)
    
    tests = [
        ("单股数据获取", test_single_stock),
        ("数据格式化", test_format),
        ("批量获取", test_batch),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n❌ {name} 测试异常: {e}")
            results.append((name, False))
    
    # 汇总结果
    print("\n" + "="*60)
    print("测试汇总")
    print("="*60)
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{name:<20} {status}")
    
    print("-"*60)
    print(f"总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️ 有 {total - passed} 个测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
