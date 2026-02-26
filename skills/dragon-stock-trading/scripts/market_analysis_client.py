"""
Market Analysis Client - 用于LLM通过API访问龙头战法Web平台数据

LLM可以通过这个client来获取市场分析数据，无需直接访问数据库
"""

import requests
from typing import Dict, List, Optional
from datetime import datetime


class MarketAnalysisClient:
    """龙头战法API客户端"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        初始化API客户端
        
        Args:
            base_url: API服务器地址（默认：http://localhost:8000）
        """
        self.base_url = base_url
        self.api_base = f"{base_url}/api"
    
    def _get(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """发送GET请求"""
        url = f"{self.api_base}{endpoint}"
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    
    def _post(self, endpoint: str, data: Dict) -> Dict:
        """发送POST请求"""
        url = f"{self.api_base}{endpoint}"
        response = requests.post(url, json=data, timeout=10)
        response.raise_for_status()
        return response.json()
    
    # ==================== 市场数据 ====================
    
    def get_market_sentiment(self, date: Optional[str] = None) -> Dict:
        """
        获取市场情绪数据
        
        Args:
            date: 日期（格式：YYYY-MM-DD），不传则为今日
        
        Returns:
            市场情绪数据（涨停/跌停家数、连板高度、市场阶段）
        """
        if date:
            return self._get(f"/market/sentiment/{date}")
        else:
            return self._get("/market/sentiment")
    
    # ==================== 股票数据 ====================
    
    def get_stock_list(self) -> List[Dict]:
        """
        获取股票池
        
        Returns:
            股票列表
        """
        result = self._get("/stocks")
        return result.get("stocks", [])
    
    def get_stock_detail(self, code: str, date: Optional[str] = None) -> Dict:
        """
        获取股票详情
        
        Args:
            code: 股票代码
            date: 日期（可选）
        
        Returns:
            股票详情（含概念归属）
        """
        params = {"date": date} if date else {}
        return self._get(f"/stocks/{code}/detail", params)
    
    def get_popularity_rank(self, date: str, limit: int = 30) -> List[Dict]:
        """
        获取人气榜
        
        Args:
            date: 日期
            limit: 返回数量（默认30）
        
        Returns:
            人气榜列表
        """
        result = self._get(f"/stocks/popularity/{date}", {"limit": limit})
        return result.get("data", [])
    
    # ==================== 概念数据 ====================
    
    def get_concepts(self) -> Dict:
        """
        获取概念树
        
        Returns:
            概念层级结构
        """
        result = self._get("/concepts")
        return result.get("data", {})
    
    def get_concept_stocks(self, concept_name: str) -> List[Dict]:
        """
        获取概念下的股票
        
        Args:
            concept_name: 概念名称
        
        Returns:
            股票列表
        """
        result = self._get(f"/concepts/{concept_name}/stocks")
        return result.get("stocks", [])
    
    def get_concept_heatmap(self, date: str) -> List[Dict]:
        """
        获取概念热力图数据
        
        Args:
            date: 日期
        
        Returns:
            概念热度数据
        """
        result = self._get(f"/concepts/heatmap/{date}")
        return result.get("data", [])
    
    def get_concept_analysis(self, concept_name: str, date: str) -> Dict:
        """
        获取概念分析
        
        Args:
            concept_name: 概念名称
            date: 日期
        
        Returns:
            概念分析数据
        """
        result = self._get(f"/concepts/{concept_name}/analysis/{date}")
        return result.get("data", {})
    
    # ==================== 龙头分析 ====================
    
    def analyze_stock(self, code: str, date: Optional[str] = None) -> Dict:
        """
        分析单只股票是否符合龙头战法
        
        Args:
            code: 股票代码
            date: 分析日期（可选，默认今日）
        
        Returns:
            分析结果，包含：
            - success: 是否成功
            - is_leader_candidate: 是否符合龙头标准
            - market_phase: 市场阶段
            - popularity_rank: 人气排名
            - concepts: 概念归属
            - suggestion: 操作建议
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        return self._post("/analysis/stock", {
            "code": code,
            "date": date
        })
    
    def analyze_concept(self, concept_name: str, date: Optional[str] = None) -> Dict:
        """
        分析概念内所有股票
        
        Args:
            concept_name: 概念名称
            date: 分析日期（可选，默认今日）
        
        Returns:
            概念分析结果
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        return self._post("/analysis/concept", {
            "concept_name": concept_name,
            "date": date
        })
    
    def get_leaders(self, date: str) -> Dict:
        """
        获取当日龙头候选
        
        Args:
            date: 日期
        
        Returns:
            龙头候选列表（概念龙头和人气龙头）
        """
        return self._get(f"/analysis/leaders/{date}")


# 使用示例
if __name__ == "__main__":
    client = MarketAnalysisClient()
    
    # 获取市场情绪
    print("=== 市场情绪 ===")
    market = client.get_market_sentiment()
    print(market)
    
    # 分析股票
    print("\n=== 分析股票 ===")
    analysis = client.analyze_stock("002342", "2026-02-25")
    print(f"股票: {analysis.get('stock_name')}")
    print(f"符合龙头标准: {analysis.get('is_leader_candidate')}")
    print(f"建议: {analysis.get('suggestion')}")
    
    # 获取人气榜
    print("\n=== 人气榜 Top 10 ===")
    popularity = client.get_popularity_rank("2026-02-25", 10)
    for i, stock in enumerate(popularity, 1):
        print(f"{i}. {stock['stock_name']} ({stock['stock_code']}): {stock['change_percent']*100:.2f}%")
