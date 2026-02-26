#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据采集器 - 每日数据采集脚本

职责：
1. 采集股票池中所有股票的每日行情数据
2. 对每只股票：
   - 查询实时行情（开高低收、成交量额等）
   - 判断涨停/跌停状态
   - 写入 stock_daily（保存所有股票，不仅限涨停）
3. 获取并更新全市场情绪指标：
   - 全市场涨停/跌停数量（非股票池范围）
   - 最高连板数（估算）
   - 指数涨跌幅

重要区分：
- stock_daily 表：保存股票池中的个股数据（我们关注的股票）
- market_sentiment 表：保存全市场统计数据（所有A股的涨停/跌停）

数据采集范围：
- ✅ 保存股票池中所有股票的每日行情
- ✅ 自动跳过ST股票（风控）
- ✅ 从市场快照获取全市场涨停/跌停统计
- ✅ 更新全市场情绪指标（不基于股票池计算）

设计理由：
- 龙头不一定涨停（弱转强、补涨分离等模式）
- 需要完整历史数据进行训练和分析
- 支持人气底线筛选（成交额排名）
- 支持板块联动分析（概念内个股表现）
- 市场情绪需要全市场数据才准确

数据来源：通过 tushare_api.py 获取
数据写入：通过后端API写入（backend_api_client.py）
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# 添加当前目录到路径
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from market_data_client import MarketDataClient
from backend_api_client import BackendAPIClient


