"""
市场热点分析模块
负责分析当前市场炒作热点，自动生成逻辑库建议
"""

import pandas as pd
from typing import Dict, List, Tuple
from collections import Counter
from .data_fetcher import DataFetcher


class MarketHotspotAnalyzer:
    """市场热点分析器"""
    
    def __init__(self):
        self.fetcher = DataFetcher()
    
    def analyze_board_distribution(self, limit_up_df: pd.DataFrame, continuous_df: pd.DataFrame) -> Dict:
        """
        分析板块分布，找出集中涨停的板块
        
        Args:
            limit_up_df: 涨停股票DataFrame
            continuous_df: 连板股票DataFrame
            
        Returns:
            Dict: 板块分析结果
        """
        print("\n【分析板块分布】")
        
        board_stats = {}
        
        # 统计连板股票的板块分布
        if not continuous_df.empty and '所属行业' in continuous_df.columns and '连板数' in continuous_df.columns:
            for _, row in continuous_df.iterrows():
                board = row.get('所属行业', '未知')
                lianban = int(row.get('连板数', 1))
                name = row.get('名称', '')
                
                if board not in board_stats:
                    board_stats[board] = {
                        '股票数量': 0,
                        '最高连板': 0,
                        '平均连板': 0,
                        '总连板': 0,
                        '股票列表': []
                    }
                
                board_stats[board]['股票数量'] += 1
                board_stats[board]['总连板'] += lianban
                board_stats[board]['最高连板'] = max(board_stats[board]['最高连板'], lianban)
                board_stats[board]['股票列表'].append({'名称': name, '连板': lianban})
        
        # 计算平均连板数
        for board in board_stats:
            avg = board_stats[board]['总连板'] / board_stats[board]['股票数量']
            board_stats[board]['平均连板'] = round(avg, 1)
        
        # 按股票数量排序
        sorted_boards = sorted(
            board_stats.items(), 
            key=lambda x: (x[1]['股票数量'], x[1]['最高连板']), 
            reverse=True
        )
        
        print(f"发现 {len(sorted_boards)} 个活跃板块")
        print("\n板块热度TOP10：")
        for i, (board, stats) in enumerate(sorted_boards[:10], 1):
            print(f"  {i}. {board}: {stats['股票数量']}只 | "
                  f"最高{stats['最高连板']}板 | 平均{stats['平均连板']}板")
        
        return {
            '板块统计': dict(sorted_boards[:10]),
            '总板块数': len(sorted_boards)
        }
    
    def analyze_concept_distribution(self, codes: List[str]) -> Dict:
        """
        分析概念分布，找出热门概念
        
        Args:
            codes: 股票代码列表
            
        Returns:
            Dict: 概念分析结果
        """
        print("\n【分析概念分布】")
        print(f"分析 {len(codes)} 只股票的概念...")
        
        concept_counter = Counter()
        stock_concepts = {}
        
        for i, code in enumerate(codes[:20], 1):  # 只分析前20只，避免太慢
            print(f"  {i}/{min(20, len(codes))} {code}...", end='')
            concepts = self.fetcher.get_stock_board_concept(code)
            
            if concepts:
                print(f" ✓ {len(concepts)}个概念")
                stock_concepts[code] = concepts
                concept_counter.update(concepts)
            else:
                print(" ✗")
        
        # 统计高频概念
        top_concepts = concept_counter.most_common(15)
        
        print(f"\n概念热度TOP15：")
        for i, (concept, count) in enumerate(top_concepts, 1):
            print(f"  {i}. {concept}: {count}只股票")
        
        return {
            '概念统计': dict(top_concepts),
            '股票概念映射': stock_concepts
        }
    
    def find_logic_leader(self, board: str, continuous_df: pd.DataFrame) -> Tuple[str, str]:
        """
        找出板块的龙头股票
        
        Args:
            board: 板块名称
            continuous_df: 连板股票DataFrame
            
        Returns:
            Tuple[str, str]: (龙头股票名称, 股票代码)
        """
        board_stocks = continuous_df[continuous_df['所属行业'] == board]
        
        if board_stocks.empty:
            return "", ""
        
        # 按连板数排序，取最高的
        board_stocks = board_stocks.sort_values('连板数', ascending=False)
        
        leader = board_stocks.iloc[0]
        return leader.get('名称', ''), str(leader.get('代码', '')).zfill(6)
    
    def generate_logic_suggestion(self) -> Dict:
        """
        生成逻辑库更新建议
        
        Returns:
            Dict: 逻辑库建议
        """
        print("\n" + "="*60)
        print("🔍 市场热点自动分析")
        print("="*60)
        
        # Step 1: 获取数据
        print("\n【Step 1】获取市场数据...")
        limit_up_df = self.fetcher.get_limit_up_stocks()
        continuous_df = self.fetcher.get_continuous_limit_up()
        
        if limit_up_df.empty:
            return {
                'error': '今日无涨停股票，无法分析热点'
            }
        
        # 解析连板数
        if not continuous_df.empty and '涨停统计' in continuous_df.columns:
            def parse_zt_stat(stat):
                try:
                    parts = str(stat).split('/')
                    return int(parts[1]) if len(parts) == 2 else 1
                except:
                    return 1
            continuous_df['连板数'] = continuous_df['涨停统计'].apply(parse_zt_stat)
        
        # Step 2: 分析板块分布
        board_analysis = self.analyze_board_distribution(limit_up_df, continuous_df)
        
        # Step 3: 分析概念分布（只分析连板股票）
        lianban_codes = continuous_df['代码'].astype(str).str.zfill(6).tolist()[:20]
        concept_analysis = self.analyze_concept_distribution(lianban_codes)
        
        # Step 4: 生成逻辑建议
        suggestions = []
        
        for board, stats in list(board_analysis['板块统计'].items())[:5]:
            # 只推荐有3只以上涨停的板块
            if stats['股票数量'] >= 3:
                leader_name, leader_code = self.find_logic_leader(board, continuous_df)
                
                suggestions.append({
                    '板块名称': board,
                    '龙头股票': leader_name,
                    '龙头代码': leader_code,
                    '股票数量': stats['股票数量'],
                    '最高连板': stats['最高连板'],
                    '平均连板': stats['平均连板'],
                    '建议逻辑强度': 5 if stats['最高连板'] >= 5 else 4,
                    '股票列表': stats['股票列表'][:5]
                })
        
        return {
            '板块分析': board_analysis,
            '概念分析': concept_analysis,
            '逻辑建议': suggestions,
            '分析时间': self.fetcher.today
        }


if __name__ == "__main__":
    # 测试代码
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from data_fetcher import DataFetcher
    
    # 重新创建实例
    class TestAnalyzer:
        def __init__(self):
            self.fetcher = DataFetcher()
        
        def run(self):
            return MarketHotspotAnalyzer().generate_logic_suggestion()
    
    analyzer = MarketHotspotAnalyzer()
    analyzer.fetcher = DataFetcher()
    result = analyzer.generate_logic_suggestion()
    
    if 'error' in result:
        print(f"\n❌ {result['error']}")
    else:
        print("\n" + "="*60)
        print("💡 逻辑库更新建议")
        print("="*60)
        
        for i, suggestion in enumerate(result['逻辑建议'], 1):
            print(f"\n{i}. {suggestion['板块名称']} {'⭐' * suggestion['建议逻辑强度']}")
            print(f"   龙头：{suggestion['龙头股票']} ({suggestion['龙头代码']})")
            print(f"   活跃度：{suggestion['股票数量']}只涨停 | 最高{suggestion['最高连板']}板")
            print(f"   股票：{', '.join([s['名称'] for s in suggestion['股票列表']])}")
