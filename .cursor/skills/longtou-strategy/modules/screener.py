"""
筛选器模块
实现龙头战法的筛选逻辑
"""

import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from .data_fetcher import DataFetcher
from .logic_matcher import LogicMatcher


class LongtouScreener:
    """龙头战法筛选器"""
    
    def __init__(self):
        self.fetcher = DataFetcher()
        self.matcher = LogicMatcher()
    
    def analyze_market_state(self, limit_down_count: int, max_continuous: int) -> Dict:
        """
        分析市场状态
        
        Args:
            limit_down_count: 昨日跌停家数
            max_continuous: 连板最高高度
            
        Returns:
            Dict: 市场状态分析
        """
        # 判断市场状态
        if limit_down_count > 15 and max_continuous <= 2:
            state = "冰点修复"
            description = "昨日跌停>15家 + 连板高度≤2板 → 今日聚焦抗分歧标的"
            focus = ["冰点修复"]
        elif max_continuous >= 3:
            state = "增量主升"
            description = "连板高度≥3板 → 只做身位龙"
            focus = ["龙头弱转强", "补涨分离"]
        else:
            state = "震荡"
            description = "市场震荡，机会不明显"
            focus = ["机构趋势"]
        
        return {
            '状态': state,
            '描述': description,
            '昨日跌停': limit_down_count,
            '连板高度': max_continuous,
            '重点关注': focus
        }
    
    def calculate_popularity_rank(self, 
                                   stock_code: str,
                                   stock_name: str,
                                   limit_up_time: str,
                                   continuous_days: int,
                                   in_dragon_tiger: bool) -> int:
        """
        计算人气排名（简化版，基于规则打分）
        
        Args:
            stock_code: 股票代码
            stock_name: 股票名称
            limit_up_time: 涨停时间
            continuous_days: 连板天数
            in_dragon_tiger: 是否在龙虎榜
            
        Returns:
            int: 人气分数（越高越好）
        """
        score = 0
        
        # 1. 连板天数贡献（连板越多，人气越高）
        score += continuous_days * 20
        
        # 2. 涨停时间贡献（越早涨停，人气越高）
        try:
            time_str = limit_up_time.replace(":", "")
            time_int = int(time_str)
            if time_int < 93500:  # 9:35之前
                score += 30
            elif time_int < 100000:  # 10:00之前
                score += 20
            elif time_int < 103000:  # 10:30之前
                score += 10
            else:
                score += 5
        except:
            score += 5
        
        # 3. 龙虎榜贡献
        if in_dragon_tiger:
            score += 25
        
        return score
    
    def judge_position(self, 
                       stock_name: str,
                       continuous_days: int,
                       limit_up_time: str,
                       is_leader: bool) -> Tuple[str, str]:
        """
        判断股票地位
        
        Args:
            stock_name: 股票名称
            continuous_days: 连板天数
            limit_up_time: 涨停时间
            is_leader: 是否是逻辑龙头
            
        Returns:
            Tuple[str, str]: (地位, 判断理由)
        """
        reasons = []
        
        # 1. 身位判断
        if continuous_days >= 5:
            position = "超级龙头"
            reasons.append(f"身位最高（{continuous_days}板）")
        elif continuous_days >= 3:
            position = "龙头"
            reasons.append(f"身位较高（{continuous_days}板）")
        elif continuous_days >= 2:
            position = "补涨"
            reasons.append(f"中位股（{continuous_days}板）")
        else:
            position = "首板"
            reasons.append("首板股")
        
        # 2. 领涨性判断
        try:
            time_str = limit_up_time.replace(":", "")
            time_int = int(time_str)
            if time_int < 93500:
                reasons.append("领涨性强（早盘涨停）")
        except:
            pass
        
        # 3. 是否是逻辑龙头
        if is_leader:
            reasons.append("逻辑龙头")
        
        return position, " | ".join(reasons)
    
    def screen_stocks(self, 
                      top_n: int = 30,
                      min_logic_strength: int = 4) -> Dict:
        """
        执行筛选流程
        
        Args:
            top_n: 筛选人气榜前N只
            min_logic_strength: 最小逻辑强度
            
        Returns:
            Dict: 筛选结果
        """
        print("\n" + "="*60)
        print("🚀 龙头战法筛选器启动")
        print("="*60)
        
        # Step 1: 获取数据
        print("\n【Step 1】获取市场数据...")
        limit_up_df = self.fetcher.get_limit_up_stocks()
        continuous_df = self.fetcher.get_continuous_limit_up()
        dragon_tiger_df = self.fetcher.get_dragon_tiger_list()
        limit_down_count = self.fetcher.get_limit_down_count()
        
        if limit_up_df.empty:
            return {
                'error': '今日暂无涨停股票',
                'selected_stocks': [],
                'filtered_stocks': [],
                'market_state': {}
            }
        
        # Step 2: 分析市场状态
        print("\n【Step 2】分析市场状态...")
        max_continuous = 0
        if not continuous_df.empty and '连板数' in continuous_df.columns:
            max_continuous = continuous_df['连板数'].max()
        
        market_state = self.analyze_market_state(limit_down_count, max_continuous)
        print(f"市场状态：{market_state['状态']}")
        print(f"说明：{market_state['描述']}")
        
        # Step 3: 构建连板字典
        continuous_dict = {}
        if not continuous_df.empty:
            for _, row in continuous_df.iterrows():
                code = str(row.get('代码', '')).zfill(6)
                continuous_dict[code] = int(row.get('连板数', 1))
        
        # Step 4: 构建龙虎榜字典
        dragon_tiger_codes = set()
        if not dragon_tiger_df.empty and '代码' in dragon_tiger_df.columns:
            dragon_tiger_codes = set(dragon_tiger_df['代码'].astype(str).str.zfill(6))
        
        # Step 5: 遍历涨停股票，计算人气分数
        print("\n【Step 3】计算人气排名...")
        stocks_with_score = []
        
        for idx, row in limit_up_df.iterrows():
            code = str(row.get('代码', '')).zfill(6)
            name = row.get('名称', '')
            limit_up_time = str(row.get('首次封板时间', '14:00'))
            
            # 获取连板数
            continuous_days = continuous_dict.get(code, 1)
            
            # 是否在龙虎榜
            in_dragon_tiger = code in dragon_tiger_codes
            
            # 计算人气分数
            score = self.calculate_popularity_rank(
                code, name, limit_up_time, continuous_days, in_dragon_tiger
            )
            
            stocks_with_score.append({
                '代码': code,
                '名称': name,
                '连板数': continuous_days,
                '首板时间': limit_up_time,
                '龙虎榜': in_dragon_tiger,
                '人气分数': score,
                'raw_data': row
            })
        
        # 按人气分数排序
        stocks_with_score.sort(key=lambda x: x['人气分数'], reverse=True)
        
        print(f"人气榜前{top_n}只股票：")
        for i, stock in enumerate(stocks_with_score[:top_n], 1):
            print(f"  {i}. {stock['名称']} - 连板{stock['连板数']}天 - 分数{stock['人气分数']}")
        
        # Step 6: 筛选人气榜前N只
        top_stocks = stocks_with_score[:top_n]
        
        # Step 7: 逻辑匹配
        print(f"\n【Step 4】逻辑匹配（最小强度：{min_logic_strength}星）...")
        selected_stocks = []
        filtered_stocks = []
        
        for stock in top_stocks:
            code = stock['代码']
            name = stock['名称']
            
            # 获取股票概念
            print(f"  分析 {name} ({code})...", end='')
            concepts = self.fetcher.get_stock_board_concept(code)
            
            if not concepts:
                print(" ⚠️  无法获取概念")
                filtered_stocks.append({
                    **stock,
                    '过滤原因': '无法获取概念信息'
                })
                continue
            
            print(f" ✓ 获取到{len(concepts)}个概念")
            
            # 匹配逻辑
            logic = self.matcher.match_logic(concepts)
            
            if logic is None:
                filtered_stocks.append({
                    **stock,
                    '概念': concepts[:5],  # 只显示前5个
                    '过滤原因': '未匹配到当前热点逻辑'
                })
                continue
            
            # 检查逻辑强度
            if logic['逻辑强度'] < min_logic_strength:
                filtered_stocks.append({
                    **stock,
                    '逻辑': logic['名称'],
                    '逻辑强度': logic['逻辑强度'],
                    '过滤原因': f'逻辑强度不足（{logic["逻辑强度"]}星 < {min_logic_strength}星）'
                })
                continue
            
            # 判断是否是核心受益方
            is_core, benefit_level = self.matcher.is_core_beneficiary(name, logic['名称'])
            
            if benefit_level == "蹭热点":
                filtered_stocks.append({
                    **stock,
                    '逻辑': logic['名称'],
                    '逻辑强度': logic['逻辑强度'],
                    '过滤原因': '蹭热点，非真正受益方'
                })
                continue
            
            # 判断地位
            is_leader = (logic['龙头代码'] == code)
            position, position_reason = self.judge_position(
                name, 
                stock['连板数'], 
                stock['首板时间'],
                is_leader
            )
            
            # 通过筛选
            selected_stocks.append({
                **stock,
                '逻辑': logic['名称'],
                '逻辑强度': logic['逻辑强度'],
                '炒作原因': logic['炒作原因'],
                '催化剂': logic['催化剂'],
                '持续性': logic['持续性'],
                '驱动类型': logic['驱动类型'],
                '推荐模式': logic['推荐模式'],
                '风险提示': logic['风险提示'],
                '匹配概念': logic['匹配概念'],
                '受益等级': benefit_level,
                '地位': position,
                '地位理由': position_reason,
                '是否龙头': is_leader
            })
            
            print(f"    ✅ 通过筛选 - {logic['名称']} ({self.matcher.format_logic_strength(logic['逻辑强度'])})")
        
        # 按逻辑强度 + 连板数排序
        selected_stocks.sort(
            key=lambda x: (x['逻辑强度'] * 100 + x['连板数']), 
            reverse=True
        )
        
        print(f"\n【筛选完成】通过筛选：{len(selected_stocks)} 只，过滤：{len(filtered_stocks)} 只")
        
        return {
            'market_state': market_state,
            'selected_stocks': selected_stocks,
            'filtered_stocks': filtered_stocks,
            'total_limit_up': len(limit_up_df),
            'scan_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }


if __name__ == "__main__":
    # 测试代码
    screener = LongtouScreener()
    result = screener.screen_stocks(top_n=30, min_logic_strength=4)
    
    print("\n" + "="*60)
    print("筛选结果：")
    print("="*60)
    
    for i, stock in enumerate(result['selected_stocks'], 1):
        print(f"\n{i}. {stock['名称']} ({stock['代码']})")
        print(f"   逻辑：{stock['逻辑']} ({stock['逻辑强度']}星)")
        print(f"   地位：{stock['地位']} - {stock['地位理由']}")
        print(f"   推荐模式：{', '.join(stock['推荐模式'])}")