class MarketDataCollector:
    """市场数据采集器（通过后端API写入）"""
    
    def __init__(self, backend_url: str = None):
        """
        初始化采集器
        
        Args:
            backend_url: 后端服务地址（不提供则从配置文件读取）
        """
        self.market_client = MarketDataClient()  # 市场数据客户端（使用tushare_api）
        self.backend_client = BackendAPIClient(backend_url)  # 后端API客户端
    
    def _get_market_overview(self, date: str) -> Dict:
        """
        获取市场概况（指数数据）
        
        Args:
            date: 交易日期
            
        Returns:
            市场数据字典
            
        Raises:
            Exception: 如果无法获取市场数据
        """
        print("📊 Step 1: 获取市场概况...")
        market_snapshot = self.market_client.get_market_snapshot(date)
        
        if not market_snapshot:
            raise Exception(f"❌ 无法获取市场数据（请检查Tushare API权限）")
        
        market_data = {
            "limit_up_count": market_snapshot.get("limit_up_count", 0),
            "limit_down_count": market_snapshot.get("limit_down_count", 0),
            "broken_board_count": market_snapshot.get("broken_board_count", 0),
            "max_streak": market_snapshot.get("max_streak", 0),
            "sh_index_change": market_snapshot.get("sh_index_change", 0.0),
            "sz_index_change": market_snapshot.get("sz_index_change", 0.0),
            "cy_index_change": market_snapshot.get("cy_index_change", 0.0),
            "total_turnover": market_snapshot.get("total_turnover", 0.0)
        }
        
        print(f"  上证指数: {market_data['sh_index_change']:+.2f}%")
        print(f"  深证成指: {market_data['sz_index_change']:+.2f}%")
        print(f"  创业板指: {market_data['cy_index_change']:+.2f}%")
        
        return market_data
    
    def _get_limit_threshold(self, code: str, name: str) -> float:
        """
        根据股票代码和名称判断涨停阈值
        
        Args:
            code: 股票代码
            name: 股票名称
            
        Returns:
            涨停阈值（百分比）
        """
        if 'ST' in name.upper():
            return 4.9  # ST股票 5%
        elif code.startswith('688') or code.startswith('300'):
            return 19.5  # 科创板/创业板 20%
        elif code.startswith('8') or code.startswith('4'):
            return 29.5  # 北交所 30%
        else:
            return 9.5  # 主板/中小板 10%
    
    def _build_stock_data(self, stock: Dict, quote: Dict, 
                          is_limit_up: int, is_limit_down: int) -> Dict:
        """
        构建股票数据字典
        
        Args:
            stock: 股票基本信息
            quote: 行情数据
            is_limit_up: 是否涨停
            is_limit_down: 是否跌停
            
        Returns:
            股票数据字典
        """
        return {
            "code": stock['code'],
            "name": stock.get('name', ''),
            "market": stock['market'],
            "open": quote.get('o', 0.0),
            "high": quote.get('h', 0.0),
            "low": quote.get('l', 0.0),
            "close": quote.get('ld', 0.0),
            "pre_close": quote.get('p', 0.0),
            "change_percent": quote.get('chp', 0.0),
            "volume": quote.get('vol', 0),
            "turnover": quote.get('amt', 0.0),
            "turnover_rate": quote.get('tr', 0.0),
            "is_limit_up": is_limit_up,
            "is_limit_down": is_limit_down,
            "limit_up_time": "",  # Tushare不提供涨停时间
            "streak_days": 0,      # 连板天数需要后端计算
        }
    
    def _process_single_stock(self, stock: Dict, index: int, total: int) -> tuple:
        """
        处理单只股票
        
        Args:
            stock: 股票信息
            index: 当前索引
            total: 总数
            
        Returns:
            (stock_data, is_limit_up, is_limit_down) 或 (None, 0, 0)
        """
        code = stock['code']
        name = stock.get('name', '')
        market = stock['market']
        
        # 跳过ST股票（风控要求）
        if 'ST' in name.upper():
            print(f"  ⚠️  跳过ST股票: {code} {name}")
            return None, 0, 0
        
        try:
            # 获取行情数据
            quote = self.market_client.get_stock_quote(code, market)
            
            if not quote:
                print(f"  ⚠️  {code} {name} - 未获取到行情数据")
                return None, 0, 0
            
            # 提取涨跌幅
            change_percent = quote.get('chp', 0.0)
            
            # 判断涨停/跌停
            limit_threshold = self._get_limit_threshold(code, name)
            is_limit_up = 1 if change_percent >= limit_threshold else 0
            is_limit_down = 1 if change_percent <= -limit_threshold else 0
            
            # ⚠️ 关键修改：返回所有股票数据（不管是否涨停）
            stock_data = self._build_stock_data(stock, quote, is_limit_up, is_limit_down)
            return stock_data, is_limit_up, is_limit_down
            
        except Exception as e:
            print(f"  ❌ 查询 {code} {name} 失败: {e}")
            return None, 0, 0
    
    def _collect_stocks_data(self, all_stocks: List[Dict]) -> tuple:
        """
        采集所有股票数据
        
        Args:
            all_stocks: 股票列表
            
        Returns:
            (stocks_data, pool_limit_up_count, pool_limit_down_count, total_checked)
            
        注意：返回的涨停/跌停数量仅为股票池内的统计，不代表全市场
        """
        print(f"\n📊 Step 3: 查询个股行情（保存所有股票数据）...")
        
        stocks_data = []
        pool_limit_up_count = 0   # 股票池内的涨停数量
        pool_limit_down_count = 0  # 股票池内的跌停数量
        total_stocks_checked = 0
        
        for i, stock in enumerate(all_stocks):
            stock_data, is_limit_up, is_limit_down = self._process_single_stock(
                stock, i, len(all_stocks)
            )
            
            if stock_data is None and is_limit_up == 0 and is_limit_down == 0:
                # 跳过的股票（如ST股票）
                continue
            
            total_stocks_checked += 1
            
            # 统计股票池内的涨停/跌停数量（仅用于日志显示）
            if is_limit_up == 1:
                pool_limit_up_count += 1
                print(f"  🔴 涨停 {pool_limit_up_count}: {stock_data['code']} "
                      f"{stock_data['name']} ({stock_data['change_percent']:+.2f}%)")
            elif is_limit_down == 1:
                pool_limit_down_count += 1
                print(f"  🟢 跌停 {pool_limit_down_count}: {stock_data['code']} "
                      f"{stock_data['name']} ({stock_data['change_percent']:+.2f}%)")
            
            # ⚠️ 关键修改：保存所有股票数据（不仅仅是涨停）
            if stock_data is not None:
                stocks_data.append(stock_data)
            
            # 每20只股票显示进度
            if (i + 1) % 20 == 0:
                print(f"  进度: {i + 1}/{len(all_stocks)} ({total_stocks_checked} 只有效, "
                      f"池内涨停 {pool_limit_up_count}, 池内跌停 {pool_limit_down_count})")
        
        return stocks_data, pool_limit_up_count, pool_limit_down_count, total_stocks_checked
    
    # 注意：市场情绪数据（涨停/跌停数量）已在 _get_market_overview() 中
    # 从 market_snapshot 获取，代表全市场统计，不需要基于股票池重新计算
        
    def collect(self, date: str) -> Dict:
        """
        采集指定日期的市场数据
        
        采集流程：
        1. 获取市场概况（指数数据 + 全市场涨停/跌停统计）
        2. 获取股票池（所有需要跟踪的股票）
        3. 查询所有股票行情并保存（不仅限涨停）
        4. 使用全市场统计更新市场情绪指标
        5. 通过后端API写入数据库
        
        Args:
            date: 交易日期（YYYY-MM-DD）
        
        Returns:
            采集结果字典 {
                'date': 日期,
                'market_saved': 市场数据是否保存成功,
                'stocks_saved': 保存的股票数量,
                'stocks_count': 总股票数量
            }
        """
        print(f"\n{'=' * 60}")
        print(f"📅 开始采集市场数据: {date}")
        print(f"{'=' * 60}\n")
        
        try:
            # Step 1: 获取市场概况（包含全市场涨停/跌停统计）
            market_data = self._get_market_overview(date)
            
            # Step 2: 获取股票池
            print(f"\n📈 Step 2: 获取股票池...")
            all_stocks = self.backend_client.get_all_stocks()
            print(f"  股票池总数: {len(all_stocks)} 只")
            
            # Step 3: 采集股票池数据
            stocks_data, pool_limit_up, pool_limit_down, total_checked = \
                self._collect_stocks_data(all_stocks)
            
            # Step 4: 使用全市场统计（来自market_snapshot）
            # 注意：不使用股票池的统计覆盖全市场统计
            print(f"\n📊 Step 4: 确认市场情绪数据...")
            print(f"  全市场涨停: {market_data['limit_up_count']} 只（来自市场快照）")
            print(f"  全市场跌停: {market_data['limit_down_count']} 只（来自市场快照）")
            print(f"  股票池涨停: {pool_limit_up} 只（仅供参考）")
            print(f"  股票池跌停: {pool_limit_down} 只（仅供参考）")
            
            print(f"\n📊 统计结果:")
            print(f"  有效股票: {total_checked} 只")
            print(f"  保存数据: {len(stocks_data)} 只")
            print(f"  全市场涨停: {market_data['limit_up_count']} 只")
            print(f"  全市场跌停: {market_data['limit_down_count']} 只")
            print(f"  最高连板估算: {market_data['max_streak']} 板")
            
            # Step 5: 通过后端API写入数据
            print(f"\n💾 Step 5: 通过后端API写入数据...")
            result = self.backend_client.collect_market_data(
                date=date,
                market_data=market_data,  # 使用全市场统计
                stocks=stocks_data
            )
            
            print(f"\n✅ 数据采集完成!")
            print(f"  日期: {result.get('date')}")
            print(f"  市场数据: {'✓' if result.get('market_saved') else '✗'}")
            print(f"  涨停个股: {result.get('stocks_saved')}/{result.get('stocks_count')}")
            
            return result
            
        except Exception as e:
            print(f"\n❌ 采集失败: {e}")
            import traceback
            traceback.print_exc()
            raise


