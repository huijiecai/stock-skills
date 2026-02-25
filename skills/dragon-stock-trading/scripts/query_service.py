#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据查询服务
为 SKILL 提供结构化查询接口
"""

import sqlite3
from typing import Dict, List, Optional
from datetime import datetime, timedelta


class QueryService:
    """数据查询服务"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def get_market_status(self, trade_date: str) -> Optional[Dict]:
        """
        获取市场状态（用于判断冰点/主升）
        
        Args:
            trade_date: 交易日期
        
        Returns:
            市场状态数据
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT trade_date, limit_up_count, limit_down_count, max_streak,
               sh_index_change, sz_index_change, cy_index_change, total_turnover
        FROM market_sentiment
        WHERE trade_date = ?
        ''', (trade_date,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        limit_up_count = row[1]
        limit_down_count = row[2]
        max_streak = row[3]
        
        # 判断市场状态
        market_phase = "正常"
        if limit_down_count > 15 and max_streak <= 2:
            market_phase = "情绪冰点"
        elif limit_up_count > 50 and max_streak >= 5:
            market_phase = "情绪高潮"
        elif limit_up_count > 30:
            market_phase = "增量主升"
        
        return {
            'trade_date': row[0],
            'limit_up_count': limit_up_count,
            'limit_down_count': limit_down_count,
            'max_streak': max_streak,
            'sh_index_change': row[4],
            'sz_index_change': row[5],
            'cy_index_change': row[6],
            'total_turnover': row[7],
            'market_phase': market_phase
        }
    
    def get_stock_with_concept(self, stock_code: str, trade_date: str) -> Optional[Dict]:
        """
        获取个股完整信息（含概念、连板等）
        
        Args:
            stock_code: 股票代码
            trade_date: 交易日期
        
        Returns:
            股票完整信息
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 获取日行情
        cursor.execute('''
        SELECT stock_code, stock_name, market, open_price, high_price, low_price,
               close_price, pre_close, change_amount, change_percent, volume, turnover,
               turnover_rate, is_limit_up, is_limit_down, streak_days
        FROM stock_daily
        WHERE stock_code = ? AND trade_date = ?
        ''', (stock_code, trade_date))
        
        row = cursor.fetchone()
        if not row:
            conn.close()
            return None
        
        stock_data = {
            'stock_code': row[0],
            'stock_name': row[1],
            'market': row[2],
            'open_price': row[3] or 0,
            'high_price': row[4] or 0,
            'low_price': row[5] or 0,
            'close_price': row[6] or 0,
            'pre_close': row[7] or 0,
            'change_amount': row[8] or 0,
            'change_percent': row[9] or 0,
            'volume': row[10] or 0,
            'turnover': row[11] or 0,
            'turnover_rate': row[12] or 0,
            'is_limit_up': row[13] or 0,
            'is_limit_down': row[14] or 0,
            'streak_days': row[15] or 0
        }
        
        # 获取关联概念
        cursor.execute('''
        SELECT concept_name, is_core
        FROM stock_concept
        WHERE stock_code = ?
        ORDER BY is_core DESC
        ''', (stock_code,))
        
        concepts = []
        for concept_row in cursor.fetchall():
            concepts.append({
                'name': concept_row[0],
                'is_core': concept_row[1]
            })
        
        stock_data['concepts'] = concepts
        
        # 获取基本信息
        cursor.execute('''
        SELECT industry, sub_industry
        FROM stock_info
        WHERE stock_code = ?
        ''', (stock_code,))
        
        info_row = cursor.fetchone()
        if info_row:
            stock_data['industry'] = info_row[0]
            stock_data['sub_industry'] = info_row[1]
        
        conn.close()
        return stock_data
    
    def get_concept_leaders(self, trade_date: str, min_limit_up: int = 1) -> List[Dict]:
        """
        获取各概念龙头列表
        
        Args:
            trade_date: 交易日期
            min_limit_up: 最少涨停家数
        
        Returns:
            概念龙头列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT cd.concept_name, cd.stock_count, cd.limit_up_count, cd.avg_change,
               cd.total_turnover, cd.leader_code, sd.stock_name, sd.change_percent,
               sd.streak_days
        FROM concept_daily cd
        LEFT JOIN stock_daily sd ON cd.leader_code = sd.stock_code AND cd.trade_date = sd.trade_date
        WHERE cd.trade_date = ? AND cd.limit_up_count >= ?
        ORDER BY cd.limit_up_count DESC, cd.avg_change DESC
        ''', (trade_date, min_limit_up))
        
        leaders = []
        for row in cursor.fetchall():
            leaders.append({
                'concept_name': row[0],
                'stock_count': row[1],
                'limit_up_count': row[2],
                'avg_change': row[3],
                'total_turnover': row[4],
                'leader_code': row[5],
                'leader_name': row[6],
                'leader_change': row[7],
                'leader_streak': row[8]
            })
        
        conn.close()
        return leaders
    
    def get_stock_popularity_rank(self, trade_date: str, top_n: int = 30) -> List[Dict]:
        """
        获取人气榜（按成交额排名）
        
        Args:
            trade_date: 交易日期
            top_n: 返回前N名
        
        Returns:
            人气股列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT stock_code, stock_name, close_price, change_percent, turnover,
               is_limit_up, streak_days
        FROM stock_daily
        WHERE trade_date = ?
        ORDER BY turnover DESC
        LIMIT ?
        ''', (trade_date, top_n))
        
        popularity = []
        for idx, row in enumerate(cursor.fetchall(), 1):
            popularity.append({
                'rank': idx,
                'stock_code': row[0],
                'stock_name': row[1],
                'close_price': row[2],
                'change_percent': row[3],
                'turnover': row[4],
                'is_limit_up': row[5],
                'streak_days': row[6]
            })
        
        conn.close()
        return popularity
    
    def check_limit_up_sequence(self, concept_name: str, trade_date: str) -> List[Dict]:
        """
        查询概念内涨停先后顺序
        
        Args:
            concept_name: 概念名称
            trade_date: 交易日期
        
        Returns:
            涨停股票列表（按涨停时间排序）
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT sd.stock_code, sd.stock_name, sd.change_percent, sd.streak_days,
               sd.limit_up_time
        FROM stock_concept sc
        JOIN stock_daily sd ON sc.stock_code = sd.stock_code
        WHERE sc.concept_name = ? AND sd.trade_date = ? AND sd.is_limit_up = 1
        ORDER BY sd.limit_up_time ASC
        ''', (concept_name, trade_date))
        
        sequence = []
        for row in cursor.fetchall():
            sequence.append({
                'stock_code': row[0],
                'stock_name': row[1],
                'change_percent': row[2],
                'streak_days': row[3],
                'limit_up_time': row[4]
            })
        
        conn.close()
        return sequence
    
    def get_stock_history(self, stock_code: str, days: int = 10) -> List[Dict]:
        """
        获取股票历史走势
        
        Args:
            stock_code: 股票代码
            days: 查询天数
        
        Returns:
            历史行情列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT trade_date, open_price, high_price, low_price, close_price,
               change_percent, volume, turnover, is_limit_up, streak_days
        FROM stock_daily
        WHERE stock_code = ?
        ORDER BY trade_date DESC
        LIMIT ?
        ''', (stock_code, days))
        
        history = []
        for row in cursor.fetchall():
            history.append({
                'trade_date': row[0],
                'open_price': row[1],
                'high_price': row[2],
                'low_price': row[3],
                'close_price': row[4],
                'change_percent': row[5],
                'volume': row[6],
                'turnover': row[7],
                'is_limit_up': row[8],
                'streak_days': row[9]
            })
        
        conn.close()
        return history
    
    def format_market_status(self, data: Dict) -> str:
        """格式化市场状态输出"""
        if not data:
            return "❌ 无市场数据"
        
        phase_emoji = {
            '情绪冰点': '🧊',
            '情绪高潮': '🔥',
            '增量主升': '📈',
            '正常': '📊'
        }
        
        emoji = phase_emoji.get(data['market_phase'], '📊')
        
        return f"""
{emoji} 市场状态 ({data['trade_date']})
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 市场阶段: {data['market_phase']}
📈 涨停家数: {data['limit_up_count']}家
📉 跌停家数: {data['limit_down_count']}家
🏆 最高连板: {data['max_streak']}板
💰 总成交额: {data['total_turnover']:.2f}亿元

