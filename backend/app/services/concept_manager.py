#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
概念数据管理器
负责加载概念配置和计算板块统计
"""

import json
import sqlite3
from typing import Dict, List, Optional
from pathlib import Path


class ConceptManager:
    """概念管理器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def load_concept_config(self, config_file: str) -> int:
        """
        从 JSON 文件加载概念定义（不包含股票关联）
        只用于验证概念结构，股票-概念关系直接在数据库中维护
        
        Args:
            config_file: 概念配置文件路径
        
        Returns:
            加载的概念数量
        """
        with open(config_file, 'r', encoding='utf-8') as f:
            concepts = json.load(f)
        
        count = 0
        # 遍历大类和细分概念，只统计数量
        for category_name, category_data in concepts.items():
            subconcepts = category_data.get('subconcepts', {})
            count += len(subconcepts)
        
        print(f"✅ 概念定义加载完成：{len(concepts)} 个大类，{count} 个细分概念")
        return count
    
    def calculate_concept_daily(self, trade_date: str) -> int:
        """
        计算指定日期的概念板块统计
        
        Args:
            trade_date: 交易日期 YYYY-MM-DD
        
        Returns:
            计算的概念数量
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 获取所有概念列表
        cursor.execute('SELECT DISTINCT concept_name FROM stock_concept')
        concepts = [row[0] for row in cursor.fetchall()]
        
        print(f"📊 计算 {trade_date} 概念板块统计，共 {len(concepts)} 个概念...")
        
        count = 0
        
        for concept_name in concepts:
            # 统计该概念的个股表现
            cursor.execute('''
            SELECT 
                COUNT(*) as stock_count,
                SUM(CASE WHEN sd.is_limit_up = 1 THEN 1 ELSE 0 END) as limit_up_count,
                AVG(sd.change_percent) as avg_change,
                SUM(sd.turnover) as total_turnover,
                sd.stock_code as leader_code
            FROM stock_concept sc
            JOIN stock_daily sd ON sc.stock_code = sd.stock_code
            WHERE sc.concept_name = ? AND sd.trade_date = ?
            GROUP BY sc.concept_name
            ORDER BY sd.change_percent DESC
            LIMIT 1
            ''', (concept_name, trade_date))
            
            row = cursor.fetchone()
            if not row or not row[0]:
                continue
            
            stock_count = row[0]
            limit_up_count = row[1] or 0
            avg_change = row[2] or 0
            total_turnover = (row[3] or 0) / 100000000  # 转为亿元
            
            # 获取领涨股（涨幅最大的）
            cursor.execute('''
            SELECT sd.stock_code, sd.change_percent
            FROM stock_concept sc
            JOIN stock_daily sd ON sc.stock_code = sd.stock_code
            WHERE sc.concept_name = ? AND sd.trade_date = ?
            ORDER BY sd.change_percent DESC
            LIMIT 1
            ''', (concept_name, trade_date))
            
            leader_row = cursor.fetchone()
            leader_code = leader_row[0] if leader_row else None
            
            # 保存统计结果
            try:
                cursor.execute('''
                INSERT OR REPLACE INTO concept_daily
                (trade_date, concept_name, stock_count, limit_up_count, 
                 avg_change, total_turnover, leader_code)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (trade_date, concept_name, stock_count, limit_up_count,
                      avg_change, total_turnover, leader_code))
                count += 1
            except Exception as e:
                print(f"❌ 保存 {concept_name} 统计失败: {e}")
        
        conn.commit()
        conn.close()
        
        print(f"✅ 完成！计算了 {count} 个概念的统计数据")
        return count
    
    def get_concept_stocks(self, concept_name: str) -> List[Dict]:
        """
        获取概念内的股票列表
        
        Args:
            concept_name: 概念名称
        
        Returns:
            股票列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT stock_code, is_core, note
        FROM stock_concept
        WHERE concept_name = ?
        ORDER BY is_core DESC
        ''', (concept_name,))
        
        stocks = []
        for row in cursor.fetchall():
            stocks.append({
                'stock_code': row[0],
                'is_core': row[1],
                'note': row[2]
            })
        
        conn.close()
        return stocks
    
    def get_stock_concepts(self, stock_code: str) -> List[Dict]:
        """
        获取股票关联的概念列表
        
        Args:
            stock_code: 股票代码
        
        Returns:
            概念列表
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT concept_name, is_core, note
        FROM stock_concept
        WHERE stock_code = ?
        ORDER BY is_core DESC
        ''', (stock_code,))
        
        concepts = []
        for row in cursor.fetchall():
            concepts.append({
                'concept_name': row[0],
                'is_core': row[1],
                'note': row[2]
            })
        
        conn.close()
        return concepts
    
    def get_concept_stats(self, concept_name: str, trade_date: str) -> Optional[Dict]:
        """
        获取概念在指定日期的统计数据
        
        Args:
            concept_name: 概念名称
            trade_date: 交易日期
        
        Returns:
            统计数据字典
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT trade_date, stock_count, limit_up_count, avg_change,
               total_turnover, leader_code
        FROM concept_daily
        WHERE concept_name = ? AND trade_date = ?
        ''', (concept_name, trade_date))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        return {
            'trade_date': row[0],
            'stock_count': row[1],
            'limit_up_count': row[2],
            'avg_change': row[3],
            'total_turnover': row[4],
            'leader_code': row[5]
        }


def main():
    """命令行测试入口"""
    import sys
    from pathlib import Path
    from datetime import datetime
    
    script_dir = Path(__file__).resolve().parent
    # 计算项目根目录（需要往上3层：scripts -> dragon-stock-trading -> skills -> stock）
    project_root = script_dir.parent.parent.parent
    db_path = project_root / "data" / "dragon_stock.db"
    config_file = project_root / "data" / "concepts.json"
    
    # 确保路径存在
    if not config_file.exists():
        print(f"❌ 配置文件不存在: {config_file}")
        return
    if not db_path.exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        return
    
    manager = ConceptManager(str(db_path))
    
    # 加载概念配置
    print("📂 加载概念配置...")
    manager.load_concept_config(str(config_file))
    
    # 计算今日概念统计
    today = datetime.now().strftime('%Y-%m-%d')
    if len(sys.argv) > 1:
        trade_date = sys.argv[1]
    else:
        trade_date = today
    
    print(f"\n📊 计算 {trade_date} 概念统计...")
    manager.calculate_concept_daily(trade_date)
    
    # 显示商业航天概念统计
    print("\n🚀 商业航天概念统计:")
    stats = manager.get_concept_stats('商业航天', trade_date)
    if stats:
        print(f"  - 个股数量: {stats['stock_count']}")
        print(f"  - 涨停家数: {stats['limit_up_count']}")
        print(f"  - 平均涨幅: {stats['avg_change']*100:.2f}%")
        print(f"  - 总成交额: {stats['total_turnover']:.2f}亿")
        print(f"  - 领涨股: {stats['leader_code']}")


if __name__ == "__main__":
    main()
