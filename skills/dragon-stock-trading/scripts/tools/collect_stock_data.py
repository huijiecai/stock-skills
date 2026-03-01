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
from market_data_client import market_data_client


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
    
    def _get_trading_dates(self, start_date: str, end_date: str) -> List[str]:
        """获取交易日期列表"""
        trading_dates = tushare_client.get_trade_calendar(start_date, end_date)
        
        if trading_dates:
            self.logger.info(f"获取到 {len(trading_dates)} 个交易日")
            return trading_dates
        
        # 回退到简单逻辑
        self.logger.warning("交易日历 API 调用失败，使用简单周末排除逻辑")
        dates = []
        current = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        while current <= end:
            if current.weekday() < 5:
                dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        
        return dates
    
    def _get_market_code(self, code: str) -> str:
        """根据股票代码获取市场后缀"""
        if code.startswith('6'):
            return f"{code}.SH"
        else:
            return f"{code}.SZ"
    
    def _get_limit_rate(self, code: str) -> float:
        """根据股票代码获取涨跌停幅度"""
        if code.startswith('688') or code.startswith('300'):
            return 0.20  # 科创板/创业板
        elif code.startswith('8') or code.startswith('4'):
            return 0.30  # 北交所
        else:
            return 0.10  # 主板
    
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
        
        ts_code = self._get_market_code(code)
        start_compact = start_date.replace('-', '')
        end_compact = end_date.replace('-', '')
        
        try:
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
            limit_rate = self._get_limit_rate(code)
            
            for item in items:
                data_dict = dict(zip(fields, item))
                trade_date_raw = str(data_dict.get('trade_date', ''))
                date = f"{trade_date_raw[:4]}-{trade_date_raw[4:6]}-{trade_date_raw[6:8]}"
                
                # 获取对应日期的基本面数据
                basic = basic_data.get(trade_date_raw, {})
                
                # 判断涨跌停
                close_price = data_dict.get('close', 0)
                pre_close = data_dict.get('pre_close', 0)
                
                if pre_close > 0:
                    limit_up_price = round(pre_close * (1 + limit_rate), 2)
                    limit_down_price = round(pre_close * (1 - limit_rate), 2)
                    is_limit_up = 1 if close_price >= limit_up_price - 0.01 else 0
                    is_limit_down = 1 if close_price <= limit_down_price + 0.01 else 0
                else:
                    is_limit_up = 0
                    is_limit_down = 0
                
                # 构建保存数据
                stock_data = {
                    "code": code,
                    "name": "",
                    "market": "SH" if code.startswith('6') else "SZ",
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
                    "is_limit_up": is_limit_up,
                    "is_limit_down": is_limit_down,
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
    
    def collect_intraday(self, code: str, start_date: str, end_date: str, force: bool = False) -> int:
        """
        收集单只股票的分时数据
        
        Args:
            code: 股票代码
            start_date: 开始日期
            end_date: 结束日期
            force: 是否强制重新采集
            
        Returns:
            成功采集的天数
        """
        print("=" * 60)
        print(f"单股票分时数据采集器")
        print("=" * 60)
        print(f"\n📊 股票代码：{code}")
        print(f"📅 采集范围：{start_date} ~ {end_date}")
        print("=" * 60 + "\n")
        
        ts_code = self._get_market_code(code)
        trading_dates = self._get_trading_dates(start_date, end_date)
        
        success_count = 0
        
        for i, date in enumerate(trading_dates, 1):
            print(f"[{i}/{len(trading_dates)}] {date}...", end=' ')
            
            # 检查是否已存在
            if not force:
                if backend_client.get_stock_intraday_existence(code, date):
                    print("⏭️ 已存在")
                    continue
            
            try:
                # 获取分时数据（带重试，最多5次）
                intraday_list = None
                for attempt in range(5):
                    intraday_list = market_data_client.get_stock_intraday(
                        code, 
                        "SH" if code.startswith('6') else "SZ", 
                        date
                    )
                    if intraday_list:
                        break
                    if attempt < 4:
                        time.sleep(1)
                
                if not intraday_list:
                    print("⏭️ 无数据")
                    continue
                
                # 保存到后端
                result = backend_client.save_intraday_data(date, code, intraday_list)
                
                if result.get('success'):
                    print(f"✅ {len(intraday_list)} 条")
                    success_count += 1
                else:
                    print("❌ 保存失败")
                
                time.sleep(0.5)
                
            except Exception as e:
                print(f"❌ 错误: {e}")
        
        print(f"\n{'=' * 60}")
        self.logger.info(f"✅ 采集完成！成功：{success_count}/{len(trading_dates)} 天")
        print("=" * 60 + "\n")
        
        return success_count


def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description='单股票数据采集器')
    parser.add_argument('--code', type=str, required=True,
                       help='股票代码（如 000001）')
    parser.add_argument('--days', type=int, default=60,
                       help='采集最近 N 天的数据（默认 60 天）')
    parser.add_argument('--start', type=str, default=None,
                       help='开始日期（YYYY-MM-DD）')
    parser.add_argument('--end', type=str, default=None,
                       help='结束日期（YYYY-MM-DD）')
    parser.add_argument('--intraday', action='store_true',
                       help='同时收集分时数据')
    parser.add_argument('--force', action='store_true',
                       help='强制重新采集')
    
    args = parser.parse_args()
    
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
