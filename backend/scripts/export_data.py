#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据导出工具 - 将数据库中的重要数据导出为JSON格式
用于版本控制、备份和团队共享配置数据
"""

import sqlite3
import json
import os
from pathlib import Path
from datetime import datetime


class DataExporter:
    """数据导出器"""
    
    def __init__(self, db_path: str, export_dir: str = None):
        self.db_path = db_path
        self.export_dir = Path(export_dir) if export_dir else Path(db_path).parent / "exports"
        self.export_dir.mkdir(exist_ok=True)
    
    def export_stock_pool(self) -> dict:
        """导出股票池配置（从stock_info表）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT stock_code, stock_name, market, board_type
            FROM stock_info
            ORDER BY stock_code
        ''')
        
        stocks = []
        for row in cursor.fetchall():
            stocks.append({
                'code': row[0],
                'name': row[1],
                'market': row[2],
                'board_type': row[3] or ""
            })
        
        conn.close()
        
        return {
            'metadata': {
                'export_time': datetime.now().isoformat(),
                'source_table': 'stock_info',
                'count': len(stocks)
            },
            'data': stocks
        }
    
    def export_concepts(self) -> dict:
        """导出概念配置"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 导出概念层级
        cursor.execute('''
            SELECT concept_name, parent_concept, description, position_in_chain
            FROM concept_hierarchy
            ORDER BY parent_concept NULLS FIRST, concept_name
        ''')
        
        concepts = {}
        for row in cursor.fetchall():
            concept_name = row[0]
            parent = row[1]
            description = row[2] or ""
            position = row[3] or ""
            
            if parent is None:
                # 顶级概念
                concepts[concept_name] = {
                    'description': description,
                    'position': position,
                    'subconcepts': {}
                }
            else:
                # 子概念
                if parent in concepts:
                    concepts[parent]['subconcepts'][concept_name] = {
                        'description': description,
                        'position': position
                    }
        
        # 导出股票-概念关系
        cursor.execute('''
            SELECT sc.stock_code, si.stock_name, sc.concept_name, sc.is_core, sc.note
            FROM stock_concept sc
            LEFT JOIN stock_info si ON sc.stock_code = si.stock_code
            ORDER BY sc.concept_name, sc.stock_code
        ''')
        
        stock_concepts = {}
        for row in cursor.fetchall():
            stock_code = row[0]
            stock_name = row[1] or stock_code
            concept_name = row[2]
            is_core = bool(row[3])
            note = row[4] or ""
            
            if concept_name not in stock_concepts:
                stock_concepts[concept_name] = {
                    'core_stocks': [],
                    'related_stocks': []
                }
            
            stock_info = {
                'code': stock_code,
                'name': stock_name,
                'note': note
            }
            
            if is_core:
                stock_concepts[concept_name]['core_stocks'].append(stock_info)
            else:
                stock_concepts[concept_name]['related_stocks'].append(stock_info)
        
        conn.close()
        
        return {
            'metadata': {
                'export_time': datetime.now().isoformat(),
                'tables': ['concept_hierarchy', 'stock_concept'],
                'concept_count': len(concepts),
                'relationship_count': sum(len(v.get('core_stocks', [])) + len(v.get('related_stocks', [])) 
                                        for v in stock_concepts.values())
            },
            'hierarchy': concepts,
            'relationships': stock_concepts
        }
    
    def export_all(self):
        """导出所有可版本控制的数据"""
        print("📦 开始导出数据...")
        
        # 导出股票池
        stock_data = self.export_stock_pool()
        stock_file = self.export_dir / "stock_pool.json"
        with open(stock_file, 'w', encoding='utf-8') as f:
            json.dump(stock_data, f, ensure_ascii=False, indent=2)
        print(f"✅ 股票池已导出: {stock_file} ({stock_data['metadata']['count']} 只股票)")
        
        # 导出概念配置
        concept_data = self.export_concepts()
        concept_file = self.export_dir / "concepts.json"
        with open(concept_file, 'w', encoding='utf-8') as f:
            json.dump(concept_data, f, ensure_ascii=False, indent=2)
        print(f"✅ 概念配置已导出: {concept_file}")
        
        print(f"\n📁 导出完成，文件保存在: {self.export_dir}")
        print("📝 这些JSON文件可以提交到Git进行版本控制")


class DataImporter:
    """数据导入器"""
    
    def __init__(self, db_path: str, export_dir: str = None):
        self.db_path = db_path
        self.export_dir = Path(export_dir) if export_dir else Path(db_path).parent / "exports"
    
    def import_stock_pool(self, data: dict):
        """导入股票池配置"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 清空现有数据
        cursor.execute("DELETE FROM stock_pool")
        
        # 插入新数据
        for stock in data['data']:
            cursor.execute('''
                INSERT INTO stock_pool (stock_code, stock_name, market, is_active, added_date, note)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                stock['code'],
                stock['name'],
                stock['market'],
                int(stock['is_active']),
                stock['added_date'],
                stock['note']
            ))
        
        conn.commit()
        conn.close()
        
        print(f"✅ 股票池导入完成: {len(data['data'])} 只股票")
    
    def import_concepts(self, data: dict):
        """导入概念配置"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 清空现有数据
        cursor.execute("DELETE FROM concept_hierarchy")
        cursor.execute("DELETE FROM stock_concept")
        
        # 导入概念层级
        for concept_name, concept_info in data['hierarchy'].items():
            cursor.execute('''
                INSERT INTO concept_hierarchy (concept_name, parent_concept, description, position_in_chain)
                VALUES (?, NULL, ?, ?)
            ''', (concept_name, concept_info['description'], concept_info['position']))
            
            # 导入子概念
            for sub_name, sub_info in concept_info.get('subconcepts', {}).items():
                cursor.execute('''
                    INSERT INTO concept_hierarchy (concept_name, parent_concept, description, position_in_chain)
                    VALUES (?, ?, ?, ?)
                ''', (sub_name, concept_name, sub_info['description'], sub_info['position']))
        
        # 导入股票-概念关系
        for concept_name, stocks in data['relationships'].items():
            # 核心股票
            for stock in stocks.get('core_stocks', []):
                cursor.execute('''
                    INSERT INTO stock_concept (stock_code, concept_name, is_core, note)
                    VALUES (?, ?, 1, ?)
                ''', (stock['code'], concept_name, stock['note']))
            
            # 相关股票
            for stock in stocks.get('related_stocks', []):
                cursor.execute('''
                    INSERT INTO stock_concept (stock_code, concept_name, is_core, note)
                    VALUES (?, ?, 0, ?)
                ''', (stock['code'], concept_name, stock['note']))
        
        conn.commit()
        conn.close()
        
        print(f"✅ 概念配置导入完成: {len(data['hierarchy'])} 个概念")
    
    def import_all(self):
        """导入所有数据"""
        print("📥 开始导入数据...")
        
        # 导入股票池
        stock_file = self.export_dir / "stock_pool.json"
        if stock_file.exists():
            with open(stock_file, 'r', encoding='utf-8') as f:
                stock_data = json.load(f)
            self.import_stock_pool(stock_data)
        else:
            print(f"⚠️  股票池文件不存在: {stock_file}")
        
        # 导入概念配置
        concept_file = self.export_dir / "concepts.json"
        if concept_file.exists():
            with open(concept_file, 'r', encoding='utf-8') as f:
                concept_data = json.load(f)
            self.import_concepts(concept_data)
        else:
            print(f"⚠️  概念配置文件不存在: {concept_file}")
        
        print("✅ 数据导入完成")


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='数据导出/导入工具')
    parser.add_argument('action', choices=['export', 'import'], help='操作类型')
    parser.add_argument('--db-path', help='数据库路径')
    parser.add_argument('--export-dir', help='导出目录')
    
    args = parser.parse_args()
    
    # 默认路径
    if not args.db_path:
        project_root = Path(__file__).parent.parent.parent
        args.db_path = str(project_root / "data" / "dragon_stock.db")
    
    # 设置导出目录为项目根目录下的data/exports
    if not args.export_dir:
        project_root = Path(__file__).parent.parent.parent
        args.export_dir = str(project_root / "data" / "exports")
    
    print(f"数据库路径: {args.db_path}")
    print(f"导出目录: {args.export_dir}")
    
    if args.action == 'export':
        exporter = DataExporter(args.db_path, args.export_dir)
        exporter.export_all()
    else:
        importer = DataImporter(args.db_path, args.export_dir)
        importer.import_all()


if __name__ == "__main__":
    main()