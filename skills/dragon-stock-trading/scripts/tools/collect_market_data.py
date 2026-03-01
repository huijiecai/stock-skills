#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据采集器 - 优化版

优化特性：
1. ✅ 支持采集指定日期范围的数据
2. ✅ 使用真实交易日历（排除节假日）
3. ✅ 批量获取行情数据（一次请求获取全部，约1秒）
4. ✅ 自动跳过已采集的日期（断点续传）
5. ✅ 精确涨停判断（基于涨停价计算）

使用方法：
    # 采集指定日期范围
    python collect_market_data.py --start 2026-01-05 --end 2026-02-28
    
    # 强制重新采集
    python collect_market_data.py --start 2026-01-05 --end 2026-02-28 --force
"""

import sys
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# 添加脚本目录到路径（上级目录，因为依赖模块在 scripts/ 下）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from market_data_client import market_data_client
from backend_client import backend_client
from tushare_client import tushare_client
from stock_utils import is_limit_up, is_limit_down


class MarketDataCollectorOptimized:
    """优化的市场数据采集器"""
    
    def __init__(self):
        # 配置日志
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
    
    def _get_trading_dates(self, start_date: str, end_date: str) -> List[str]:
        """
        获取交易日期列表（使用 Tushare 交易日历）
        
        Args:
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            
        Returns:
            交易日期列表
        """
        # 使用 Tushare 交易日历接口获取真实的交易日
        trading_dates = tushare_client.get_trade_calendar(start_date, end_date)
        
        if trading_dates:
            self.logger.info(f"获取到 {len(trading_dates)} 个交易日（{start_date} ~ {end_date}）")
            return trading_dates
        
        # 如果 API 调用失败，回退到简单逻辑（排除周末）
        self.logger.warning("交易日历 API 调用失败，使用简单周末排除逻辑")
        dates = []
        current = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        while current <= end:
            # 排除周末（简单处理，未考虑节假日）
            if current.weekday() < 5:  # 0-4 为周一到周五
                dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        
        return dates
    
    def _check_date_exists(self, date: str) -> bool:
        """
        检查指定日期的数据是否已存在
        
        Args:
            date: 交易日期
            
        Returns:
            True if exists, False otherwise
        """
        try:
            return backend_client.check_market_data_exists(date)
        except Exception as e:
            self.logger.warning(f"检查日期 {date} 是否存在失败：{e}")
            return False
    
    def _collect_date_data(self, date: str, force: bool = False) -> Tuple[bool, int]:
        """
        采集单个日期的数据
        
        Args:
            date: 交易日期
            force: 是否强制重新采集
            
        Returns:
            (是否成功，采集的股票数量)
        """
        import time
        
        try:
            # 检查是否已存在（非强制模式）
            if not force:
                exists = self._check_date_exists(date)
                if exists:
                    self.logger.info(f"⏭️  跳过已存在日期：{date}")
                    return True, 0
            
            self.logger.info(f"\n📅 开始采集：{date}")
            
            # Step 1: 获取市场概况（带重试，最多5次）
            self.logger.info("  Step 1: 获取市场概况...")
            market_data = None
            for attempt in range(5):
                market_data = market_data_client.get_market_snapshot(date)
                if market_data:
                    break
                if attempt < 4:
                    self.logger.warning(f"  ⚠️ 获取市场概况失败，重试 {attempt + 2}/5...")
                    time.sleep(2)
            
            if not market_data:
                self.logger.error("  ❌ 获取市场概况失败（已重试5次），停止采集")
                return False, 0
            
            self.logger.info(f"  ✅ 涨停：{market_data['limit_up_count']} 只，"
                           f"跌停：{market_data['limit_down_count']} 只")
            
            # Step 2: 获取股票池
            self.logger.info("  Step 2: 获取股票池...")
            all_stocks = backend_client.get_all_stocks()
            
            if not all_stocks:
                self.logger.error("  ❌ 股票池为空，请先导入股票")
                return False, 0
            
            self.logger.info(f"  ✅ 股票池总数：{len(all_stocks)} 只")
            
            # Step 3: 批量获取所有股票行情（带重试，最多5次）
            self.logger.info("  Step 3: 批量获取行情数据...")
            all_quotes = None
            for attempt in range(5):
                all_quotes = market_data_client.get_daily_all(date)
                if all_quotes:
                    break
                if attempt < 4:
                    self.logger.warning(f"  ⚠️ 批量获取行情失败，重试 {attempt + 2}/5...")
                    time.sleep(3)
            
            if not all_quotes:
                self.logger.error("  ❌ 批量获取行情数据失败（已重试5次），停止采集")
                return False, 0
            
            self.logger.info(f"  ✅ 获取到 {len(all_quotes)} 只股票行情")
            
            # Step 4: 获取每日基本面数据（换手率、量比、估值等）
            self.logger.info("  Step 4: 获取每日基本面数据...")
            daily_basic = market_data_client.get_daily_basic(date)
            if daily_basic:
                self.logger.info(f"  ✅ 获取到 {len(daily_basic)} 只股票基本面数据")
            else:
                self.logger.warning("  ⚠️ 未获取到基本面数据，使用默认值")
            
            # Step 5: 过滤股票池并构建数据
            self.logger.info("  Step 5: 处理股票池数据...")
            stocks_data = []
            pool_limit_up = 0
            pool_limit_down = 0
            
            # 构建股票池代码集合（快速查找）
            pool_codes = {s['code'] for s in all_stocks}
            stock_info = {s['code']: s for s in all_stocks}  # 代码 -> 股票信息
            
            for code, quote in all_quotes.items():
                if code not in pool_codes:
                    continue  # 不在股票池中，跳过
                
                stock = stock_info[code]
                name = stock.get('name', '')
                market = stock.get('market', '')
                
                # 提取数据
                change_percent = quote.get('chp', 0.0)
                close_price = quote.get('ld', 0.0)
                pre_close = quote.get('p', 0.0)
                
                # 精确判断涨停/跌停（使用公共函数）
                limit_up = 1 if is_limit_up(close_price, pre_close, code) else 0
                limit_down = 1 if is_limit_down(close_price, pre_close, code) else 0
                
                stock_data = {
                    "code": code,
                    "name": name,
                    "market": market,
                    "open": quote.get('o', 0.0),
                    "high": quote.get('h', 0.0),
                    "low": quote.get('l', 0.0),
                    "close": close_price,
                    "pre_close": pre_close,
                    "change_percent": change_percent,
                    "volume": quote.get('vol', 0),
                    "turnover": quote.get('amt', 0.0),
                    # 基本面数据
                    "turnover_rate": daily_basic.get(code, {}).get('turnover_rate'),
                    "turnover_rate_f": daily_basic.get(code, {}).get('turnover_rate_f'),
                    "volume_ratio": daily_basic.get(code, {}).get('volume_ratio'),
                    "pe": daily_basic.get(code, {}).get('pe'),
                    "pe_ttm": daily_basic.get(code, {}).get('pe_ttm'),
                    "pb": daily_basic.get(code, {}).get('pb'),
                    "ps": daily_basic.get(code, {}).get('ps'),
                    "ps_ttm": daily_basic.get(code, {}).get('ps_ttm'),
                    "dv_ratio": daily_basic.get(code, {}).get('dv_ratio'),
                    "dv_ttm": daily_basic.get(code, {}).get('dv_ttm'),
                    "total_share": daily_basic.get(code, {}).get('total_share'),
                    "float_share": daily_basic.get(code, {}).get('float_share'),
                    "free_share": daily_basic.get(code, {}).get('free_share'),
                    "total_mv": daily_basic.get(code, {}).get('total_mv'),
                    "circ_mv": daily_basic.get(code, {}).get('circ_mv'),
                    # 涨跌停数据
                    "is_limit_up": limit_up,
                    "is_limit_down": limit_down,
                    "limit_up_time": "",
                    "streak_days": 0,
                }
                
                stocks_data.append(stock_data)
                
                # 统计涨停/跌停
                if limit_up:
                    pool_limit_up += 1
                    self.logger.debug(f"    🔴 涨停: {code} {name} ({change_percent:+.2%})")
                elif limit_down:
                    pool_limit_down += 1
            
            self.logger.info(f"  ✅ 股票池有效数据：{len(stocks_data)} 只")
            self.logger.info(f"  📊 涨停：{pool_limit_up} 只，跌停：{pool_limit_down} 只")
            
            # Step 6: 保存市场情绪
            self.logger.info("  Step 6: 保存市场情绪...")
            result = backend_client.collect_market_sentiment(
                date=date,
                market_data=market_data
            )
            
            if not result.get('success'):
                self.logger.error("  ❌ 市场情绪保存失败")
                return False, 0
            
            self.logger.info(f"  ✅ 市场情绪保存成功")
            
            # Step 7: 逐个保存股票数据
            self.logger.info("  Step 7: 保存股票数据...")
            saved_count = 0
            for stock in stocks_data:
                try:
                    result = backend_client.save_stock_daily(date, stock)
                    if result.get('success'):
                        saved_count += 1
                except Exception as e:
                    self.logger.warning(f"    ⚠️ 保存 {stock.get('code')} 失败: {e}")
            
            self.logger.info(f"  ✅ 股票数据保存成功：{saved_count}/{len(stocks_data)} 只")
            
            return True, saved_count
            
        except Exception as e:
            self.logger.error(f"❌ 采集 {date} 失败：{e}")
            return False, 0
    
    def collect_range(self, start_date: str, end_date: str, 
                     force: bool = False, save_interval: int = 10, reverse: bool = True):
        """
        采集指定日期范围的数据
        
        Args:
            start_date: 开始日期（YYYY-MM-DD）
            end_date: 结束日期（YYYY-MM-DD）
            force: 是否强制重新采集
            save_interval: 保存进度的间隔（每 N 个日期保存一次）
            reverse: 是否从新到旧采集（默认 True，从新到旧）
        """
        print("=" * 60)
        print("市场数据采集器（优化版）")
        print("=" * 60)
        print(f"\n📅 采集范围：{start_date} ~ {end_date}")
        print(f"🔄 强制模式：{'是' if force else '否'}")
        print(f"📅 采集顺序：{'从新到旧' if reverse else '从旧到新'}")
        print(f"💾 保存间隔：每 {save_interval} 个日期")
        print(f"{'=' * 60}\n")
        
        # 获取交易日期列表
        trading_dates = self._get_trading_dates(start_date, end_date)
        
        # 从新到旧采集（默认）
        if reverse:
            trading_dates = list(reversed(trading_dates))
        total_dates = len(trading_dates)
        
        self.logger.info(f"✅ 找到 {total_dates} 个交易日")
        
        # 统计信息
        success_count = 0
        failed_count = 0
        skipped_count = 0
        total_stocks = 0
        
        # 开始采集
        for i, date in enumerate(trading_dates, 1):
            print(f"\n[{i}/{total_dates}] ", end='')
            
            success, saved = self._collect_date_data(date, force)
            
            if success:
                if saved > 0:
                    success_count += 1
                    total_stocks += saved
                else:
                    skipped_count += 1
            else:
                failed_count += 1
            
            # 定期保存进度（断点续传）
            if i % save_interval == 0:
                self.logger.info(f"\n💾 保存进度：已完成 {success_count}/{i} 个日期")
                # 这里可以保存进度到文件，用于断点续传
            
            # 定期休息（避免 API 疲劳）
            if i % 20 == 0:
                self.logger.info("\n⏱️  休息 5 秒...")
                time.sleep(5)
        
        # 最终统计
        print(f"\n{'=' * 60}")
        self.logger.info("✅ 采集完成！")
        self.logger.info(f"{'=' * 60}")
        self.logger.info(f"📊 最终统计:")
        self.logger.info(f"  总交易日：{total_dates} 个")
        self.logger.info(f"  成功：{success_count} 个")
        self.logger.info(f"  跳过：{skipped_count} 个")
        self.logger.info(f"  失败：{failed_count} 个")
        self.logger.info(f"  保存股票：{total_stocks} 只次")
        self.logger.info(f"{'=' * 60}\n")


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='市场数据采集器（优化版）')
    parser.add_argument('--days', type=int, default=60,
                       help='采集最近 N 天的数据（默认 60 天，约 2 个月）')
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
        # 默认使用最近 N 天
        days = args.days
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    # 创建采集器并执行
    collector = MarketDataCollectorOptimized()
    
    try:
        collector.collect_range(
            start_date=start_date,
            end_date=end_date,
            force=args.force
        )
        print("\n🎉 采集任务成功完成！")
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


market_collector = MarketDataCollectorOptimized()