指数表现:
  上证指数: {data['sh_index_change']*100:+.2f}%
  深证成指: {data['sz_index_change']*100:+.2f}%
  创业板指: {data['cy_index_change']*100:+.2f}%
"""
    
    def format_stock_info(self, data: Dict) -> str:
        """格式化个股信息输出"""
        if not data:
            return "❌ 无股票数据"
        
        status = ""
        if data.get('is_limit_up'):
            status = f"🔴 涨停 ({data.get('streak_days', 0)}连板)" if data.get('streak_days', 0) > 1 else "🔴 涨停"
        elif data.get('is_limit_down'):
            status = "🟢 跌停"
        
        concepts_str = ", ".join([f"{'⭐' if c.get('is_core') else ''}{c.get('name', '')}" for c in data.get('concepts', [])])
        
        # 安全获取所有字段
        stock_name = data.get('stock_name', 'N/A')
        stock_code = data.get('stock_code', 'N/A')
        close_price = data.get('close_price', 0)
        change_percent = data.get('change_percent', 0)
        change_amount = data.get('change_amount', 0)
        volume = data.get('volume', 0)
        turnover = data.get('turnover', 0)
        turnover_rate = data.get('turnover_rate', 0)
        industry = data.get('industry', '未知')
        open_price = data.get('open_price', 0)
        high_price = data.get('high_price', 0)
        low_price = data.get('low_price', 0)
        pre_close = data.get('pre_close', 0)
        
        amplitude = (high_price - low_price) / pre_close * 100 if pre_close > 0 else 0
        
        return f"""
