#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试套件：数据库和基础模块
"""

import unittest
import os
import sys
from pathlib import Path
import sqlite3
from datetime import datetime

# 添加 scripts 目录到路径
script_dir = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(script_dir))

from db_init import DatabaseInitializer
from concept_manager import ConceptManager


class TestDatabaseInit(unittest.TestCase):
    """测试数据库初始化"""
    
    def setUp(self):
        """测试前准备"""
        self.test_db = "test_dragon_stock.db"
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def test_init_database(self):
        """测试数据库初始化"""
        initializer = DatabaseInitializer(self.test_db)
        initializer.init_database()
        
        # 检查数据库文件是否创建
        self.assertTrue(os.path.exists(self.test_db))
        
        # 检查所有表是否创建
        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = [
            'market_sentiment',
            'stock_daily',
            'stock_info',
            'stock_concept',
            'concept_daily',
            'stock_events'
        ]
        
        for table in expected_tables:
            self.assertIn(table, tables, f"表 {table} 未创建")
        
        conn.close()
    
    def test_table_structure(self):
        """测试表结构"""
        initializer = DatabaseInitializer(self.test_db)
        initializer.init_database()
        
        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        
        # 检查 stock_daily 表结构
        cursor.execute("PRAGMA table_info(stock_daily)")
        columns = [row[1] for row in cursor.fetchall()]
        
        required_columns = [
            'trade_date', 'stock_code', 'stock_name', 'close_price',
            'change_percent', 'is_limit_up', 'streak_days'
        ]
        
        for col in required_columns:
            self.assertIn(col, columns, f"列 {col} 不存在")
        
        conn.close()


class TestConceptManager(unittest.TestCase):
    """测试概念管理器"""
    
    def setUp(self):
        """测试前准备"""
        self.test_db = "test_dragon_stock.db"
        self.test_config = "test_concepts.json"
        
        # 清理旧文件
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        
        # 初始化数据库
        initializer = DatabaseInitializer(self.test_db)
        initializer.init_database()
        
        # 创建测试配置文件（简化格式：只有层级和描述）
        import json
        test_concepts = {
            "测试大类1": {
                "description": "测试用大类1（测试环节）",
                "subconcepts": {
                    "测试概念1": {
                        "description": "测试细分概念1（产业链上游）"
                    }
                }
            },
            "测试大类2": {
                "description": "测试用大类2（测试环节）",
                "subconcepts": {
                    "测试概念2": {
                        "description": "测试细分概念2（产业链中游）"
                    }
                }
            }
        }
        with open(self.test_config, 'w', encoding='utf-8') as f:
            json.dump(test_concepts, f, ensure_ascii=False)
        
        # 手动添加股票-概念关系到数据库
        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        test_mappings = [
            ('000001', '测试概念1', 1, '测试大类1/测试概念1'),
            ('000002', '测试概念1', 1, '测试大类1/测试概念1'),
            ('000003', '测试概念1', 0, '测试大类1/测试概念1'),
            ('000004', '测试概念2', 1, '测试大类2/测试概念2'),
        ]
        for stock_code, concept_name, is_core, note in test_mappings:
            cursor.execute('''
            INSERT OR REPLACE INTO stock_concept 
            (stock_code, concept_name, is_core, note)
            VALUES (?, ?, ?, ?)
            ''', (stock_code, concept_name, is_core, note))
        conn.commit()
        conn.close()
    
    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        if os.path.exists(self.test_config):
            os.remove(self.test_config)
    
    def test_load_concept_config(self):
        """测试加载概念配置"""
        manager = ConceptManager(self.test_db)
        count = manager.load_concept_config(self.test_config)
        
        # 应该加载 2 个细分概念（概念定义数量）
        self.assertEqual(count, 2)
        
        # 检查数据库中的股票-概念关系（已手动添加）
        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM stock_concept")
        db_count = cursor.fetchone()[0]
        conn.close()
        
        self.assertEqual(db_count, 4)
    
    def test_get_concept_stocks(self):
        """测试获取概念股票列表"""
        manager = ConceptManager(self.test_db)
        manager.load_concept_config(self.test_config)
        
        stocks = manager.get_concept_stocks("测试概念1")
        self.assertEqual(len(stocks), 3)
        
        # 检查核心标的排在前面
        self.assertEqual(stocks[0]['is_core'], 1)
    
    def test_get_stock_concepts(self):
        """测试获取股票关联概念"""
        manager = ConceptManager(self.test_db)
        manager.load_concept_config(self.test_config)
        
        concepts = manager.get_stock_concepts("000001")
        self.assertEqual(len(concepts), 1)
        self.assertEqual(concepts[0]['concept_name'], "测试概念1")
    
    def test_calculate_concept_daily(self):
        """测试计算概念日统计"""
        manager = ConceptManager(self.test_db)
        manager.load_concept_config(self.test_config)
        
        # 插入测试数据
        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        
        test_date = "2026-02-25"
        cursor.execute('''
        INSERT INTO stock_daily 
        (trade_date, stock_code, stock_name, close_price, change_percent, 
         turnover, is_limit_up, pre_close)
        VALUES 
        (?, '000001', '测试股1', 10.0, 0.05, 100000000, 0, 9.5),
        (?, '000002', '测试股2', 20.0, 0.10, 200000000, 1, 18.0),
        (?, '000003', '测试股3', 15.0, 0.03, 150000000, 0, 14.5)
        ''', (test_date, test_date, test_date))
        conn.commit()
        conn.close()
        
        # 计算统计
        count = manager.calculate_concept_daily(test_date)
        self.assertGreater(count, 0)
        
        # 检查统计结果
        stats = manager.get_concept_stats("测试概念1", test_date)
        self.assertIsNotNone(stats)
        self.assertEqual(stats['stock_count'], 3)
        self.assertEqual(stats['limit_up_count'], 1)


class TestQueryService(unittest.TestCase):
    """测试查询服务"""
    
    def setUp(self):
        """测试前准备"""
        self.test_db = "test_dragon_stock.db"
        
        # 清理旧文件
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
        
        # 初始化数据库
        initializer = DatabaseInitializer(self.test_db)
        initializer.init_database()
        
        # 插入测试数据
        conn = sqlite3.connect(self.test_db)
        cursor = conn.cursor()
        
        test_date = "2026-02-25"
        
        # 市场情绪数据
        cursor.execute('''
        INSERT INTO market_sentiment 
        (trade_date, limit_up_count, limit_down_count, max_streak, total_turnover)
        VALUES (?, 50, 5, 3, 10000.0)
        ''', (test_date,))
        
        # 个股数据
        cursor.execute('''
        INSERT INTO stock_daily 
        (trade_date, stock_code, stock_name, market, close_price, change_percent, 
         turnover, is_limit_up, streak_days, pre_close, open_price, high_price, low_price,
         change_amount, volume, turnover_rate)
        VALUES (?, '000001', '测试股1', 'SZ', 10.0, 0.10, 500000000, 1, 2, 
                9.0, 9.5, 10.5, 9.0, 1.0, 5000000, 5.0)
        ''', (test_date,))
        
        # 概念关联
        cursor.execute('''
        INSERT INTO stock_concept (stock_code, concept_name, is_core)
        VALUES ('000001', '测试概念', 1)
        ''')
        
        conn.commit()
        conn.close()
    
    def tearDown(self):
        """测试后清理"""
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
    
    def test_get_market_status(self):
        """测试获取市场状态"""
        from query_service import QueryService
        
        service = QueryService(self.test_db)
        status = service.get_market_status("2026-02-25")
        
        self.assertIsNotNone(status)
        self.assertEqual(status['limit_up_count'], 50)
        self.assertEqual(status['market_phase'], "增量主升")
    
    def test_get_stock_with_concept(self):
        """测试获取个股信息"""
        from query_service import QueryService
        
        service = QueryService(self.test_db)
        stock = service.get_stock_with_concept("000001", "2026-02-25")
        
        self.assertIsNotNone(stock)
        self.assertEqual(stock['stock_name'], "测试股1")
        self.assertEqual(stock['is_limit_up'], 1)
        self.assertEqual(stock['streak_days'], 2)
        self.assertEqual(len(stock['concepts']), 1)
    
    def test_get_stock_popularity_rank(self):
        """测试人气榜查询"""
        from query_service import QueryService
        
        service = QueryService(self.test_db)
        popularity = service.get_stock_popularity_rank("2026-02-25", 10)
        
        self.assertGreater(len(popularity), 0)
        self.assertEqual(popularity[0]['rank'], 1)


def run_tests():
    """运行所有测试"""
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseInit))
    suite.addTests(loader.loadTestsFromTestCase(TestConceptManager))
    suite.addTests(loader.loadTestsFromTestCase(TestQueryService))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 返回测试结果
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
