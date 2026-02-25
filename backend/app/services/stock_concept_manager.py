#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
股票-概念关系维护脚本
用于直接操作 stock_concept 表，建立或更新股票与概念的关联
"""

import sqlite3
from pathlib import Path
from typing import List, Tuple


class StockConceptManager:
    """股票-概念关系管理器"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def add_stock_to_concept(
        self,
        stock_code: str,
        concept_name: str,
        is_core: bool = True,
        note: str = ""
    ) -> bool:
        """
        添加股票到概念
        
        Args:
            stock_code: 股票代码
            concept_name: 概念名称（细分概念）
            is_core: 是否为核心标的
            note: 备注（如：大类/细分路径）
        
        Returns:
            是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            INSERT OR REPLACE INTO stock_concept 
            (stock_code, concept_name, is_core, note)
            VALUES (?, ?, ?, ?)
            ''', (stock_code, concept_name, 1 if is_core else 0, note))
            
            conn.commit()
            conn.close()
            
            core_label = "核心" if is_core else "相关"
            print(f"✅ 添加 {stock_code} → {concept_name} ({core_label})")
            return True
            
        except Exception as e:
            print(f"❌ 添加失败: {e}")
            return False
    
    def batch_add_stocks(
        self,
        mappings: List[Tuple[str, str, bool, str]]
    ) -> int:
        """
        批量添加股票-概念关系
        
        Args:
            mappings: [(stock_code, concept_name, is_core, note), ...]
        
        Returns:
            成功添加的数量
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        count = 0
        for stock_code, concept_name, is_core, note in mappings:
            try:
                cursor.execute('''
                INSERT OR REPLACE INTO stock_concept 
                (stock_code, concept_name, is_core, note)
                VALUES (?, ?, ?, ?)
                ''', (stock_code, concept_name, 1 if is_core else 0, note))
                count += 1
            except Exception as e:
                print(f"❌ 添加 {stock_code} - {concept_name} 失败: {e}")
        
        conn.commit()
        conn.close()
        
        print(f"✅ 批量添加完成: {count}/{len(mappings)}")
        return count
    
    def remove_stock_from_concept(
        self,
        stock_code: str,
        concept_name: str
    ) -> bool:
        """
        移除股票与概念的关联
        
        Args:
            stock_code: 股票代码
            concept_name: 概念名称
        
        Returns:
            是否成功
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
            DELETE FROM stock_concept 
            WHERE stock_code = ? AND concept_name = ?
            ''', (stock_code, concept_name))
            
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            if deleted > 0:
                print(f"✅ 移除 {stock_code} ← {concept_name}")
                return True
            else:
                print(f"⚠️ 未找到关联: {stock_code} - {concept_name}")
                return False
                
        except Exception as e:
            print(f"❌ 移除失败: {e}")
            return False
    
    def list_concept_stocks(self, concept_name: str) -> List[dict]:
        """
        列出概念下的所有股票
        
        Args:
            concept_name: 概念名称
        
        Returns:
            股票列表（包含股票代码、名称、是否核心、备注）
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT sc.stock_code, sp.stock_name, sc.is_core, sc.note 
        FROM stock_concept sc
        LEFT JOIN stock_pool sp ON sc.stock_code = sp.stock_code
        WHERE sc.concept_name = ?
        ORDER BY sc.is_core DESC, sc.stock_code
        ''', (concept_name,))
        
        stocks = []
        for row in cursor.fetchall():
            stocks.append({
                'stock_code': row[0],
                'stock_name': row[1] if row[1] else '',  # 如果没有找到名称，返回空字符串
                'is_core': bool(row[2]),
                'note': row[3]
            })
        
        conn.close()
        return stocks
    
    def list_all_mappings(self) -> List[dict]:
        """列出所有股票-概念关系"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT stock_code, concept_name, is_core, note 
        FROM stock_concept 
        ORDER BY concept_name, is_core DESC, stock_code
        ''')
        
        mappings = []
        for row in cursor.fetchall():
            mappings.append({
                'stock_code': row[0],
                'concept_name': row[1],
                'is_core': bool(row[2]),
                'note': row[3]
            })
        
        conn.close()
        return mappings


def main():
    """示例：维护商业航天概念的股票关系"""
    script_dir = Path(__file__).resolve().parent
    # 计算项目根目录（需要往上3层）
    project_root = script_dir.parent.parent.parent
    db_path = project_root / "data" / "dragon_stock.db"
    
    if not db_path.exists():
        print(f"❌ 数据库不存在: {db_path}")
        return
    
    manager = StockConceptManager(str(db_path))
    
    print("=" * 60)
    print("示例：维护商业航天概念的股票关系")
    print("=" * 60)
    
    # 示例1：批量添加商业航天概念的股票
    print("\n1. 批量添加股票到商业航天概念：")
    commercial_space_stocks = [
        ('002025', '商业航天', True, '商业航天/商业航天'),
        ('688122', '商业航天', True, '商业航天/商业航天'),
        ('002342', '商业航天', True, '商业航天/商业航天'),
        ('300416', '商业航天', False, '商业航天/商业航天'),
        ('688051', '商业航天', False, '商业航天/商业航天'),
        ('600391', '商业航天', False, '商业航天/商业航天'),
    ]
    manager.batch_add_stocks(commercial_space_stocks)
    
    # 示例2：查看商业航天概念的股票
    print("\n2. 查看商业航天概念下的股票：")
    stocks = manager.list_concept_stocks('商业航天')
    for stock in stocks:
        core_label = "核心" if stock['is_core'] else "相关"
        print(f"  - {stock['stock_code']} ({core_label}) {stock['note']}")
    
    print("\n" + "=" * 60)
    print("💡 提示：")
    print("  - 修改此脚本来添加/删除股票-概念关系")
    print("  - 或直接使用 SQL 操作 stock_concept 表")
    print("=" * 60)


if __name__ == "__main__":
    main()
