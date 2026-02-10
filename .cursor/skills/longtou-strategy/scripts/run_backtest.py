#!/usr/bin/env python3
"""
历史回测脚本

用途：
- 获取最近N天的涨停板数据
- 追踪每只股票的后续表现
- 分析赚钱模式和亏钱模式
- 生成策略优化建议

使用方式：
    python scripts/run_backtest.py --days 30 --sample 100
"""

import sys
import os
import argparse
import json
from datetime import datetime

# 添加模块路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from modules import BacktestEngine, PatternAnalyzer


def run_backtest(days: int = 30, sample_size: int = 100):
    """
    运行回测分析
    
    Args:
        days: 回测天数
        sample_size: 采样数量
    """
    print("="*60)
    print(f"🚀 龙头战法历史回测")
    print("="*60)
    print(f"回测周期：最近 {days} 个交易日")
    print(f"采样数量：{sample_size} 只股票")
    print("="*60)
    
    # 1. 初始化回测引擎
    engine = BacktestEngine(days=days)
    
    # 2. 获取交易日
    trading_days = engine.get_trading_days(days)
    
    # 3. 获取涨停股票数据
    limit_up_data = engine.get_limit_up_stocks_batch(trading_days)
    
    if not limit_up_data:
        print("\n❌ 未能获取到涨停数据，退出")
        return
    
    # 统计涨停股票总数
    total_stocks = sum(len(df) for df in limit_up_data.values())
    print(f"\n📊 涨停股票总数：{total_stocks} 只")
    
    # 4. 计算续板率和后续表现
    backtest_df = engine.calculate_continuation_rate(limit_up_data, sample_size=sample_size)
    
    if backtest_df.empty:
        print("\n❌ 回测数据为空，退出")
        return
    
    # 5. 保存原始数据
    data_dir = os.path.join(parent_dir, "data", "backtest")
    os.makedirs(data_dir, exist_ok=True)
    
    today_str = datetime.now().strftime("%Y%m%d")
    csv_path = os.path.join(data_dir, f"backtest_{today_str}_days{days}.csv")
    backtest_df.to_csv(csv_path, index=False, encoding='utf-8-sig')
    print(f"\n💾 原始数据已保存：{csv_path}")
    
    # 6. 模式分析
    print("\n" + "="*60)
    print("📊 模式分析")
    print("="*60)
    
    analyzer = PatternAnalyzer(backtest_df)
    
    # 时间模式
    time_pattern = analyzer.analyze_time_pattern()
    print("\n### 时间模式分析")
    for category, info in time_pattern.items():
        if info['数量'] > 0:
            print(f"\n**{category}** ({info['定义']})")
            print(f"  样本数：{info['数量']}")
            print(f"  T+1平均收益：{info['T+1平均收益']}")
            print(f"  T+1胜率：{info['T+1胜率']}")
            print(f"  T+3平均收益：{info['T+3平均收益']}")
    
    # 行业模式
    industry_pattern = analyzer.analyze_industry_pattern()
    print("\n### 行业模式分析（TOP10）")
    for i, ind in enumerate(industry_pattern[:10], 1):
        print(f"{i}. {ind['行业']}：")
        print(f"   样本数={ind['样本数']}, "
              f"T+1收益={ind['T+1平均收益']:.2%}, "
              f"胜率={ind['T+1胜率']:.1%}")
    
    # 赚钱模式
    winning_patterns = analyzer.find_winning_patterns(top_n=5)
    print("\n### 🔥 赚钱模式TOP5")
    for i, pattern in enumerate(winning_patterns, 1):
        print(f"\n{i}. **{pattern['模式']}**")
        print(f"   特征：{pattern['特征']}")
        print(f"   样本数：{pattern['样本数']}")
        print(f"   T+1平均收益：{pattern['T+1平均收益']:.2%}")
        print(f"   T+1胜率：{pattern['T+1胜率']:.1%}")
        print(f"   T+3平均收益：{pattern['T+3平均收益']:.2%}")
    
    # 亏钱模式
    losing_patterns = analyzer.find_losing_patterns(top_n=3)
    print("\n### ⚠️  亏钱模式（需要避免）")
    for i, pattern in enumerate(losing_patterns, 1):
        print(f"\n{i}. **{pattern['模式']}**")
        print(f"   特征：{pattern['特征']}")
        print(f"   样本数：{pattern['样本数']}")
        print(f"   T+1平均收益：{pattern['T+1平均收益']:.2%}")
        print(f"   T+1胜率：{pattern['T+1胜率']:.1%}")
        if '风险' in pattern:
            print(f"   ⚠️ {pattern['风险']}")
    
    # 优化建议
    suggestions = analyzer.generate_suggestions()
    print("\n### 💡 策略优化建议")
    for suggestion in suggestions:
        print(f"  {suggestion}")
    
    # 7. 保存分析报告
    report = {
        '回测周期': f"{days}个交易日",
        '采样数量': sample_size,
        '分析股票': len(backtest_df),
        '时间模式': {k: {
            '数量': v['数量'],
            'T+1平均收益': v['T+1平均收益'],
            'T+1胜率': v['T+1胜率']
        } for k, v in time_pattern.items() if v['数量'] > 0},
        '赚钱模式': winning_patterns,
        '亏钱模式': losing_patterns,
        '优化建议': suggestions
    }
    
    report_path = os.path.join(data_dir, f"report_{today_str}_days{days}.json")
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 分析报告已保存：{report_path}")
    
    print("\n" + "="*60)
    print("✅ 回测完成！")
    print("="*60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='龙头战法历史回测')
    parser.add_argument('--days', type=int, default=30, help='回测天数（默认30天）')
    parser.add_argument('--sample', type=int, default=100, help='采样数量（默认100只）')
    
    args = parser.parse_args()
    
    run_backtest(days=args.days, sample_size=args.sample)
