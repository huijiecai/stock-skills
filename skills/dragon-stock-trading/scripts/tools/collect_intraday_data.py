#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分时数据采集器 - 批量查询优化版

优化特性：
1. ✅ 复用 collect_stock_data 的批量查询逻辑
2. ✅ 按股票遍历，每只股票批量获取多天数据
3. ✅ 自动跳过已采集的数据（断点续传）
4. ✅ 增量采集（默认只采集不存在的日期）

使用方法：
    # 采集最近 2 个月分时数据
    python collect_intraday_data.py --days 60
    
    # 采集指定日期范围
    python collect_intraday_data.py --start 2025-12-01 --end 2026-02-28
    
    # 强制重新采集
    python collect_intraday_data.py --days 60 --force
"""

import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import List

# 添加脚本目录到路径（上级目录，因为依赖模块在 scripts/ 下）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend_client import backend_client
from collect_stock_data import stock_data_collector


class IntradayDataCollectorOptimized:
    """分时数据采集器（复用 collect_stock_data 的批量查询逻辑）"""
    
    def __init__(self):
        self._setup_logging()
    
    def _setup_logging(self):
        """配置日志（仅控制台输出）"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def collect_range(self, start_date: str, end_date: str, 
                     force: bool = False, reverse: bool = True):
        """
        采集所有股票指定日期范围的分时数据
        
        复用 collect_stock_data.collect_intraday 的批量查询逻辑
        
        Args:
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            force: 是否强制重新采集
            reverse: 是否从新到旧采集（默认 True，从新到旧）
        """
        print("=" * 60)
        print("分时数据采集器（批量查询优化版）")
        print("=" * 60)
        print(f"\n📅 采集范围：{start_date} ~ {end_date}")
        print(f"🔄 强制模式：{'是' if force else '否'}")
        print(f"📅 采集顺序：{'从新到旧' if reverse else '从旧到新'}")
        print("=" * 60 + "\n")
        
        # 获取股票池
        self.logger.info("📋 获取股票池...")
        all_stocks = backend_client.get_all_stocks()
        
        if not all_stocks:
            self.logger.error("❌ 股票池为空，请先导入股票")
            return
        
        total_stocks = len(all_stocks)
        self.logger.info(f"✅ 股票池总数：{total_stocks} 只")
        
        # 统计信息
        total_success = 0
        total_failed = 0
        
        # 遍历所有股票，调用 collect_stock_data.collect_intraday
        for i, stock in enumerate(all_stocks, 1):
            code = stock['code']
            name = stock.get('name', '')
            
            print(f"\n[{i}/{total_stocks}] {code} {name}")
            
            try:
                # 复用 collect_stock_data 的批量查询方法
                success_count = stock_data_collector.collect_intraday(
                    code, start_date, end_date, force
                )
                
                if success_count > 0:
                    total_success += success_count
                else:
                    total_failed += 1
                
            except Exception as e:
                self.logger.error(f"  ❌ 采集失败: {e}")
                total_failed += 1
            
            # 每 10 只股票休息 2 秒（避免 API 疲劳）
            if i % 10 == 0:
                self.logger.info(f"  ⏱️ 休息 2 秒... (已完成 {i}/{total_stocks})")
                time.sleep(2)
        
        # 最终统计
        print(f"\n{'=' * 60}")
        self.logger.info("✅ 采集完成！")
        self.logger.info(f"{'=' * 60}")
        self.logger.info(f"📊 最终统计:")
        self.logger.info(f"  股票总数：{total_stocks} 只")
        self.logger.info(f"  成功采集：{total_success} 天")
        self.logger.info(f"  失败：{total_failed} 只")
        self.logger.info(f"{'=' * 60}\n")


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='分时数据采集器（批量查询优化版）')
    parser.add_argument('--days', type=int, default=60,
                       help='采集最近 N 天的数据（默认 60 天）')
    parser.add_argument('--start', type=str, default=None,
                       help='开始日期（YYYY-MM-DD），与--days 互斥')
    parser.add_argument('--end', type=str, default=None,
                       help='结束日期（YYYY-MM-DD），默认为今天')
    parser.add_argument('--force', action='store_true',
                       help='强制重新采集（即使数据已存在）')
    
    args = parser.parse_args()
    
    # 计算日期范围
    if args.start:
        start_date = args.start
        end_date = args.end if args.end else datetime.now().strftime('%Y-%m-%d')
    else:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
    
    # 创建采集器并执行
    collector = IntradayDataCollectorOptimized()
    
    try:
        collector.collect_range(
            start_date=start_date,
            end_date=end_date,
            force=args.force
        )
        print("\n🎉 分时数据采集完成！")
        sys.exit(0)
        
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断采集")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 采集失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


intraday_collector = IntradayDataCollectorOptimized()
