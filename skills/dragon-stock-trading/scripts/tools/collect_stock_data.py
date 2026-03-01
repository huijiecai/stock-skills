#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单股票数据采集器

功能：
1. 收集指定股票的日线数据
2. 收集指定股票的分时数据
3. 支持指定日期范围
4. 自动获取基本面数据

使用方法：
    # 收集单只股票的日线数据（最近60天）
    python collect_stock_data.py --code 000001 --days 60
    
    # 收集指定日期范围
    python collect_stock_data.py --code 000001 --start 2026-01-01 --end 2026-02-28
    
    # 同时收集日线和分时数据
    python collect_stock_data.py --code 000001 --days 30 --intraday
    
    # 强制重新采集
    python collect_stock_data.py --code 000001 --days 30 --force
"""

import sys
import logging
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tushare_client import tushare_client
from backend_client import backend_client
from market_data_client import market_data_client, get_auction_data
from stock_utils import get_board_type, get_market, get_ts_code, is_limit_up, is_limit_down


class StockDataCollector:
    """单股票数据采集器"""
    
    def __init__(self):
        self._setup_logging()
    
    def _setup_logging(self):
        """配置日志（仅控制台输出）"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[logging.StreamHandler(sys.stdout)]
        )
        self.logger = logging.getLogger(__name__)
    
    def get_trading_dates(self, start_date: str, end_date: str) -> List[str]:
        """获取交易日期列表（带重试，公开方法）"""
        trading_dates = None
        for attempt in range(5):
            trading_dates = tushare_client.get_trade_calendar(start_date, end_date)
            if trading_dates:
                self.logger.info(f"获取到 {len(trading_dates)} 个交易日")
                return trading_dates
            if attempt < 4:
                self.logger.warning(f"交易日历 API 调用失败，重试 {attempt + 2}/5...")
                time.sleep(2)
        
        # 重试5次后仍失败，抛出异常
        raise RuntimeError(f"交易日历 API 调用失败（已重试5次），无法获取 {start_date} ~ {end_date} 的交易日数据")
    
    def _ensure_stock_in_pool(self, code: str) -> Dict:
        """
        确保股票在 stock_pool 和 stock_info 中存在
        
        Args:
            code: 股票代码
            
        Returns:
            股票信息字典 {'name': ..., 'market': ...}
        """
        # 检查股票池
        all_stocks = backend_client.get_all_stocks()
        stock_info = next((s for s in all_stocks if s['code'] == code), None)
        
        if stock_info:
            self.logger.info(f"  ✅ 股票已在池中: {stock_info.get('name', code)}")
            return {
                'name': stock_info.get('name', ''),
                'market': stock_info.get('market', get_market(code))
            }
        
        # 不在池中，从 Tushare 获取信息
        self.logger.info(f"  📥 股票不在池中，从 Tushare 获取信息...")
        
        ts_code = get_ts_code(code)
        basic_info = tushare_client.get_stock_basic(ts_code)
        
        if not basic_info or not basic_info.get('items'):
            self.logger.warning(f"  ⚠️ 未获取到股票基本信息，使用默认值")
            stock_name = ""
        else:
            item = basic_info['items'][0]
            # fields: ts_code, name, area, industry, market(主板/创业板), list_date
            stock_name = item[1] if len(item) > 1 else ""
        
        # market 根据股票代码判断（SH/SZ）
        market = get_market(code)
        
        # 添加到股票池
        board_type = get_board_type(code)
        
        try:
            # 添加到 stock_pool（market 使用 SH/SZ）
            backend_client.add_stock_to_pool(code, stock_name, market, f"自动添加 ({board_type})")
            self.logger.info(f"  ✅ 已添加到股票池: {stock_name or code}")
            
            # 同步到 stock_info
            backend_client.sync_stock_info([{
                'stock_code': code,
                'stock_name': stock_name,
                'market': market,
                'board_type': board_type
            }])
            self.logger.info(f"  ✅ 已同步到 stock_info: {board_type}")
            
        except Exception as e:
            self.logger.warning(f"  ⚠️ 添加股票信息失败: {e}")
        
        return {
            'name': stock_name,
            'market': market
        }
    
    def collect_daily(self, code: str, start_date: str, end_date: str, force: bool = False) -> int:
        """
        收集单只股票的日线数据（批量查询）
        
        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            force: 是否强制重新采集
            
        Returns:
            成功采集的天数
        """
        print("=" * 60)
        print(f"单股票日线数据采集器")
        print("=" * 60)
        print(f"\n📊 股票代码：{code}")
        print(f"📅 采集范围：{start_date} ~ {end_date}")
        print(f"🔄 强制模式：{'是' if force else '否'}")
        print("=" * 60 + "\n")
        
        ts_code = get_ts_code(code)
        start_compact = start_date.replace('-', '')
        end_compact = end_date.replace('-', '')
        
        try:
            # Step 0: 确保股票在股票池中
            self.logger.info("Step 0: 检查股票池...")
            stock_info = self._ensure_stock_in_pool(code)
            stock_name = stock_info.get('name', '')
            market = stock_info.get('market', get_market(code))
            
            # Step 1: 一次性获取日期范围内的所有日线数据
            self.logger.info("Step 1: 批量获取日线数据...")
            daily_data = None
            for attempt in range(5):
                daily_data = tushare_client.get_stock_daily(
                    ts_code=ts_code,
                    start_date=start_compact,
                    end_date=end_compact
                )
                if daily_data and daily_data.get('items'):
                    break
                if attempt < 4:
                    self.logger.warning(f"  重试 {attempt + 2}/5...")
                    time.sleep(2)
            
            if not daily_data or not daily_data.get('items'):
                self.logger.error("❌ 未获取到日线数据")
                return 0
            
            self.logger.info(f"  ✅ 获取到 {len(daily_data['items'])} 条日线数据")
            
            # Step 2: 一次性获取日期范围内的所有基本面数据
            self.logger.info("Step 2: 批量获取基本面数据...")
            basic_data = None
            for attempt in range(5):
                basic_data = tushare_client.get_daily_basic(
                    ts_code=ts_code,
                    start_date=start_compact,
                    end_date=end_compact
                )
                if basic_data:
                    break
                if attempt < 4:
                    self.logger.warning(f"  重试 {attempt + 2}/5...")
                    time.sleep(2)
            
            if basic_data:
                self.logger.info(f"  ✅ 获取到 {len(basic_data)} 条基本面数据")
            else:
                self.logger.warning("  ⚠️ 未获取到基本面数据")
                basic_data = {}
            
            # Step 3: 合并数据并保存
            self.logger.info("Step 3: 保存数据...")
            
            # 解析日线数据
            fields = daily_data['fields']
            items = daily_data['items']
            
            success_count = 0
            
            for item in items:
                data_dict = dict(zip(fields, item))
                trade_date_raw = str(data_dict.get('trade_date', ''))
                date = f"{trade_date_raw[:4]}-{trade_date_raw[4:6]}-{trade_date_raw[6:8]}"
                
                # 获取对应日期的基本面数据
                basic = basic_data.get(trade_date_raw, {})
                
                # 判断涨跌停（使用公共函数）
                close_price = data_dict.get('close', 0)
                pre_close = data_dict.get('pre_close', 0)
                
                limit_up = 1 if is_limit_up(close_price, pre_close, code) else 0
                limit_down = 1 if is_limit_down(close_price, pre_close, code) else 0
                
                # 构建保存数据
                stock_data = {
                    "code": code,
                    "name": stock_name,
                    "market": market,
                    "open": data_dict.get('open', 0),
                    "high": data_dict.get('high', 0),
                    "low": data_dict.get('low', 0),
                    "close": close_price,
                    "pre_close": pre_close,
                    "change_percent": data_dict.get('pct_chg', 0) / 100,
                    "volume": data_dict.get('vol', 0),
                    "turnover": data_dict.get('amount', 0) * 1000,
                    "turnover_rate": basic.get('turnover_rate'),
                    "turnover_rate_f": basic.get('turnover_rate_f'),
                    "volume_ratio": basic.get('volume_ratio'),
                    "pe": basic.get('pe'),
                    "pe_ttm": basic.get('pe_ttm'),
                    "pb": basic.get('pb'),
                    "ps": basic.get('ps'),
                    "ps_ttm": basic.get('ps_ttm'),
                    "dv_ratio": basic.get('dv_ratio'),
                    "dv_ttm": basic.get('dv_ttm'),
                    "total_share": basic.get('total_share'),
                    "float_share": basic.get('float_share'),
                    "free_share": basic.get('free_share'),
                    "total_mv": basic.get('total_mv'),
                    "circ_mv": basic.get('circ_mv'),
                    "is_limit_up": limit_up,
                    "is_limit_down": limit_down,
                    "limit_up_time": "",
                    "streak_days": 0
                }
                
                # 保存到后端
                try:
                    result = backend_client.save_stock_daily(date, stock_data)
                    if result.get('success'):
                        pct_chg = data_dict.get('pct_chg', 0)
                        print(f"  {date}: ✅ 涨跌: {pct_chg:+.2f}%")
                        success_count += 1
                    else:
                        print(f"  {date}: ❌ 保存失败")
                except Exception as e:
                    print(f"  {date}: ❌ 错误: {e}")
            
            print(f"\n{'=' * 60}")
            self.logger.info(f"✅ 采集完成！成功：{success_count}/{len(items)} 天")
            print("=" * 60 + "\n")
            
            return success_count
            
        except Exception as e:
            self.logger.error(f"❌ 采集失败: {e}")
            return 0
    
    def collect_intraday(self, code: str, start_date: str = None, end_date: str = None, 
                         force: bool = False, trading_dates: List[str] = None,
                         verbose: bool = True) -> int:
        """
        收集单只股票的分时数据（批量查询优化版）
        
        Args:
            code: 股票代码
            start_date: 开始日期（trading_dates 为 None 时必填）
            end_date: 结束日期（trading_dates 为 None 时必填）
            force: 是否强制重新采集
            trading_dates: 交易日列表（批量采集时传入，避免重复调用 API）
            verbose: 是否打印详细信息（批量采集时设为 False）
            
        Returns:
            成功采集的天数
        """
        # 获取交易日列表
        if trading_dates is None:
            if not start_date or not end_date:
                raise ValueError("trading_dates 为 None 时，必须提供 start_date 和 end_date")
            trading_dates = self.get_trading_dates(start_date, end_date)
        
        market = get_market(code)
        
        # 打印标题（批量模式时跳过）
        if verbose:
            print("=" * 60)
            print(f"单股票分时数据采集器（批量查询）")
            print("=" * 60)
            print(f"\n📊 股票代码：{code}")
            print(f"📅 交易日数：{len(trading_dates)} 天")
            print(f"🔄 强制模式：{'是' if force else '否'}")
            print("=" * 60 + "\n")
        
        # 获取需要采集的日期（批量检查存在性）
        if force:
            dates_to_collect = list(trading_dates)
        else:
            # 批量检查已存在的日期（一次 API 调用）
            exists_dict = backend_client.get_stock_intraday_existence_batch(code, trading_dates)
            dates_to_collect = [d for d in trading_dates if not exists_dict.get(d, False)]
            if verbose:
                for date in trading_dates:
                    if exists_dict.get(date, False):
                        print(f"  {date}: ⏭️ 已存在")
        
        if not dates_to_collect:
            if verbose:
                self.logger.info("✅ 所有日期已存在，无需采集")
            return 0
        
        if verbose:
            print(f"\n📋 需要采集 {len(dates_to_collect)} 个交易日")
        
        success_count = 0
        total_dates = len(dates_to_collect)
        
        # 分批采集（每批最多 30 天，避免超过 API 返回限制 8000 条）
        batch_size = 30
        for batch_start in range(0, total_dates, batch_size):
            batch_dates = dates_to_collect[batch_start:batch_start + batch_size]
            
            # 确保 start_date <= end_date（batch_dates 可能是倒序的）
            batch_start_date = min(batch_dates[0], batch_dates[-1])
            batch_end_date = max(batch_dates[0], batch_dates[-1])
            
            if verbose:
                print(f"\n[批次 {batch_start//batch_size + 1}] 采集 {batch_start_date} ~ {batch_end_date}...")
            
            try:
                # 批量获取分时数据（一次 API 调用获取多天）
                intraday_data = None
                for attempt in range(5):
                    intraday_data = market_data_client.get_stock_intraday_range(
                        code, 
                        market, 
                        batch_start_date, 
                        batch_end_date
                    )
                    if intraday_data:
                        break
                    if attempt < 4:
                        self.logger.warning(f"  重试 {attempt + 2}/5...")
                        time.sleep(2)
                
                if not intraday_data:
                    self.logger.warning(f"  ⚠️ 批次无数据")
                    continue
                
                # 按日期保存数据
                for date in batch_dates:
                    day_data = intraday_data.get(date, [])
                    
                    if not day_data:
                        if verbose:
                            print(f"  {date}: ⏭️ 无数据")
                        continue
                    
                    # 保存到后端
                    result = backend_client.save_intraday_data(date, code, day_data)
                    
                    if result.get('success'):
                        if verbose:
                            print(f"  {date}: ✅ {len(day_data)} 条")
                        success_count += 1
                    elif verbose:
                        print(f"  {date}: ❌ 保存失败")
                
                # 批次间休息（避免 API 疲劳）
                if batch_start + batch_size < total_dates:
                    time.sleep(0.5)
                    
            except Exception as e:
                self.logger.error(f"  ❌ 批次失败: {e}")
        
        if verbose:
            print(f"\n{'=' * 60}")
            self.logger.info(f"✅ 采集完成！成功：{success_count}/{total_dates} 天")
            print("=" * 60 + "\n")
        
        return success_count
    
    def collect_auction(self, start_date: str, end_date: str, force: bool = False, verbose: bool = True) -> int:
        """
        收集竞价数据（仅股票池中的股票）
        
        Args:
            start_date: 开始日期
            end_date: 结束日期
            force: 是否强制重新采集
            verbose: 是否打印详细信息
            
        Returns:
            成功采集的天数
        """
        # 获取交易日列表
        trading_dates = self.get_trading_dates(start_date, end_date)
        
        # 获取股票池列表
        all_stocks = backend_client.get_all_stocks()
        stock_codes = [s['code'] for s in all_stocks]
        
        if verbose:
            print("=" * 60)
            print("竞价数据采集器")
            print("=" * 60)
            print(f"\n📅 交易日数：{len(trading_dates)} 天")
            print(f"📊 股票池：{len(stock_codes)} 只")
            print(f"🔄 强制模式：{'是' if force else '否'}")
            print("=" * 60 + "\n")
        
        success_count = 0
        
        for date in trading_dates:
            # 检查是否已存在
            if not force and backend_client.check_auction_exists(date):
                if verbose:
                    print(f"  {date}: ⏭️ 已存在")
                continue
            
            try:
                # 获取竞价数据（仅股票池中的股票）
                auction_data = get_auction_data(date, stock_codes)
                
                if not auction_data:
                    if verbose:
                        print(f"  {date}: ⚠️ 无数据")
                    continue
                
                # 保存到后端
                result = backend_client.save_auction_data(date, auction_data)
                
                if result.get('success'):
                    if verbose:
                        print(f"  {date}: ✅ {len(auction_data)} 只股票")
                    success_count += 1
                elif verbose:
                    print(f"  {date}: ❌ 保存失败")
                
                # 避免API疲劳
                time.sleep(0.3)
                
            except Exception as e:
                self.logger.error(f"  {date}: ❌ 错误: {e}")
        
        if verbose:
            print(f"\n{'=' * 60}")
            self.logger.info(f"✅ 采集完成！成功：{success_count}/{len(trading_dates)} 天")
            print("=" * 60 + "\n")
        
        return success_count


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='单股票数据采集器')
    parser.add_argument('--code', type=str, default=None,
                       help='股票代码（如 000001）')
    parser.add_argument('--days', type=int, default=60,
                       help='采集最近 N 天的数据（默认 60 天）')
    parser.add_argument('--start', type=str, default=None,
                       help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, default=None,
                       help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--intraday', action='store_true',
                       help='同时收集分时数据')
    parser.add_argument('--auction', action='store_true',
                       help='收集竞价数据（全市场，无需指定 --code）')
    parser.add_argument('--force', action='store_true',
                       help='强制重新采集')
    
    args = parser.parse_args()
    
    # 验证参数
    if not args.auction and not args.code:
        parser.error("必须指定 --code 或 --auction")
    
    # 计算日期范围
    if args.start:
        start_date = args.start
        end_date = args.end if args.end else datetime.now().strftime('%Y-%m-%d')
    else:
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=args.days)).strftime('%Y-%m-%d')
    
    # 创建采集器并执行
    collector = StockDataCollector()
    
    try:
        # 收集竞价数据（全市场）
        if args.auction:
            collector.collect_auction(start_date, end_date, args.force)
        
        # 收集单只股票数据
        if args.code:
            # 收集日线数据
            collector.collect_daily(args.code, start_date, end_date, args.force)
            
            # 如果指定，收集分时数据
            if args.intraday:
                collector.collect_intraday(args.code, start_date, end_date, args.force)
        
        print("\n🎉 采集任务成功完成！")
        sys.exit(0)
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断采集")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 采集失败：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


stock_data_collector = StockDataCollector()
