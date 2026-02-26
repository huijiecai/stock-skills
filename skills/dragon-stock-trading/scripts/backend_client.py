#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Backend Client - 后端API客户端

数据采集脚本使用此客户端将数据提交到后端API，而非直接操作数据库
"""

import requests
from typing import Dict, List, Optional
from datetime import datetime
from config_loader import ConfigLoader


class BackendClient:
    """后端API客户端"""
    
    def __init__(self, base_url: str = None):
        """
        初始化API客户端
        
        Args:
            base_url: 后端服务地址（不提供则从配置文件读取）
        """
        if base_url is None:
            config = ConfigLoader()
            base_url = config.get('backend', {}).get('url', 'http://localhost:8000')
        
        self.base_url = base_url
        self.api_base = f"{base_url}/api"
    
    def _post(self, endpoint: str, data: Dict, timeout: int = 30) -> Dict:
        """发送POST请求"""
        url = f"{self.api_base}{endpoint}"
        try:
            response = requests.post(url, json=data, timeout=timeout)
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
        提交市场数据采集结果
        
        Args:
            date: 交易日期（YYYY-MM-DD）
            market_data: 市场概况数据
            stocks: 涨停个股列表
        
        Returns:
            采集结果
        """
        return self._post("/market/collect", {
            "date": date,
            "market_data": market_data,
            "stocks": stocks
        })
    
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

if __name__ == "__main__":
    # 测试
    client = BackendClient()
    print("✅ BackendClient 初始化成功")
    print(f"  后端地址: {client.base_url}")
