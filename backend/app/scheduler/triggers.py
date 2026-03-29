"""触发器管理"""
from datetime import datetime, timedelta
from typing import Optional, List
from app.core.logger import get_logger

logger = get_logger(__name__)


class TriggerManager:
    """触发器管理类 - 支持按需触发采集"""
    
    def __init__(self):
        self._pending_tasks = {}
    
    async def trigger_stock_daily(self, stock_code: str, date: str) -> bool:
        """
        触发单只股票日线数据采集
        
        Args:
            stock_code: 股票代码
            date: 日期
            
        Returns:
            是否触发成功
        """
        from app.services.data_collector import data_collector
        try:
            await data_collector.collect_stock_daily(stock_code, date)
            return True
        except Exception as e:
            logger.error(f"触发采集失败 [{stock_code} {date}]: {e}")
            return False
    
    async def trigger_stock_intraday(self, stock_code: str, date: str) -> bool:
        """
        触发单只股票分时数据采集
        
        Args:
            stock_code: 股票代码
            date: 日期
            
        Returns:
            是否触发成功
        """
        from app.services.data_collector import data_collector
        try:
            await data_collector.collect_stock_intraday(stock_code, date)
            return True
        except Exception as e:
            logger.error(f"触发分时采集失败 [{stock_code} {date}]: {e}")
            return False
    
    async def trigger_index_daily(self, index_code: str, start_date: str, end_date: str) -> bool:
        """
        触发指数日线数据采集
        
        Args:
            index_code: 指数代码
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            是否触发成功
        """
        from app.services.data_collector import data_collector
        try:
            await data_collector.collect_index_daily(index_code, start_date, end_date)
            return True
        except Exception as e:
            logger.error(f"触发指数采集失败 [{index_code}]: {e}")
            return False
    
    async def trigger_concept_data(self, date: str) -> bool:
        """
        触发概念板块数据采集
        
        Args:
            date: 日期
            
        Returns:
            是否触发成功
        """
        from app.services.data_collector import data_collector
        try:
            await data_collector.collect_concept_daily(date)
            return True
        except Exception as e:
            logger.error(f"触发概念采集失败 [{date}]: {e}")
            return False
    
    async def trigger_limit_list(self, date: str) -> bool:
        """
        触发涨跌停数据采集
        
        Args:
            date: 日期
            
        Returns:
            是否触发成功
        """
        from app.services.data_collector import data_collector
        try:
            await data_collector.collect_limit_list(date)
            return True
        except Exception as e:
            logger.error(f"触发涨跌停采集失败 [{date}]: {e}")
            return False
    
    @staticmethod
    def get_date_range(start_date: str, end_date: str) -> List[str]:
        """获取日期范围内的所有日期"""
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        dates = []
        current = start
        while current <= end:
            dates.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        return dates


# 单例
trigger_manager = TriggerManager()
