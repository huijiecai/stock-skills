#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backend Client - 后端API客户端

数据采集脚本使用此客户端将数据提交到后端API，而非直接操作数据库
"""

import requests
from typing import Dict, List, Optional, Union
from datetime import datetime
from config_loader import ConfigLoader
import math


def _clean_nan_values(data: Union[Dict, List]) -> Union[Dict, List]:
    """
    清理数据中的 NaN 值，转换为 None
    
    Args:
        data: 原始数据（字典或列表）
        
    Returns:
        清理后的数据
    """
    if isinstance(data, list):
        return [_clean_nan_values(item) for item in data]
    elif isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if isinstance(value, float) and math.isnan(value):
                result[key] = None
            elif isinstance(value, dict):
                result[key] = _clean_nan_values(value)
            elif isinstance(value, list):
                result[key] = _clean_nan_values(value)
            else:
                result[key] = value
        return result
    else:
        return data


class BackendClient:
    """后端API客户端"""
    
    def __init__(self):
        """
        初始化API客户端（从配置文件读取）
        """
        config = ConfigLoader()
        base_url = config.get('backend', {}).get('url')
        if not base_url:
            raise ValueError("配置文件中未找到 backend.url 配置")
        
        self.base_url = base_url
        self.api_base = f"{base_url}/api"
    
    def _post(self, endpoint: str, data: Union[Dict, List], timeout: int = 30) -> Dict:
        """发送POST请求"""
        url = f"{self.api_base}{endpoint}"
        try:
            # 清理 NaN 值（JSON 无法序列化）
            clean_data = _clean_nan_values(data)
            response = requests.post(url, json=clean_data, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ API请求失败 {url}: {e}")
            raise
    
    def _get(self, endpoint: str, params: Dict = None, timeout: int = 30) -> Dict:
        """发送GET请求"""
        url = f"{self.api_base}{endpoint}"
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"❌ API请求失败 {url}: {e}")
            raise
    
    def collect_market_data(self, date: str, market_data: Dict, stocks: List[Dict]) -> Dict:
        """
        提交市场情绪数据（仅市场概况，向后兼容）
        
        Args:
            date: 交易日期（YYYY-MM-DD）
            market_data: 市场概况数据
            stocks: 涨停个股列表（已废弃，不再使用）
        
        Returns:
            采集结果
        """
        return self._post("/market/collect", {
            "date": date,
            "market_data": market_data,
            "stocks": []  # 空列表，个股数据通过 save_stock_daily 逐个保存
        })
    
    def collect_market_sentiment(self, date: str, market_data: Dict) -> Dict:
        """
        提交市场情绪数据（仅市场概况）
        
        Args:
            date: 交易日期（YYYY-MM-DD）
            market_data: 市场概况数据
        
        Returns:
            保存结果
        """
        return self._post("/market/collect", {
            "date": date,
            "market_data": market_data,
            "stocks": []
        })
    
    def save_stock_daily(self, date: str, stock_data: Dict) -> Dict:
        """
        保存单股票日线数据
        
        Args:
            date: 交易日期（YYYY-MM-DD）
            stock_data: 股票日线数据字典
        
        Returns:
            保存结果
        """
        data = {"date": date}
        data.update(stock_data)
        return self._post("/stocks/daily", data)
    
    def add_stock_to_pool(self, code: str, name: str, market: str, note: str = "") -> Dict:
        """
        添加股票到股票池
        
        Args:
            code: 股票代码
            name: 股票名称
            market: 市场（SH/SZ）
            note: 备注
        
        Returns:
            添加结果
        """
        return self._post("/stocks", {
            "code": code,
            "name": name,
            "market": market,
            "note": note
        })
    
    def create_concept(self, name: str, parent: Optional[str], description: str) -> Dict:
        """
        创建概念
        
        Args:
            name: 概念名称
            parent: 父概念（None表示顶级概念）
            description: 描述
        
        Returns:
            创建结果
        """
        return self._post("/concepts", {
            "name": name,
            "parent": parent,
            "description": description
        })
    
    def get_all_stocks(self) -> List[Dict]:
        """
        获取所有股票列表
        
        Returns:
            股票列表 [{"code": "000001", "name": "平安银行", "market": "SZ"}, ...]
        """
        result = self._get("/stocks")
        return result.get("stocks", [])
    
    def sync_stock_info(self, stocks: List[Dict]) -> Dict:
        """
        批量同步股票信息到 stock_info 表
        
        Args:
            stocks: 股票信息列表，每项包含:
                - stock_code: 股票代码
                - stock_name: 股票名称
                - market: 市场
                - board_type: 板块类型
        
        Returns:
            同步结果
        """
        return self._post("/stocks/sync-info", stocks)
    
    def save_intraday_data(self, date: str, stock_code: str, intraday_data: List[Dict]) -> Dict:
        """
        保存分时数据
        
        Args:
            date: 交易日期（YYYY-MM-DD）
            stock_code: 股票代码
            intraday_data: 分时数据列表
        
        Returns:
            保存结果
        """
        return self._post("/stocks/intraday", {
            "date": date,
            "stock_code": stock_code,
            "intraday_data": intraday_data
        })
    
    def get_intraday_data(self, stock_code: str, date: str) -> List[Dict]:
        """
        获取分时数据
        
        Args:
            stock_code: 股票代码
            date: 交易日期（YYYY-MM-DD）
        
        Returns:
            分时数据列表
        """
        result = self._get(f"/stocks/intraday/{stock_code}/{date}")
        return result.get("data", [])


    def get_stock_intraday_existence(self, stock_code: str, date: str) -> bool:
        """
        检查指定股票指定日期的分时数据是否存在
        
        Args:
            stock_code: 股票代码
            date: 交易日期（YYYY-MM-DD）
        
        Returns:
            True if data exists, False otherwise
        """
        try:
            result = self._get(f"/stocks/intraday-exists/{stock_code}/{date}")
            return result.get("exists", False)
        except Exception:
            # 如果API调用失败，默认返回False（假设不存在）
            return False
    
    def get_stock_intraday_existence_batch(self, stock_code: str, dates: List[str]) -> Dict[str, bool]:
        """
        批量检查指定股票多个日期的分时数据是否存在
        
        Args:
            stock_code: 股票代码
            dates: 交易日期列表（YYYY-MM-DD）
        
        Returns:
            {日期: 是否存在} 字典
        """
        if not dates:
            return {}
        
        try:
            # 调用后端批量检查接口
            result = self._post(f"/stocks/intraday-exists-batch/{stock_code}", {"dates": dates})
            return result.get("exists", {})
        except Exception:
            # 如果API调用失败，默认全部返回False
            return {date: False for date in dates}
    
    def check_market_data_exists(self, date: str) -> bool:
        """
        检查指定日期的市场数据是否存在
        
        Args:
            date: 交易日期（YYYY-MM-DD）
        
        Returns:
            True if data exists, False otherwise
        """
        try:
            result = self._get(f"/market/sentiment/{date}")
            # 如果返回了数据且 success 为 True，说明数据存在
            return result.get("success", False) and result.get("data") is not None
        except Exception:
            # 如果API调用失败（404等），说明数据不存在
            return False


# 模块级别全局实例
def _init_backend_client() -> BackendClient:
    """初始化后端客户端"""
    try:
        return BackendClient()
    except Exception as e:
        print(f"⚠️  初始化后端客户端失败: {e}")
        print("   请检查配置文件中的 backend.url 配置")
        raise


# 全局客户端实例
backend_client = _init_backend_client()


if __name__ == "__main__":
    # 测试
    client = BackendClient()
    print("✅ BackendClient 初始化成功")
    print(f"  后端地址: {client.base_url}")
