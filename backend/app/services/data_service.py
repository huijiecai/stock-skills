import sys
from pathlib import Path
from typing import Optional

# 添加skills/dragon-stock-trading/scripts目录到Python路径
project_root = Path(__file__).parent.parent.parent
scripts_path = project_root / "skills" / "dragon-stock-trading" / "scripts"
sys.path.insert(0, str(scripts_path))

# 导入现有模块
from query_service import QueryService
from market_fetcher import MarketDataFetcher
from concept_manager import ConceptManager
from stock_concept_manager import StockConceptManager


class DataService:
    """数据服务，封装对现有scripts模块的调用"""
    
    def __init__(self):
        db_path = project_root / "skills" / "dragon-stock-trading" / "data" / "dragon_stock.db"
        self.db_path = str(db_path)
        self.query_service = QueryService(self.db_path)
        self.market_fetcher = MarketDataFetcher(self.db_path)
        self.concept_manager = ConceptManager(self.db_path)
        self.stock_concept_manager = StockConceptManager(self.db_path)
        
    def get_market_status(self, date: str):
        """获取市场情绪数据"""
        return self.query_service.get_market_status(date)
    
    def get_stock_with_concept(self, stock_code: str, date: str):
        """获取个股信息（含概念）"""
        return self.query_service.get_stock_with_concept(stock_code, date)
    
    def get_stock_popularity_rank(self, date: str, limit: int = 30):
        """获取人气榜"""
        return self.query_service.get_stock_popularity_rank(date, limit)
    
    def get_concept_leaders(self, date: str, min_limit_up: int = 1):
        """获取概念龙头"""
        return self.query_service.get_concept_leaders(date, min_limit_up)
    
    def get_concept_analysis(self, concept: str, date: str):
        """获取概念分析"""
        return self.query_service.get_concept_analysis(concept, date)
    
    def list_concept_stocks(self, concept_name: str):
        """获取概念下的股票"""
        return self.stock_concept_manager.list_concept_stocks(concept_name)
    
    def add_stock_to_concept(self, stock_code: str, concept_name: str, is_core: bool, note: str):
        """添加股票到概念"""
        return self.stock_concept_manager.add_stock(stock_code, concept_name, is_core, note)
    
    def remove_stock_from_concept(self, stock_code: str, concept_name: str):
        """从概念中移除股票"""
        return self.stock_concept_manager.remove_stock(stock_code, concept_name)


# 单例
_data_service: Optional[DataService] = None

def get_data_service() -> DataService:
    """获取数据服务单例"""
    global _data_service
    if _data_service is None:
        _data_service = DataService()
    return _data_service
