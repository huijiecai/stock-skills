#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
itick API 客户端
封装所有 itick API 调用，提供统一接口
"""

import requests
import time
from typing import Dict, Optional
from config_loader import config


class ItickClient:
    """itick API 客户端"""
    
    def __init__(self, api_key: str = None, base_url: str = None, timeout: int = None):
        """
        初始化客户端
        
        Args:
            api_key: API密钥，默认从配置文件读取
            base_url: API基础URL，默认从配置文件读取
            timeout: 超时时间，默认从配置文件读取
        """
        self.api_key = api_key or config.get_itick_api_key()
        self.base_url = base_url or config.get_itick_base_url()
        self.timeout = timeout or config.get_itick_timeout()
        
        self.headers = {
            'accept': 'application/json',
            'token': self.api_key
        }
        
        # 请求计数（用于频率控制）
        self._request_count = 0
        self._last_request_time = 0
    
    def _rate_limit(self):
        """频率控制"""
        current_time = time.time()
        
        # 简单的频率控制：每秒最多20个请求
        if current_time - self._last_request_time < 0.05:
            time.sleep(0.05)
        
        self._last_request_time = time.time()
        self._request_count += 1
    
    def get_stock_quote(self, stock_code: str, region: str) -> Optional[Dict]:
        """
        获取股票实时行情
        
        Args:
            stock_code: 股票代码
            region: 市场（SH/SZ）
        
        Returns:
            行情数据字典，失败返回 None
        """
        self._rate_limit()
        
        url = f"{self.base_url}/stock/quote"
        params = {
            'region': region,
            'code': stock_code
        }
        
        try:
            response = requests.get(
                url, 
                headers=self.headers, 
                params=params, 
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') == 0 and data.get('data'):
                return data['data']
            else:
                return None
                
        except requests.exceptions.RequestException as e:
            # 静默处理网络错误，由调用方决定如何处理
            return None
        except Exception as e:
            return None
    
    def get_stock_info(self, stock_code: str, region: str) -> Optional[Dict]:
        """
        获取股票基本信息
        
        Args:
            stock_code: 股票代码
            region: 市场（SH/SZ）
        
        Returns:
            股票信息字典
        """
        self._rate_limit()
        
        url = f"{self.base_url}/stock/info"
        params = {
            'type': 'stock',
            'region': region,
            'code': stock_code
        }
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') == 0 and data.get('data'):
                stock_data = data['data']
                return {
                    'industry': stock_data.get('s', ''),
                    'sub_industry': stock_data.get('i', ''),
                    'company_desc': stock_data.get('bd', ''),
                    'website': stock_data.get('wu', '')
                }
            return None
            
        except Exception as e:
            return None
    
    def get_stock_kline(self, stock_code: str, region: str, period: str = 'day', count: int = 100) -> Optional[list]:
        """
        获取股票K线数据
        
        Args:
            stock_code: 股票代码
            region: 市场（SH/SZ）
            period: 周期（day/week/month）
            count: 数量
        
        Returns:
            K线数据列表
        """
        self._rate_limit()
        
        url = f"{self.base_url}/stock/kline"
        params = {
            'region': region,
            'code': stock_code,
            'period': period,
            'count': count
        }
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('code') == 0 and data.get('data'):
                return data['data']
            return None
            
        except Exception as e:
            return None
    
    def get_index_quote(self, index_code: str, region: str) -> Optional[Dict]:
        """
        获取指数行情
        
        Args:
            index_code: 指数代码
            region: 市场（SH/SZ）
        
        Returns:
            指数行情数据
        """
        # 指数也使用 stock/quote 接口
        return self.get_stock_quote(index_code, region)
    
    def get_request_count(self) -> int:
        """获取请求计数"""
        return self._request_count
    
    def reset_request_count(self):
        """重置请求计数"""
        self._request_count = 0


# 全局客户端实例
client = ItickClient()


def main():
    """测试客户端"""
    print("="*60)
    print("itick 客户端测试")
    print("="*60)
    
    # 测试获取股票行情
    print("\n测试1: 获取股票行情")
    quote = client.get_stock_quote('000001', 'SZ')
    if quote:
        print(f"✅ 平安银行: {quote.get('ld', 0)}元 ({quote.get('chp', 0):+.2f}%)")
    else:
        print("❌ 获取失败")
    
    # 测试获取股票信息
    print("\n测试2: 获取股票信息")
    info = client.get_stock_info('000001', 'SZ')
    if info:
        print(f"✅ 行业: {info.get('industry', 'N/A')}")
    else:
        print("❌ 获取失败")
    
    # 测试获取指数
    print("\n测试3: 获取指数行情")
    index = client.get_index_quote('000001', 'SH')
    if index:
        print(f"✅ 上证指数: {index.get('ld', 0):.2f} ({index.get('chp', 0):+.2f}%)")
    else:
        print("❌ 获取失败")
    
    print(f"\n总请求数: {client.get_request_count()}")
    print("\n✅ 客户端测试完成！")


if __name__ == "__main__":
    main()
