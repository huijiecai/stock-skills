#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将stock_list.json和concepts.json迁移到SQLite数据库

这个脚本将JSON配置文件中的数据导入到数据库表中：
- stock_list.json -> stock_pool表
- concepts.json -> concept_hierarchy表

依赖: backend/scripts/db_init.py
"""

import json
import sqlite3
from pathlib import Path
import sys

# 添加backend/scripts到路径以导入db_init
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from db_init import DatabaseInitializer


def migrate_stock_list(db_path: str, json_path: str):
    """
    迁移股票池数据
    
    从stock_list.json导入到stock_pool表
    """
    print(f"\n📥 开始迁移股票池数据...")
    print(f"  JSON文件: {json_path}")
    print(f"  数据库: {db_path}")
    
    # 读取JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    stocks = data.get('stocks', [])
    update_date = data.get('update_date', '')
    
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 插入数据
    success_count = 0
    for stock in stocks:
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO stock_pool 
                (stock_code, stock_name, market, is_active, added_date)
                VALUES (?, ?, ?, 1, ?)
            ''', (
                stock['code'],
                stock['name'],
                stock['market'],
                update_date
            ))
            success_count += 1
        except Exception as e:
            print(f"  ❌ 导入失败 {stock['code']} {stock['name']}: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"  ✅ 成功迁移 {success_count}/{len(stocks)} 只股票")


def migrate_concepts(db_path: str, json_path: str):
    """
    迁移概念层级数据
    
    从concepts.json导入到concept_hierarchy表
    """
    print(f"\n📥 开始迁移概念层级数据...")
    print(f"  JSON文件: {json_path}")
    print(f"  数据库: {db_path}")
    
    # 读取JSON
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 连接数据库
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    parent_count = 0
    sub_count = 0
    
    # 遍历所有顶级概念
    for parent_name, parent_data in data.items():
        try:
            # 插入顶级概念
            cursor.execute('''
                INSERT OR REPLACE INTO concept_hierarchy
                (concept_name, parent_concept, description, position_in_chain)
                VALUES (?, NULL, ?, NULL)
            ''', (
                parent_name,
                parent_data.get('description', '')
            ))
            parent_count += 1
            
            # 插入子概念
            subconcepts = parent_data.get('subconcepts', {})
            for sub_name, sub_data in subconcepts.items():
                cursor.execute('''
                    INSERT OR REPLACE INTO concept_hierarchy
                    (concept_name, parent_concept, description, position_in_chain)
                    VALUES (?, ?, ?, ?)
                ''', (
                    sub_name,
                    parent_name,
                    sub_data.get('description', ''),
                    sub_data.get('description', '')  # 使用description作为position_in_chain
                ))
                sub_count += 1
                
        except Exception as e:
            print(f"  ❌ 导入失败 {parent_name}: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"  ✅ 成功迁移 {parent_count} 个顶级概念")
    print(f"  ✅ 成功迁移 {sub_count} 个子概念")


def verify_migration(db_path: str):
    """验证迁移结果"""
    print(f"\n🔍 验证迁移结果...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 检查股票池
    cursor.execute("SELECT COUNT(*) FROM stock_pool")
    stock_count = cursor.fetchone()[0]
    print(f"  股票池: {stock_count} 只股票")
    
    # 检查顶级概念
    cursor.execute("SELECT COUNT(*) FROM concept_hierarchy WHERE parent_concept IS NULL")
    parent_count = cursor.fetchone()[0]
    print(f"  顶级概念: {parent_count} 个")
    
    # 检查子概念
    cursor.execute("SELECT COUNT(*) FROM concept_hierarchy WHERE parent_concept IS NOT NULL")
    sub_count = cursor.fetchone()[0]
    print(f"  子概念: {sub_count} 个")
    
    # 显示一些示例
    print(f"\n  📋 股票池示例:")
    cursor.execute("SELECT stock_code, stock_name, market FROM stock_pool LIMIT 5")
    for row in cursor.fetchall():
        print(f"    - {row[0]} {row[1]} ({row[2]})")
    
    print(f"\n  📋 概念层级示例:")
    cursor.execute("""
        SELECT c1.concept_name, c2.concept_name as sub_concept
        FROM concept_hierarchy c1
        LEFT JOIN concept_hierarchy c2 ON c2.parent_concept = c1.concept_name
        WHERE c1.parent_concept IS NULL
        LIMIT 3
    """)
    
    current_parent = None
    for row in cursor.fetchall():
        if row[0] != current_parent:
            print(f"    - {row[0]}")
            current_parent = row[0]
        if row[1]:
            print(f"      └─ {row[1]}")
    
    conn.close()
    
    print(f"\n✅ 迁移验证完成")


def main():
    """主函数"""
    # 计算路径
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    
    db_path = project_root / "data" / "dragon_stock.db"
    stock_list_path = project_root / "data" / "stock_list.json"
    concepts_path = project_root / "data" / "concepts.json"
    
    print("=" * 60)
    print("数据迁移工具：JSON -> SQLite")
    print("=" * 60)
    
    # 检查文件是否存在
    if not db_path.exists():
        print(f"❌ 数据库文件不存在: {db_path}")
        print("请先运行: python skills/dragon-stock-trading/scripts/db_init.py")
        return
    
    if not stock_list_path.exists():
        print(f"❌ 股票列表文件不存在: {stock_list_path}")
        return
    
    if not concepts_path.exists():
        print(f"❌ 概念配置文件不存在: {concepts_path}")
        return
    
    # 执行迁移
    try:
        migrate_stock_list(str(db_path), str(stock_list_path))
        migrate_concepts(str(db_path), str(concepts_path))
        verify_migration(str(db_path))
        
        print("\n" + "=" * 60)
        print("✅ 数据迁移完成！")
        print("=" * 60)
        print("\n💡 提示:")
        print("  - JSON文件已迁移到数据库，可保留作为备份")
        print("  - 后续修改股票池/概念请通过API或直接操作数据库")
        print("  - 前端、Skill将自动从数据库读取数据")
        
    except Exception as e:
        print(f"\n❌ 迁移失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
