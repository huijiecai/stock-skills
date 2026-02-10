#!/usr/bin/env python3
"""
龙头战法快速测试脚本
用于验证SKILL是否正常工作
"""

import sys
import os

# 添加模块路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_logic_matcher():
    """测试逻辑匹配器"""
    print("\n" + "="*60)
    print("测试1：逻辑匹配器")
    print("="*60)
    
    try:
        from modules import LogicMatcher
        
        matcher = LogicMatcher()
        print(f"✅ 逻辑库加载成功：{len(matcher.get_all_logics())} 个逻辑")
        
        # 测试匹配
        concepts = ["数字货币", "区块链"]
        result = matcher.match_logic(concepts)
        
        if result:
            print(f"✅ 逻辑匹配成功：{result['名称']}")
            print(f"   逻辑强度：{matcher.format_logic_strength(result['逻辑强度'])}")
        else:
            print("⚠️  未匹配到逻辑")
        
        return True
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_data_fetcher():
    """测试数据获取器"""
    print("\n" + "="*60)
    print("测试2：数据获取器")
    print("="*60)
    
    try:
        from modules import DataFetcher
        
        fetcher = DataFetcher()
        print("✅ 数据获取器初始化成功")
        
        # 测试获取涨停股票（可能会失败，因为非交易时间）
        print("\n尝试获取涨停数据（非交易时间可能无数据）...")
        limit_up = fetcher.get_limit_up_stocks()
        
        if not limit_up.empty:
            print(f"✅ 获取成功：{len(limit_up)} 只涨停股票")
        else:
            print("⚠️  无涨停数据（可能非交易时间）")
        
        return True
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


def test_screener():
    """测试筛选器"""
    print("\n" + "="*60)
    print("测试3：筛选器（完整流程）")
    print("="*60)
    
    try:
        from modules import LongtouScreener
        
        screener = LongtouScreener()
        print("✅ 筛选器初始化成功")
        
        print("\n执行筛选（可能需要1-2分钟）...")
        result = screener.screen_stocks(top_n=30, min_logic_strength=4)
        
        if 'error' in result:
            print(f"⚠️  筛选结果：{result['error']}")
        else:
            print(f"✅ 筛选完成")
            print(f"   通过筛选：{len(result['selected_stocks'])} 只")
            print(f"   过滤：{len(result['filtered_stocks'])} 只")
            
            if result['selected_stocks']:
                print("\n重点自选股：")
                for i, stock in enumerate(result['selected_stocks'][:3], 1):
                    print(f"   {i}. {stock['名称']} - {stock['逻辑']} (逻辑强度：{stock['逻辑强度']}星)")
        
        return True
    except Exception as e:
        print(f"❌ 测试失败：{e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n🚀 龙头战法SKILL测试")
    print("="*60)
    
    # 执行测试
    results = []
    results.append(("逻辑匹配器", test_logic_matcher()))
    results.append(("数据获取器", test_data_fetcher()))
    
    # 询问是否执行完整测试
    print("\n" + "="*60)
    print("⚠️  注意：完整筛选测试需要访问网络，可能需要1-2分钟")
    choice = input("是否执行完整筛选测试？(y/n): ").strip().lower()
    
    if choice == 'y':
        results.append(("筛选器", test_screener()))
    
    # 输出测试结果
    print("\n" + "="*60)
    print("测试结果汇总")
    print("="*60)
    
    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{name}: {status}")
    
    all_passed = all(r[1] for r in results)
    
    if all_passed:
        print("\n🎉 所有测试通过！SKILL可以正常使用。")
    else:
        print("\n⚠️  部分测试失败，请检查错误信息。")
