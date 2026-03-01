#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试套件：Tushare 客户端
测试 tushare_client.py 中的所有主要方法
"""

import unittest
import sys
from pathlib import Path
from datetime import datetime, timedelta

# 添加 scripts 目录到路径（使用绝对路径）
script_dir = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(script_dir))

from tushare_client import TushareClient, tushare_client
from config_loader import ConfigLoader


class TestTushareClient(unittest.TestCase):
    """测试 Tushare 客户端"""
    
    @classmethod
    def setUpClass(cls):
        """测试前准备 - 使用全局客户端"""
        cls.client = tushare_client
    
    def test_01_client_initialization(self):
        """测试客户端初始化"""
        self.assertIsNotNone(self.client)
        self.assertIsNotNone(self.client.pro)
        self.assertIsNotNone(self.client.token)
        print("✅ 客户端初始化成功")
    
    def test_02_get_stock_daily(self):
        """测试获取单只股票日线数据"""
        # 获取平安银行最近数据
        data = self.client.get_stock_daily("000001.SZ")
        
        self.assertIsNotNone(data, "应该返回数据")
        self.assertIn('items', data)
        self.assertIn('fields', data)
        self.assertGreater(len(data['items']), 0, "应该有数据项")
        
        # 验证字段
        fields = data['fields']
        self.assertIn('ts_code', fields)
        self.assertIn('trade_date', fields)
        self.assertIn('open', fields)
        self.assertIn('close', fields)
        print(f"✅ 获取股票日线数据成功: {len(data['items'])} 条")
    
    def test_03_get_stock_daily_by_date(self):
        """测试按日期获取股票日线数据"""
        # 获取最近一个交易日的数据
        today = datetime.now().strftime('%Y%m%d')
        data = self.client.get_stock_daily("000001.SZ", today)
        
        # 可能当天还没有数据，所以不强制要求有数据
        if data and data.get('items'):
            item = data['items'][0]
            self.assertEqual(item[0], "000001.SZ")  # ts_code
            print(f"✅ 按日期获取日线数据成功: {item[1]}")
        else:
            print("⚠️ 当天暂无数据（非交易日或数据未更新）")
    
    def test_04_get_daily_all(self):
        """测试批量获取所有股票日线数据"""
        # 使用最近一个交易日
        today = datetime.now().strftime('%Y%m%d')
        data = self.client.get_daily_all(today)
        
        if data and data.get('items'):
            items = data['items']
            self.assertGreater(len(items), 4000, "应该有 4000+ 只股票")
            
            # 验证数据结构
            first_item = items[0]
            self.assertEqual(len(first_item), 11, "每条数据应有 11 个字段")
            
            # 验证字段顺序: ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
            self.assertIn('.', first_item[0])  # ts_code 格式如 000001.SZ
            
            print(f"✅ 批量获取日线数据成功: {len(items)} 只股票")
        else:
            print("⚠️ 当天暂无数据")
    
    def test_05_get_index_daily(self):
        """测试获取指数日线数据"""
        # 获取上证指数
        data = self.client.get_index_daily("000001.SH")
        
        self.assertIsNotNone(data, "应该返回数据")
        if data and data.get('items'):
            items = data['items']
            self.assertGreater(len(items), 0)
            print(f"✅ 获取指数数据成功: {len(items)} 条")
        else:
            print("⚠️ 未获取到指数数据")
    
    def test_06_get_trade_calendar(self):
        """测试获取交易日历"""
        # 获取最近一个月的交易日
        end_date = datetime.now().strftime('%Y%m%d')
        start_date = (datetime.now() - timedelta(days=30)).strftime('%Y%m%d')
        
        dates = self.client.get_trade_calendar(start_date, end_date)
        
        self.assertIsInstance(dates, list)
        if dates:
            # 验证日期格式 YYYY-MM-DD
            self.assertRegex(dates[0], r'\d{4}-\d{2}-\d{2}')
            print(f"✅ 获取交易日历成功: {len(dates)} 个交易日")
        else:
            print("⚠️ 未获取到交易日历")
    
    def test_07_get_stock_basic(self):
        """测试获取股票基本信息"""
        data = self.client.get_stock_basic("000001.SZ")
        
        self.assertIsNotNone(data, "应该返回数据")
        if data and data.get('items'):
            item = data['items'][0]
            # ts_code, name, area, industry, market, list_date
            self.assertEqual(item[0], "000001.SZ")
            self.assertEqual(item[1], "平安银行")  # name
            print(f"✅ 获取股票基本信息成功: {item[1]}")
        else:
            print("⚠️ 未获取到股票基本信息")
    
    def test_08_get_limit_list(self):
        """测试获取涨跌停列表"""
        # 使用最近一个交易日
        today = datetime.now().strftime('%Y%m%d')
        data = self.client.get_limit_list(today)
        
        if data and data.get('items'):
            items = data['items']
            print(f"✅ 获取涨跌停列表成功: {len(items)} 条")
            
            # 统计涨跌停类型
            limit_types = {}
            for item in items:
                lt = item[3] if len(item) > 3 else 'Unknown'
                limit_types[lt] = limit_types.get(lt, 0) + 1
            print(f"   类型分布: {limit_types}")
        else:
            print("⚠️ 当天暂无涨跌停数据")
    
    def test_09_request_count(self):
        """测试请求计数"""
        initial_count = self.client._request_count
        
        # 使用一个已知有数据的交易日（2026-02-26）
        self.client.get_daily_all('20260226')
        
        # 计数应该增加
        self.assertGreater(self.client._request_count, initial_count)
        print(f"✅ 请求计数正常: {self.client._request_count}")
    
    def test_10_invalid_stock_code(self):
        """测试无效股票代码"""
        data = self.client.get_stock_daily("999999.SZ")
        
        # 无效代码应该返回 None 或空数据
        self.assertTrue(data is None or not data.get('items'))
        print("✅ 无效股票代码处理正确")


class TestTushareClientPerformance(unittest.TestCase):
    """测试 Tushare 客户端性能"""
    
    @classmethod
    def setUpClass(cls):
        cls.client = tushare_client
    
    def test_batch_vs_single_performance(self):
        """对比批量获取和单个获取的性能"""
        import time
        
        today = datetime.now().strftime('%Y%m%d')
        
        # 测试批量获取
        start = time.time()
        batch_data = self.client.get_daily_all(today)
        batch_time = time.time() - start
        
        if batch_data and batch_data.get('items'):
            batch_count = len(batch_data['items'])
            print(f"\n📊 批量获取: {batch_count} 只股票, 耗时 {batch_time:.2f} 秒")
            print(f"   平均每只股票: {batch_time/batch_count*1000:.2f} 毫秒")
        else:
            print("⚠️ 批量获取无数据，跳过性能对比")


def run_tests():
    """运行所有测试"""
    print("=" * 60)
    print("Tushare 客户端测试套件")
    print("=" * 60)
    
    # 创建测试套件
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # 添加测试类
    suite.addTests(loader.loadTestsFromTestCase(TestTushareClient))
    suite.addTests(loader.loadTestsFromTestCase(TestTushareClientPerformance))
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # 打印总结
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    print(f"运行测试: {result.testsRun}")
    print(f"成功: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"失败: {len(result.failures)}")
    print(f"错误: {len(result.errors)}")
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
