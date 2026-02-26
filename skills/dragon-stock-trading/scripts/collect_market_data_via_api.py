#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据采集包装器 - 通过后端API写入数据

这个脚本作为数据采集的入口，负责：
1. 从Tushare API获取市场数据
2. 通过后端API写入数据（而非直接操作数据库）

供LLM调用进行数据采集
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List

# 添加当前目录到路径
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from tushare_client import TushareClient as MarketDataClient  # 使用Tushare替代iTock
from backend_api_client import BackendAPIClient


class MarketDataCollector:
    """市场数据采集器（通过API）"""
    
    def __init__(self, backend_url: str = "http://localhost:8000"):
        """
        初始化采集器
        
        Args:
            backend_url: 后端服务地址
        """
        self.market_client = MarketDataClient()  # 使用Tushare客户端
        self.backend_client = BackendAPIClient(backend_url)
        
    def collect(self, date: str) -> Dict:
        """
        采集指定日期的市场数据
        
        Args:
            date: 交易日期（YYYY-MM-DD）
        
        Returns:
            采集结果
        """
        print(f"\n{'=' * 60}")
        print(f"开始采集市场数据: {date}")
        print(f"{'=' * 60}\n")
        
        try:
            # 1. 从Tushare获取市场概况
            print("📊 正在获取市场概况...")
            market_snapshot = self.market_client.get_market_snapshot(date)
            
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
            
            print(f"  涨停: {market_data['limit_up_count']} 家")
            print(f"  跌停: {market_data['limit_down_count']} 家")
            print(f"  最高连板: {market_data['max_streak']} 板")
            
            # 2. 获取股票池并查询个股行情
            print(f"\n📈 正在获取股票池...")
            all_stocks = self.backend_client.get_all_stocks()
            print(f"  股票池总数: {len(all_stocks)} 只")

            stocks_data = []
            limit_up_count = 0
            limit_down_count = 0

            print(f"📊 正在查询个股行情...")
            for i, stock in enumerate(all_stocks):
                code = stock['code']
                market = stock['market']
                
                # 获取个股行情
                try:
                    print(f"  查询 {code} ({stock.get('name', '')})...")
                    quote = self.market_client.get_stock_quote(code, market)
                    print(f"  查询结果: {'成功' if quote else '失败'}")
                    if quote:
                        close_price = quote.get('ld', 0.0)  # 现价
                        change_percent = quote.get('chp', 0.0)  # 涨跌幅
                        volume = quote.get('vol', 0)  # 成交量
                        turnover = quote.get('amt', 0.0)  # 成交额
                    
                    # 判断是否涨停（根据板块判断涨停阈值）
                    is_limit_up = 0
                    is_limit_down = 0
                    if market.upper() == 'SH' or market.upper() == 'SZ':
                        # 主板/中小板，涨停阈值约10%
                        if change_percent >= 9.5:
                            is_limit_up = 1
                            limit_up_count += 1
                        elif change_percent <= -9.5:
                            is_limit_down = 1
                            limit_down_count += 1
                    elif market.upper() == 'BJ':
                        # 北交所，涨跌幅5%
                        if change_percent >= 4.5:
                            is_limit_up = 1
                            limit_up_count += 1
                        elif change_percent <= -4.5:
                            is_limit_down = 1
                            limit_down_count += 1
                    else:
                        # 其他板块，按20%（创业板/科创板）处理
                        if change_percent >= 19.5:
                            is_limit_up = 1
                            limit_up_count += 1
                        elif change_percent <= -19.5:
                            is_limit_down = 1
                            limit_down_count += 1
                    
                    # 只保存涨停股票
                    if is_limit_up == 1:
                        stocks_data.append({
                            "code": code,
                            "name": stock.get('name', ''),
                            "market": market,
                            "close": close_price,
                            "change_percent": change_percent,
                            "is_limit_up": is_limit_up,
                            "limit_up_time": "",  # iTick不提供涨停时间
                            "streak_days": 0,  # 连板天数需要从历史数据计算
                            "volume": volume,
                            "turnover": turnover,
                            "turnover_rate": quote.get('tr', 0.0)  # 换手率
                        })
                    
                    # 每处理20只股票显示进度
                    if (i + 1) % 20 == 0:
                        print(f"  已处理 {i + 1}/{len(all_stocks)} 只股票")
                
                except Exception as e:
                    print(f"  查询 {code} 失败: {e}")
                    continue  # 继续处理下一个股票
                    
                # 每20只股票暂停一下，避免请求过于频繁
                if (i + 1) % 20 == 0:
                    import time
                    time.sleep(2)
                    print(f"  已处理 {i + 1}/{len(all_stocks)} 只股票")

            # 更新市场数据中的涨停/跌停数量
            market_data["limit_up_count"] = limit_up_count
            market_data["limit_down_count"] = limit_down_count

            print(f"  涨停股票: {limit_up_count} 只")
            print(f"  跌停股票: {limit_down_count} 只")
            print(f"  涨停数据: {len(stocks_data)} 只")
            
            # 3. 通过后端API写入
            print(f"\n💾 正在通过API写入数据...")
            result = self.backend_client.collect_market_data(
                date=date,
                market_data=market_data,
                stocks=stocks_data
            )
            
            print(f"\n✅ 数据采集完成!")
            print(f"  日期: {result.get('date')}")
            print(f"  市场数据: {'✓' if result.get('market_saved') else '✗'}")
            print(f"  个股数据: {result.get('stocks_saved')}/{result.get('stocks_count')}")
            
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
市场数据采集工具
================
使用后端API写入数据，确保数据统一管理

后端服务: http://localhost:8000
采集日期: {date}
""")
    
    # 执行采集
    collector = MarketDataCollector()
    result = collector.collect(date)
    
    print(f"\n{'=' * 60}")
    print("✅ 采集任务完成")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
