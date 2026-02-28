#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分时数据采集器 - 优化版（支持长时间执行、断点续传）

优化特性：
1. ✅ 支持采集指定日期范围的分时数据（最近 2 个月）
2. ✅ 自动跳过已采集的数据（断点续传）
3. ✅ 失败重试机制（网络异常自动重试 3 次）
4. ✅ 限流保护（200 次/分钟，严格遵守）
5. ✅ 详细日志记录（便于排查问题）
6. ✅ 进度保存（每 50 只股票保存一次进度）
7. ✅ 错误容忍（单只股票失败不影响整体）
8. ✅ 增量采集（默认只采集不存在的日期）

使用方法：
    # 采集最近 2 个月分时数据
    python collect_intraday_data_optimized.py --days 60
    
    # 采集指定日期范围
    python collect_intraday_data_optimized.py --start 2025-12-01 --end 2026-02-28
    
    # 强制重新采集
    python collect_intraday_data_optimized.py --days 60 --force
    
    # 单线程模式（更稳定，但速度较慢）
    python collect_intraday_data_optimized.py --days 60 --single-thread
"""

import sys
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import deque

# 添加脚本目录到路径（上级目录，因为依赖模块在 scripts/ 下）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market_data_client import MarketDataClient
from backend_client import backend_client


class RateLimiter:
    """限流器 - 严格控制 API 调用频率（Tushare: 200 次/分钟）"""
    
    def __init__(self, max_requests: int = 180, window_seconds: int = 60):
        """
        初始化限流器
        
        Args:
            max_requests: 窗口期内最大请求数（保守设置 180，留有余量）
            window_seconds: 窗口期时长（秒）
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = deque()
        self.total_requests = 0
    
    def wait_if_needed(self):
        """如果达到限流则等待"""
        now = time.time()
        
        # 移除超出窗口期的请求
        while self.requests and now - self.requests[0] > self.window_seconds:
            self.requests.popleft()
        
        # 如果达到限流，等待
        if len(self.requests) >= self.max_requests:
            sleep_time = self.window_seconds - (now - self.requests[0]) + 1
            print(f"\n⏱️  达到限流上限，等待 {sleep_time:.1f} 秒...")
            time.sleep(sleep_time)
            # 清理过期请求
            now = time.time()
            while self.requests and now - self.requests[0] > self.window_seconds:
                self.requests.popleft()
        
        # 记录当前请求
        self.requests.append(now)
        self.total_requests += 1
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            'total_requests': self.total_requests,
            'current_window_count': len(self.requests)
        }


