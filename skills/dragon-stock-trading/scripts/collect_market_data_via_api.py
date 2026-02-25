#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据采集包装器 - 通过后端API写入数据

这个脚本作为数据采集的入口，负责：
1. 从iTick API获取市场数据
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

from itick_client import ItickClient
from backend_api_client import BackendAPIClient


class MarketDataCollector:
    """市场数据采集器（通过API）"""
    
    def __init__(self, backend_url: str = "http://localhost:8000"):
        """
        初始化采集器
        
        Args:
            backend_url: 后端服务地址
        """
        self.itick_client = ItickClient()
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
            # 1. 从iTick获取市场概况
            print("📊 正在获取市场概况...")
            market_snapshot = self.itick_client.get_market_snapshot(date)
            
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
            
            # 2. 获取涨停股票列表
            print(f"\n📈 正在获取涨停股票列表...")
            limit_up_stocks = self.itick_client.get_limit_up_stocks(date)
            
            stocks_data = []
            for stock in limit_up_stocks:
                stocks_data.append({
                    "code": stock.get("code"),
                    "name": stock.get("name"),
                    "market": stock.get("market"),
                    "close": stock.get("close", 0.0),
                    "change_percent": stock.get("change_percent", 0.0),
                    "is_limit_up": 1,
                    "limit_up_time": stock.get("limit_up_time", ""),
                    "streak_days": stock.get("streak_days", 0),
                    "volume": stock.get("volume", 0),
                    "turnover": stock.get("turnover", 0.0),
                    "turnover_rate": stock.get("turnover_rate", 0.0)
                })
            
            print(f"  获取到 {len(stocks_data)} 只涨停股票")
            
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
