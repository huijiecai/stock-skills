#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tushare API 调用器 - 底层API调用实现
专门负责与Tushare API的直接交互
"""

import requests
import time
from typing import Dict, List, Optional


class TushareAPI:
    """Tushare API底层调用器"""
    
    def __init__(self, token: str):
        """
        初始化API调用器
        
        Args:
            token: Tushare token
        """
        self.token = token
        self.base_url = "http://api.tushare.pro"
        self.headers = {
            'Content-Type': 'application/json'
        }
        
        # 请求计数和频率控制
        self._request_count = 0
        self._last_request_time = 0
    
    def _rate_limit(self):
        """频率控制 - Tushare免费用户限制每分钟100次"""
        current_time = time.time()
        
        # 控制频率：每分钟最多100次请求（约0.6秒一次）
        if current_time - self._last_request_time < 0.6:
            sleep_time = 0.6 - (current_time - self._last_request_time)
            time.sleep(sleep_time)
        
        self._last_request_time = time.time()
        self._request_count += 1
    
    def _post(self, api_name: str, fields: List[str], **kwargs) -> Optional[Dict]:
        """
        发送POST请求到Tushare API
        
        Args:
            api_name: API接口名称
            fields: 返回字段列表
            **kwargs: 请求参数
            
        Returns:
            API返回的数据字典
        """
        self._rate_limit()
        
        payload = {
            "api_name": api_name,
            "token": self.token,
            "params": kwargs,
            "fields": fields
        }
        
        try:
            response = requests.post(
                self.base_url,
                json=payload,
                headers=self.headers,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()
            
            if result.get('code') == 0:
                return result.get('data')
            else:
                print(f"Tushare API错误: {result.get('msg', '未知错误')}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"Tushare请求失败: {e}")
            return None
        except Exception as e:
            print(f"Tushare处理错误: {e}")
            return None
    
    def get_stock_daily(self, ts_code: str, trade_date: str = "") -> Optional[List]:
        """
        获取股票日线数据
        
        Args:
            ts_code: Tushare股票代码（如 000001.SZ）
            trade_date: 交易日期
            
        Returns:
            日线数据列表
        """
        return self._post(
            api_name="daily",
            fields=["ts_code", "trade_date", "open", "high", "low", "close", 
                   "pre_close", "change", "pct_chg", "vol", "amount"],
            ts_code=ts_code,
            trade_date=trade_date
        )
    
    def get_index_daily(self, ts_code: str, trade_date: str = "") -> Optional[List]:
        """
        获取指数日线数据
        
        Args:
            ts_code: Tushare指数代码（如 000001.SH）
            trade_date: 交易日期
            
        Returns:
            指数日线数据列表
        """
        return self._post(
            api_name="index_daily",
            fields=["ts_code", "trade_date", "open", "high", "low", "close", 
                   "pre_close", "change", "pct_chg", "vol", "amount"],
            ts_code=ts_code,
            trade_date=trade_date
        )
    
    def get_stock_basic(self, ts_code: str) -> Optional[List]:
        """
        获取股票基本信息
        
        Args:
            ts_code: Tushare股票代码
            
        Returns:
            股票基本信息列表
        """
        return self._post(
            api_name="stock_basic",
            fields=["ts_code", "name", "area", "industry", "market", "list_date"],
            ts_code=ts_code
        )


# 全局API实例（供TushareClient使用）
_tushare_api = None


def get_tushare_api(token: str = None) -> TushareAPI:
    """
    获取TushareAPI单例实例
    
    Args:
        token: Tushare token，如果不提供则使用默认token
        
    Returns:
        TushareAPI实例
    """
    global _tushare_api
    if _tushare_api is None:
        if token is None:
            token = "2fcac3d55f4d1844d0bd4e4b8d205003b947a625b596767c697d0e7b"
        _tushare_api = TushareAPI(token)
    return _tushare_api


def main():
    """测试API调用器"""
    print("="*60)
    print("Tushare API 调用器测试")
    print("="*60)
    
    api = get_tushare_api()
    
    # 测试获取股票数据
    print("\n测试1: 获取股票日线数据")
    data = api.get_stock_daily("000001.SZ")
    if data and data.get('items'):
        item = data['items'][0]
        print(f"✅ 平安银行: 收盘价 {item[5]}, 涨跌幅 {item[8]:+.2f}%")
    else:
        print("❌ 获取失败")
    
    # 测试获取指数数据
    print("\n测试2: 获取指数日线数据")
    data = api.get_index_daily("000001.SH")
    if data and data.get('items'):
        item = data['items'][0]
        print(f"✅ 上证指数: {item[5]:.2f} ({item[8]:+.2f}%)")
    else:
        print("❌ 获取失败")
    
    print(f"\n总请求数: {api._request_count}")
    print("\n✅ API调用器测试完成！")


if __name__ == "__main__":
    main()