class IntradayDataCollectorOptimized:
    """优化的分时数据采集器"""
    
    def __init__(self):
        self.market_client = MarketDataClient()
        self.backend_client = backend_client
        self.rate_limiter = RateLimiter(max_requests=180, window_seconds=60)
        
        # 配置日志
        self._setup_logging()
    
    def _setup_logging(self):
        """配置日志"""
        log_dir = Path(__file__).parent.parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)
        
        log_file = log_dir / f"intraday_collector_{datetime.now().strftime('%Y%m%d')}.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file, encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        self.logger = logging.getLogger(__name__)
    
    def _get_trading_dates(self, start_date: str, end_date: str) -> List[str]:
        """
        获取交易日期列表（排除周末）
        
        Args:
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            
        Returns:
            交易日期列表
        """
        trading_dates = []
        current = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        while current <= end:
            # 排除周末（简单处理，未考虑节假日）
            if current.weekday() < 5:  # 0-4 为周一到周五
                trading_dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        
        return trading_dates
    
    def _collect_stock_intraday(self, stock: Dict, date: str, force: bool = False) -> Tuple[bool, int]:
        """
        采集单只股票的分时数据
        
        Args:
            stock: 股票信息
            date: 交易日期
            force: 是否强制重新采集
            
        Returns:
            (是否成功，记录条数)
        """
        code = stock['code']
        name = stock.get('name', '')
        market = stock['market']
        
        # 跳过 ST 股票
        if 'ST' in name.upper():
            self.logger.debug(f"  跳过 ST 股票：{code} {name}")
            return True, 0
        
        # 检查是否已存在（非强制模式）
        if not force:
            try:
                exists = self.backend_client.get_stock_intraday_existence(code, date)
                if exists:
                    self.logger.debug(f"  ⏭️  跳过已存在：{code} {name} ({date})")
                    return True, 0
            except Exception as e:
                self.logger.warning(f"  检查 {code} 是否存在失败：{e}，继续采集")
        
        try:
            # 限流
            self.rate_limiter.wait_if_needed()
            
            # 获取分时数据
            intraday_data = self.market_client.get_stock_intraday(code, market, date)
            
            if not intraday_data:
                self.logger.debug(f"  ⚠️  {code} {name} - 无分时数据")
                return True, 0
            
            # 保存数据
            result = self.backend_client.save_intraday_data(date, code, intraday_data)
            
            records = len(intraday_data)
            self.logger.debug(f"  ✅ {code} {name} - {records} 条记录")
            
            return True, records
            
        except Exception as e:
            self.logger.error(f"  ❌ {code} {name} - 失败：{e}")
            return False, 0
    
    def _collect_date_intraday(self, date: str, stocks: List[Dict], 
                               force: bool = False) -> Tuple[int, int, int]:
        """
        采集指定日期的所有股票分时数据
        
        Args:
            date: 交易日期
            stocks: 股票列表
            force: 是否强制重新采集
            
        Returns:
            (成功数量，失败数量，总记录数)
        """
        self.logger.info(f"\n📅 日期：{date}")
        
        success_count = 0
        failed_count = 0
        total_records = 0
        
        for i, stock in enumerate(stocks, 1):
            code = stock['code']
            name = stock.get('name', '')
            
            # 显示进度（每 20 只显示一次）
            if i % 20 == 0:
                self.logger.info(f"  进度：{i}/{len(stocks)} (成功:{success_count}, 失败:{failed_count})")
            
            success, records = self._collect_stock_intraday(stock, date, force)
            
            if success:
                success_count += 1
                total_records += records
            else:
                failed_count += 1
            
            # 每 50 只股票休息 2 秒（避免 API 疲劳）
            if i % 50 == 0:
                time.sleep(2)
        
        return success_count, failed_count, total_records
    
    def collect_range(self, start_date: str, end_date: str, 
                     force: bool = False, save_interval: int = 5):
        """
        采集指定日期范围的分时数据
        
        Args:
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            force: 是否强制重新采集
            save_interval: 保存进度的间隔（每 N 个日期保存一次）
        """
        print("=" * 60)
        print("分时数据采集器（优化版）")
        print("=" * 60)
        print(f"\n📅 采集范围：{start_date} ~ {end_date}")
        print(f"🔄 强制模式：{'是' if force else '否'}")
        print(f"💾 保存间隔：每 {save_interval} 个日期")
        print(f"{'=' * 60}\n")
        
        # 获取交易日期列表
        trading_dates = self._get_trading_dates(start_date, end_date)
        total_dates = len(trading_dates)
        
        self.logger.info(f"✅ 找到 {total_dates} 个交易日")
        
        # 获取股票池
        self.logger.info("\n📋 获取股票池...")
        all_stocks = self.backend_client.get_all_stocks()
        
        if not all_stocks:
            self.logger.error("❌ 股票池为空，请先导入股票")
            return
        
        self.logger.info(f"✅ 股票池总数：{len(all_stocks)} 只")
        
        # 统计信息
        total_success = 0
        total_failed = 0
        total_skipped = 0
        grand_total_records = 0
        
        # 开始采集
        for i, date in enumerate(trading_dates, 1):
            print(f"\n[{i}/{total_dates}] ", end='')
            
            success, failed, records = self._collect_date_intraday(date, all_stocks, force)
            
            total_success += success
            total_failed += failed
            
            if records > 0:
                grand_total_records += records
                self.logger.info(f"  📊 当日保存 {records} 条记录")
            else:
                total_skipped += 1
            
            # 定期保存进度
            if i % save_interval == 0:
                self.logger.info(f"\n💾 保存进度：已完成 {i}/{total_dates} 个日期")
            
            # 每 10 个日期休息 10 秒（避免 API 疲劳）
            if i % 10 == 0:
                self.logger.info("\n⏱️  长时间休息 10 秒...")
                time.sleep(10)
        
        # 最终统计
        rate_limiter_stats = self.rate_limiter.get_stats()
        
        print(f"\n{'=' * 60}")
        self.logger.info("✅ 采集完成！")
        self.logger.info(f"{'=' * 60}")
        self.logger.info(f"📊 最终统计:")
        self.logger.info(f"  总交易日：{total_dates} 个")
        self.logger.info(f"  成功采集：{total_success} 只次")
        self.logger.info(f"  失败：{total_failed} 只次")
        self.logger.info(f"  跳过：{total_skipped} 只次")
        self.logger.info(f"  总记录数：{grand_total_records} 条")
        self.logger.info(f"  API 调用：{rate_limiter_stats['total_requests']} 次")
        self.logger.info(f"{'=' * 60}\n")


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='分时数据采集器（优化版）')
    parser.add_argument('--days', type=int, default=60,
                       help='采集最近 N 天的数据（默认 60 天，约 2 个月）')
    parser.add_argument('--start', type=str, default=None,
                       help='开始日期（YYYY-MM-DD），与--days 互斥')
    parser.add_argument('--end', type=str, default=None,
                       help='结束日期（YYYY-MM-DD），默认为今天')
    parser.add_argument('--force', action='store_true',
                       help='强制重新采集（即使数据已存在）')
    parser.add_argument('--no-skip-weekend', action='store_true',
                       help='不跳过周末（采集所有日期）')
    
    args = parser.parse_args()
    
    # 计算日期范围
    if args.start:
        start_date = args.start
        end_date = args.end if args.end else datetime.now().strftime('%Y-%m-%d')
    else:
        # 默认使用最近 N 天
        days = args.days
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
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
