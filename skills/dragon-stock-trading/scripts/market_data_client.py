#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
市场数据客户端 - 统一的数据访问接口
作为业务逻辑层，提供标准化的数据获取接口
实际API调用委托给底层的tushare_api模块
"""

from typing import Dict, List, Optional
from datetime import datetime

# 导入底层API调用器
from tushare_api import get_tushare_api


class MarketDataClient:
    """市场数据客户端（业务逻辑层）"""
    
    def __init__(self):
        """初始化客户端"""
        # 获取底层API调用器实例
        self._api = get_tushare_api()
        self._request_count = 0
    
    def get_stock_quote(self, stock_code: str, market: str = None) -> Optional[Dict]:
        """
        获取股票行情数据
        
        Args:
            stock_code: 股票代码（如 000001）
            market: 市场代码（SH/SZ，可选）
            
        Returns:
            行情数据字典
        """
        # 构造Tushare格式的股票代码
        if '.' not in stock_code:
            if market:
                ts_code = f"{stock_code}.{market.upper()}"
            else:
                # 自动识别市场
                if stock_code.startswith(('6', '5')):
                    ts_code = f"{stock_code}.SH"
                else:
                    ts_code = f"{stock_code}.SZ"
        else:
            ts_code = stock_code
        
        # 委托给底层API获取数据
        data = self._api.get_stock_daily(ts_code=ts_code)
        
        if data and data.get('items'):
            item = data['items'][0]
            self._request_count += 1
            return {
                'ld': item[5],      # close
                'chp': item[8],     # pct_chg
                'vol': item[9],
                'amt': item[10],
                'o': item[2],
                'h': item[3],
                'l': item[4],
                'p': item[6],
                'tr': 0.0  # 换手率需要额外计算
            }
        return None
    
    def get_stock_info(self, stock_code: str, market: str = None) -> Optional[Dict]:
        """
        获取股票基本信息
        
        Args:
            stock_code: 股票代码
            market: 市场代码
            
        Returns:
            股票信息字典
        """
        # 构造Tushare格式的股票代码
        if '.' not in stock_code:
            if market:
                ts_code = f"{stock_code}.{market.upper()}"
            else:
                if stock_code.startswith(('6', '5')):
                    ts_code = f"{stock_code}.SH"
                else:
                    ts_code = f"{stock_code}.SZ"
        else:
            ts_code = stock_code
        
        # 委托给底层API获取数据
        data = self._api.get_stock_basic(ts_code=ts_code)
        
        if data and data.get('items'):
            item = data['items'][0]
            self._request_count += 1
            return {
                'code': stock_code,
                'name': item[1],
                'market': item[4],
                'industry': item[3]
            }
        return None
    
    def get_index_quote(self, index_code: str, region: str = None) -> Optional[Dict]:
        """
        获取指数行情
        
        Args:
            index_code: 指数代码
            region: 市场代码（兼容参数）
            
        Returns:
            指数行情数据
        """
        # 指数代码映射
        index_mapping = {
            '000001': '000001.SH',  # 上证指数
            '399001': '399001.SZ',  # 深证成指
            '399006': '399006.SZ'   # 创业板指
        }
        
        ts_code = index_mapping.get(index_code, f"{index_code}.SH")
        
        # 委托给底层API获取数据
        data = self._api.get_index_daily(ts_code=ts_code)
        
        if data and data.get('items'):
            item = data['items'][0]
            self._request_count += 1
            return {
                'ld': item[5],      # close
                'chp': item[8],     # pct_chg
                'vol': item[9],
                'amt': item[10],
                'o': item[2],
                'h': item[3],
                'l': item[4],
                'p': item[6]
            }
        return None
    
    def get_market_snapshot(self, date: str = None) -> Optional[Dict]:
        """
        获取市场概况快照
        
        Args:
            date: 日期（YYYY-MM-DD），默认为今天
            
        Returns:
            市场概况数据
        """
        print(f"  📊 正在计算市场快照...")
        
        # 获取主要指数行情
        sh_index = self.get_index_quote('000001')  # 上证指数
        sz_index = self.get_index_quote('399001')  # 深证成指
        cy_index = self.get_index_quote('399006')  # 创业板指
        
        # 估算市场数据（基于指数变化）
        sh_change = sh_index.get('chp', 0.0) if sh_index else 0.0
        sz_change = sz_index.get('chp', 0.0) if sz_index else 0.0
        cy_change = cy_index.get('chp', 0.0) if cy_index else 0.0
        
        # 简单估算：根据指数涨跌幅推测涨停跌停数量
        # 这只是一个粗略估算，实际应该通过查询所有股票来精确统计
        avg_change = (sh_change + sz_change + cy_change) / 3
        
        if avg_change > 2:
            # 市场强势，假设较多涨停
            limit_up_estimate = 50
            limit_down_estimate = 5
        elif avg_change < -2:
            # 市场弱势，假设较多跌停
            limit_up_estimate = 5
            limit_down_estimate = 30
        else:
            # 市场平稳
            limit_up_estimate = 20
            limit_down_estimate = 10
        
        return {
            'limit_up_count': limit_up_estimate,
            'limit_down_count': limit_down_estimate,
            'broken_board_count': max(0, limit_up_estimate - 30),  # 粗略估算破板数
            'max_streak': min(8, max(3, limit_up_estimate // 10)),  # 粗略估算最高连板
            'sh_index_change': sh_change,
            'sz_index_change': sz_change,
            'cy_index_change': cy_change,
            'total_turnover': 1200.0  # 万亿元级别，粗略估算
        }
    
    def get_limit_up_stocks(self, date: str = None) -> List[Dict]:
        """
        获取涨停股票列表（Tushare暂不直接支持，需要通过涨跌幅筛选）
        
        Args:
            date: 日期（YYYY-MM-DD）
            
        Returns:
            涨停股票列表
        """
        # Tushare没有直接的涨停列表接口，需要通过涨跌幅筛选
        print("  ⚠️  Tushare不直接提供涨停列表，需要通过涨跌幅>=9.5%筛选")
        return []
    
    def get_request_count(self) -> int:
        """获取请求计数"""
        return self._request_count
    
    def reset_request_count(self):
        """重置请求计数"""
        self._request_count = 0


def main():
    """测试客户端"""
    print("="*60)
    print("市场数据客户端测试")
    print("="*60)
    
    client = MarketDataClient()
    
    # 测试获取股票行情
    print("\n测试1: 获取平安银行行情")
    quote = client.get_stock_quote("000001", "SZ")
    if quote:
        print(f"✅ 收盘价: {quote['ld']}, 涨跌幅: {quote['chp']:+.2f}%")
    else:
        print("❌ 获取失败")
    
    # 测试获取股票信息
    print("\n测试2: 获取平安银行信息")
    info = client.get_stock_info("000001", "SZ")
    if info:
        print(f"✅ 名称: {info['name']}, 行业: {info['industry']}")
    else:
        print("❌ 获取失败")
    
    # 测试获取指数行情
    print("\n测试3: 获取上证指数行情")
    index_quote = client.get_index_quote("000001")
    if index_quote:
        print(f"✅ 上证指数: {index_quote['ld']:.2f} ({index_quote['chp']:+.2f}%)")
    else:
        print("❌ 获取失败")
    
    print(f"\n总请求数: {client.get_request_count()}")
    print("\n✅ 客户端测试完成！")


if __name__ == "__main__":
    main()