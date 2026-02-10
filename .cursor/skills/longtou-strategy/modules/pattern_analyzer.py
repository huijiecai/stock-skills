"""
模式分析器模块
负责挖掘历史数据中的赚钱模式
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from collections import defaultdict


class PatternAnalyzer:
    """模式分析器"""
    
    def __init__(self, backtest_data: pd.DataFrame):
        """
        初始化分析器
        
        Args:
            backtest_data: 回测数据（包含股票及其后续表现）
        """
        self.data = backtest_data
        
    def analyze_time_pattern(self) -> Dict:
        """
        分析涨停时间模式
        
        Returns:
            Dict: 不同时间段的统计数据
        """
        print("\n📊 分析涨停时间模式...")
        
        result = {
            '早盘涨停': {'定义': '9:30-10:00', '数据': []},
            '上午涨停': {'定义': '10:00-11:30', '数据': []},
            '午后涨停': {'定义': '13:00-14:00', '数据': []},
            '尾盘涨停': {'定义': '14:00-15:00', '数据': []}
        }
        
        for _, row in self.data.iterrows():
            time_str = str(row.get('首板时间', '14:00'))
            
            try:
                # 解析时间
                time_parts = time_str.split(':')
                hour = int(time_parts[0])
                minute = int(time_parts[1]) if len(time_parts) > 1 else 0
                time_int = hour * 100 + minute
                
                # 分类
                if 930 <= time_int < 1000:
                    category = '早盘涨停'
                elif 1000 <= time_int < 1130:
                    category = '上午涨停'
                elif 1300 <= time_int < 1400:
                    category = '午后涨停'
                else:
                    category = '尾盘涨停'
                
                result[category]['数据'].append({
                    'T+1': row.get('T+1', 0),
                    'T+2': row.get('T+2', 0),
                    'T+3': row.get('T+3', 0),
                    'max_gain': row.get('max_gain', 0)
                })
                
            except:
                continue
        
        # 计算统计指标
        for category, info in result.items():
            data = info['数据']
            if data:
                df = pd.DataFrame(data)
                info['数量'] = len(data)
                info['T+1平均收益'] = f"{df['T+1'].mean():.2%}"
                info['T+1胜率'] = f"{(df['T+1'] > 0).sum() / len(df):.1%}"
                info['T+3平均收益'] = f"{df['T+3'].mean():.2%}"
                info['最大收益'] = f"{df['max_gain'].mean():.2%}"
            else:
                info['数量'] = 0
                info['T+1平均收益'] = "N/A"
                info['T+1胜率'] = "N/A"
        
        return result
    
    def analyze_industry_pattern(self) -> List[Dict]:
        """
        分析行业/板块模式
        
        Returns:
            List[Dict]: 按收益率排序的行业数据
        """
        print("\n📊 分析行业/板块模式...")
        
        industry_stats = defaultdict(lambda: {
            'count': 0,
            't1_returns': [],
            't3_returns': [],
            'max_gains': []
        })
        
        for _, row in self.data.iterrows():
            industry = row.get('所属行业', '未知')
            if industry and industry != '未知':
                stats = industry_stats[industry]
                stats['count'] += 1
                stats['t1_returns'].append(row.get('T+1', 0))
                stats['t3_returns'].append(row.get('T+3', 0))
                stats['max_gains'].append(row.get('max_gain', 0))
        
        # 计算平均值并排序
        result = []
        for industry, stats in industry_stats.items():
            if stats['count'] >= 3:  # 至少3个样本
                result.append({
                    '行业': industry,
                    '样本数': stats['count'],
                    'T+1平均收益': np.mean(stats['t1_returns']),
                    'T+1胜率': sum(1 for x in stats['t1_returns'] if x > 0) / len(stats['t1_returns']),
                    'T+3平均收益': np.mean(stats['t3_returns']),
                    '最大收益': np.mean(stats['max_gains'])
                })
        
        # 按T+1收益率排序
        result = sorted(result, key=lambda x: x['T+1平均收益'], reverse=True)
        
        return result
    
    def find_winning_patterns(self, top_n: int = 5) -> List[Dict]:
        """
        发现赚钱模式
        
        Args:
            top_n: 返回前N个最佳模式
            
        Returns:
            List[Dict]: 赚钱模式列表
        """
        print(f"\n🔍 挖掘TOP{top_n}赚钱模式...")
        
        patterns = []
        
        # 模式1: 早盘涨停 + 特定行业
        early_limit = self.data[
            self.data['首板时间'].str.contains('09:|10:0', na=False)
        ]
        if not early_limit.empty:
            patterns.append({
                '模式': '早盘涨停',
                '特征': '9:30-10:00涨停',
                '样本数': len(early_limit),
                'T+1平均收益': early_limit['T+1'].mean(),
                'T+1胜率': (early_limit['T+1'] > 0).sum() / len(early_limit),
                'T+3平均收益': early_limit['T+3'].mean()
            })
        
        # 模式2: 特定行业
        industry_data = self.analyze_industry_pattern()
        for ind in industry_data[:3]:  # 取前3个行业
            patterns.append({
                '模式': f"{ind['行业']}板块",
                '特征': f"{ind['行业']}相关股票",
                '样本数': ind['样本数'],
                'T+1平均收益': ind['T+1平均收益'],
                'T+1胜率': ind['T+1胜率'],
                'T+3平均收益': ind['T+3平均收益']
            })
        
        # 按T+1收益率排序
        patterns = sorted(patterns, key=lambda x: x['T+1平均收益'], reverse=True)
        
        return patterns[:top_n]
    
    def find_losing_patterns(self, top_n: int = 3) -> List[Dict]:
        """
        发现亏钱模式（需要避免的）
        
        Args:
            top_n: 返回前N个最差模式
            
        Returns:
            List[Dict]: 亏钱模式列表
        """
        print(f"\n⚠️  挖掘TOP{top_n}亏钱模式...")
        
        patterns = []
        
        # 模式1: 尾盘涨停
        late_limit = self.data[
            self.data['首板时间'].str.contains('14:|15:', na=False)
        ]
        if not late_limit.empty and len(late_limit) >= 5:
            patterns.append({
                '模式': '尾盘涨停',
                '特征': '14:00后涨停',
                '样本数': len(late_limit),
                'T+1平均收益': late_limit['T+1'].mean(),
                'T+1胜率': (late_limit['T+1'] > 0).sum() / len(late_limit),
                '风险': '续板率低，容易高开低走'
            })
        
        # 模式2: 收益率最差的行业
        industry_data = self.analyze_industry_pattern()
        for ind in industry_data[-2:]:  # 取最后2个行业
            if ind['T+1平均收益'] < 0:
                patterns.append({
                    '模式': f"{ind['行业']}板块",
                    '特征': f"{ind['行业']}相关股票",
                    '样本数': ind['样本数'],
                    'T+1平均收益': ind['T+1平均收益'],
                    'T+1胜率': ind['T+1胜率'],
                    '风险': '板块退潮，无赚钱效应'
                })
        
        # 按T+1收益率排序（从低到高）
        patterns = sorted(patterns, key=lambda x: x['T+1平均收益'])
        
        return patterns[:top_n]
    
    def generate_suggestions(self) -> List[str]:
        """
        生成策略优化建议
        
        Returns:
            List[str]: 建议列表
        """
        print("\n💡 生成优化建议...")
        
        suggestions = []
        
        # 分析时间模式
        time_pattern = self.analyze_time_pattern()
        early = time_pattern.get('早盘涨停', {})
        late = time_pattern.get('尾盘涨停', {})
        
        if early.get('数量', 0) > 0 and late.get('数量', 0) > 0:
            early_return = float(early['T+1平均收益'].strip('%')) if early['T+1平均收益'] != 'N/A' else 0
            late_return = float(late['T+1平均收益'].strip('%')) if late['T+1平均收益'] != 'N/A' else 0
            
            if early_return > late_return + 2:
                suggestions.append(
                    f"✅ 提高'早盘涨停'权重（+20分）：早盘涨停收益率{early['T+1平均收益']}，"
                    f"明显优于尾盘涨停{late['T+1平均收益']}"
                )
            
            if late_return < 0:
                suggestions.append(
                    f"⚠️ 降低'尾盘涨停'权重（-30分）：尾盘涨停平均收益{late['T+1平均收益']}，风险较大"
                )
        
        # 分析行业模式
        industry_data = self.analyze_industry_pattern()
        if industry_data:
            # 推荐最佳行业
            top_industry = industry_data[0]
            if top_industry['T+1平均收益'] > 0.03:
                suggestions.append(
                    f"🔥 重点关注'{top_industry['行业']}'板块：T+1平均收益{top_industry['T+1平均收益']:.2%}，"
                    f"胜率{top_industry['T+1胜率']:.1%}"
                )
            
            # 警告最差行业
            worst_industry = industry_data[-1]
            if worst_industry['T+1平均收益'] < -0.01:
                suggestions.append(
                    f"🗑️ 建议移除'{worst_industry['行业']}'逻辑：T+1平均收益{worst_industry['T+1平均收益']:.2%}，"
                    f"无赚钱效应"
                )
        
        if not suggestions:
            suggestions.append("✅ 当前策略整体表现良好，继续观察")
        
        return suggestions


if __name__ == "__main__":
    # 测试代码
    print("模式分析器模块已加载")
    print("需要配合 BacktestEngine 使用")
