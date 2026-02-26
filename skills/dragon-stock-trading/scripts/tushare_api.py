#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tushare API 调用器 - 底层API调用实现
专门负责与Tushare API的直接交互

注意：使用自定义API域名（高积分用户专用）
"""

import tushare as ts
import tushare.pro.client as client
import requests
import time
from typing import Dict, List, Optional

# 【重要】全局设置自定义API域名（高积分用户专用，速度更快）
# 必须在创建任何 ts.pro_api() 实例之前设置
client.DataApi._DataApi__http_url = "http://tushare.xyz"


class TushareAPI:
    """Tushare API底层调用器（使用自定义域名）"""
    
    def __init__(self, token: str):
        """
        初始化API调用器
        
        Args:
            token: Tushare token
        """
        self.token = token
        self.base_url = "http://tushare.xyz"
        
        # 使用官方SDK（已配置自定义域名）
        self.pro = ts.pro_api(token)
        
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
    
    def get_stock_daily(self, ts_code: str, trade_date: str = "") -> Optional[Dict]:
        """
        获取股票日线数据（使用官方SDK）
        
        Args:
            ts_code: Tushare股票代码（如 000001.SZ）
            trade_date: 交易日期（格式：20260226，留空则获取最近一条）
            
        Returns:
            日线数据字典
        """
        try:
            # 如果没有指定日期，使用 start_date 限制只返回最近数据
            if trade_date:
                df = self.pro.daily(
                    ts_code=ts_code,
                    trade_date=trade_date,
                    fields='ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
                )
            else:
                # 获取最近1条数据（避免返回全部历史数据导致超时）
                import datetime
                end_date = datetime.datetime.now().strftime('%Y%m%d')
                start_date = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime('%Y%m%d')
                df = self.pro.daily(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    fields='ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
                )
            
            if df is None or df.empty:
                return None
            
            return {
                'items': df.values.tolist(),
                'fields': df.columns.tolist()
            }
        except Exception as e:
            print(f"Tushare API错误: {e}")
            return None
    
    def get_index_daily(self, ts_code: str, trade_date: str = "") -> Optional[Dict]:
        """
        获取指数日线数据（使用官方SDK）
        
        Args:
            ts_code: Tushare指数代码（如 000001.SH）
            trade_date: 交易日期（格式：20260226，留空则获取最近一条）
            
        Returns:
            指数日线数据字典
        """
        try:
            # 如果没有指定日期，使用 start_date 限制只返回最近数据
            if trade_date:
                df = self.pro.index_daily(
                    ts_code=ts_code,
                    trade_date=trade_date,
                    fields='ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
                )
            else:
                # 获取最近1条数据（避免返回全部历史数据导致超时）
                import datetime
                end_date = datetime.datetime.now().strftime('%Y%m%d')
                start_date = (datetime.datetime.now() - datetime.timedelta(days=7)).strftime('%Y%m%d')
                df = self.pro.index_daily(
                    ts_code=ts_code,
                    start_date=start_date,
                    end_date=end_date,
                    fields='ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount'
                )
            
            if df is None or df.empty:
                return None
            
            return {
                'items': df.values.tolist(),
                'fields': df.columns.tolist()
            }
        except Exception as e:
            print(f"Tushare API错误: {e}")
            return None
    
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


    def get_limit_list(self, trade_date: str, limit_type: str = None) -> Optional[Dict]:
        """
        获取涨跌停列表（使用官方SDK）
        
        Args:
            trade_date: 交易日期（格式：20260226）
            limit_type: 涨跌停类型（U=涨停, D=跌停, Z=炸板, None=全部）
            
        Returns:
            涨跌停数据字典 {'items': [[...], [...]], 'fields': [...]}
        """
        try:
            # 使用官方SDK调用（支持自定义域名）
            df = self.pro.limit_list_d(
                trade_date=trade_date,
                limit_type=limit_type,
                fields='ts_code,trade_date,name,limit,limit_times,pct_chg'
            )
            
            if df is None or df.empty:
                return None
            
            # 转换为与_post相同的格式
            return {
                'items': df.values.tolist(),
                'fields': df.columns.tolist()
            }
        except Exception as e:
            print(f"Tushare API错误: {e}")
            return None


# 全局API实例（供TushareClient使用）
_tushare_api = None


def get_tushare_api(token: str = None) -> TushareAPI:
    """
    获取TushareAPI单例实例
    
    Args:
        token: Tushare token，如果不提供则从配置文件读取
        
    Returns:
        TushareAPI实例
    """
    global _tushare_api
    if _tushare_api is None:
        if token is None:
            from config_loader import ConfigLoader
            config = ConfigLoader()
            token = config.get_tushare_token()
            if not token:
                raise ValueError("未配置 Tushare Token，请在 config.yaml 中设置 tushare.token")
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