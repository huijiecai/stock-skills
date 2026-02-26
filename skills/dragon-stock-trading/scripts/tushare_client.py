#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tushare API 客户端
封装所有 Tushare API 调用，提供统一接口
与 iTick client 保持相同的方法签名，便于切换
"""

import requests
import time
from typing import Dict, List, Optional
from config_loader import config


class TushareClient:
    """Tushare API 客户端"""
    
    def __init__(self, token: str = None, base_url: str = None, timeout: int = None):
        """
        初始化客户端
        
        Args:
            token: Tushare token，默认从配置文件读取
            base_url: API基础URL，默认使用Tushare官方地址
            timeout: 超时时间，默认从配置文件读取
        """
        self.token = token or "2fcac3d55f4d1844d0bd4e4b8d205003b947a625b596767c697d0e7b"
        self.base_url = base_url or "http://api.tushare.pro"
        self.timeout = timeout or config.get_itick_timeout() if hasattr(config, 'get_itick_timeout') else 30
        
        self.headers = {
            'Content-Type': 'application/json'
        }
        
        # 请求计数（用于频率控制）
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
                timeout=self.timeout
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
    
    def get_stock_quote(self, stock_code: str, region: str = None) -> Optional[Dict]:
        """
        获取股票实时行情（兼容iTock接口）
        
        Args:
            stock_code: 股票代码（如 '000001'）
            region: 市场代码（兼容参数，Tushare不需要）
            
        Returns:
            行情数据字典，字段映射为iTock格式
        """
        # Tushare使用daily接口获取最新行情
        data = self._post(
            api_name="daily",
            fields=["ts_code", "trade_date", "open", "high", "low", "close", 
                   "pre_close", "change", "pct_chg", "vol", "amount"],
            ts_code=f"{stock_code}.SZ" if stock_code.startswith(('00', '30')) else f"{stock_code}.SH",
            trade_date=""  # 获取最新数据
        )
        
        if data and data.get('items'):
            item = data['items'][0]  # 取最新一条
            return {
                'ld': item[5],      # close -> ld (最新价)
                'chp': item[8],     # pct_chg -> chp (涨跌幅%)
                'vol': item[9],     # vol -> vol (成交量，手)
                'amt': item[10],    # amount -> amt (成交额，千元)
                'tr': item[9] * 100 / 10000 if item[9] else 0,  # 换手率估算
                'o': item[2],       # open
                'h': item[3],       # high
                'l': item[4],       # low
                'p': item[6]        # pre_close
            }
        return None
    
    def get_stock_info(self, stock_code: str, region: str = None) -> Optional[Dict]:
        """
        获取股票基本信息
        
        Args:
            stock_code: 股票代码
            region: 市场代码（兼容参数）
            
        Returns:
            股票信息字典
        """
        data = self._post(
            api_name="stock_basic",
            fields=["ts_code", "name", "area", "industry", "market", "list_date"],
            ts_code=f"{stock_code}.SZ" if stock_code.startswith(('00', '30')) else f"{stock_code}.SH"
        )
        
        if data and data.get('items'):
            item = data['items'][0]
            return {
                'industry': item[3] if len(item) > 3 else '',
                'sub_industry': '',  # Tushare没有细分行业
                'company_desc': '',
                'website': ''
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
        
        data = self._post(
            api_name="index_daily",
            fields=["ts_code", "trade_date", "open", "high", "low", "close", 
                   "pre_close", "change", "pct_chg", "vol", "amount"],
            ts_code=ts_code,
            trade_date=""
        )
        
        if data and data.get('items'):
            item = data['items'][0]
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
        # 获取主要指数行情来估算市场状态
        sh_index = self.get_index_quote('000001')  # 上证指数
        sz_index = self.get_index_quote('399001')  # 深证成指
        cy_index = self.get_index_quote('399006')  # 创业板指
        
        return {
            'limit_up_count': 0,  # 需要通过其他方式获取或计算
            'limit_down_count': 0,
            'broken_board_count': 0,
            'max_streak': 0,
            'sh_index_change': sh_index.get('chp', 0.0) if sh_index else 0.0,
            'sz_index_change': sz_index.get('chp', 0.0) if sz_index else 0.0,
            'cy_index_change': cy_index.get('chp', 0.0) if cy_index else 0.0,
            'total_turnover': 0.0  # 需要汇总计算
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


# 全局客户端实例
client = TushareClient()


def main():
    """测试客户端"""
    print("="*60)
    print("Tushare 客户端测试")
    print("="*60)
    
    # 测试获取股票行情
    print("\n测试1: 获取股票行情")
    quote = client.get_stock_quote('000001')
    if quote:
        print(f"✅ 平安银行: {quote.get('ld', 0)}元 ({quote.get('chp', 0):+.2f}%)")
    else:
        print("❌ 获取失败")
    
    # 测试获取股票信息
    print("\n测试2: 获取股票信息")
    info = client.get_stock_info('000001')
    if info:
        print(f"✅ 行业: {info.get('industry', 'N/A')}")
    else:
        print("❌ 获取失败")
    
    # 测试获取指数
    print("\n测试3: 获取指数行情")
    index = client.get_index_quote('000001')
    if index:
        print(f"✅ 上证指数: {index.get('ld', 0):.2f} ({index.get('chp', 0):+.2f}%)")
    else:
        print("❌ 获取失败")
    
    print(f"\n总请求数: {client.get_request_count()}")
    print("\n✅ 客户端测试完成！")


if __name__ == "__main__":
    main()