def main():
    """命令行入口"""
    import sys
    
    # 解析参数
    if len(sys.argv) > 1:
        date = sys.argv[1]
    else:
        # 默认使用今天
        date = datetime.now().strftime('%Y-%m-%d')
    
    print(f"""
{'=' * 60}
市场数据采集工具
{'=' * 60}

功能说明：
  1. 获取指定日期的市场概况（指数数据）
  2. 遍历股票池，查询个股行情
  3. 筛选并保存涨停股票
  4. 计算市场情绪指标（涨停/跌停/连板）
  5. 通过后端API写入数据库

数据来源: Tushare API (通过 tushare_api.py)
数据写入: 后端API (http://localhost:8000)
采集日期: {date}

{'=' * 60}
""")
    
    # 执行采集
    try:
        collector = MarketDataCollector()
        result = collector.collect(date)
        
        print(f"\n{'=' * 60}")
        print("✅ 采集任务成功完成")
        print(f"{'=' * 60}")
        print(f"\n📊 采集统计:")
        print(f"  日期: {result.get('date')}")
        print(f"  市场数据: {'已保存' if result.get('market_saved') else '失败'}")
        print(f"  涨停个股: {result.get('stocks_saved')}/{result.get('stocks_count')}")
        print(f"\n{'=' * 60}\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断采集")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 采集失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