🔍 {stock_name} ({stock_code}) {status}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 最新价格: {close_price:.2f}元 ({change_percent*100:+.2f}%)
📊 涨跌额: {change_amount:+.2f}元
📊 成交量: {volume:,}手
💰 成交额: {turnover/100000000:.2f}亿元
🔄 换手率: {turnover_rate:.2f}%

🏷️ 概念标签: {concepts_str or '无'}
🏭 行业分类: {industry}

📈 今日行情:
  开盘: {open_price:.2f}元
  最高: {high_price:.2f}元
  最低: {low_price:.2f}元
  昨收: {pre_close:.2f}元
  振幅: {amplitude:.2f}%
"""


def main():
    """命令行测试入口"""
    import sys
    from pathlib import Path
    from datetime import datetime
    
    script_dir = Path(__file__).resolve().parent
    # 计算项目根目录（需要往上3层）
    project_root = script_dir.parent.parent.parent
    db_path = project_root / "data" / "dragon_stock.db"
    
    if not db_path.exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        return
    
    service = QueryService(str(db_path))
    
    today = datetime.now().strftime('%Y-%m-%d')
    trade_date = sys.argv[1] if len(sys.argv) > 1 else today
    
    # 测试市场状态查询
    print("=" * 50)
    print("测试1: 市场状态查询")
    print("=" * 50)
    market_status = service.get_market_status(trade_date)
    print(service.format_market_status(market_status))
    
    # 测试个股查询
    print("\n" + "=" * 50)
    print("测试2: 个股信息查询（巨力索具）")
    print("=" * 50)
    stock_info = service.get_stock_with_concept('002342', trade_date)
    print(service.format_stock_info(stock_info))
    
    # 测试人气榜
    print("\n" + "=" * 50)
    print("测试3: 人气榜 Top 5")
    print("=" * 50)
    popularity = service.get_stock_popularity_rank(trade_date, 5)
    for stock in popularity:
        print(f"{stock['rank']}. {stock['stock_name']}({stock['stock_code']}) "
              f"{stock['change_percent']*100:+.2f}% 成交{stock['turnover']/100000000:.2f}亿")
    
    # 测试概念龙头
    print("\n" + "=" * 50)
    print("测试4: 概念龙头")
    print("=" * 50)
    leaders = service.get_concept_leaders(trade_date, min_limit_up=1)
    for leader in leaders[:5]:
        print(f"🏆 {leader['concept_name']}: {leader['leader_name']}({leader['leader_code']}) "
              f"{leader['leader_change']*100:+.2f}% (涨停{leader['limit_up_count']}家)")


if __name__ == "__main__":
    main()
