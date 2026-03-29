"""指数服务层"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.logger import get_logger

logger = get_logger(__name__)


class IndexService:
    """指数业务服务"""
    
    async def get_index_list(self) -> Dict:
        """获取指数列表"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(text("""
                SELECT DISTINCT index_code, index_name 
                FROM index_daily
                WHERE index_code IN ('000001', '399001', '399006', '000688')
            """))
            rows = result.fetchall()
            
            items = [{"index_code": row[0], "index_name": row[1]} for row in rows]
            return {"items": items}
    
    async def get_index_daily(
        self, 
        code: str, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None
    ) -> Dict:
        """获取指数日线"""
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT trade_date, index_name, open_price, close_price, high_price, low_price,
                           change_pct, volume, amount
                    FROM index_daily 
                    WHERE index_code = :code 
                      AND trade_date BETWEEN :start_date AND :end_date
                    ORDER BY trade_date DESC
                """),
                {"code": code, "start_date": start_date, "end_date": end_date}
            )
            rows = result.fetchall()
            
            items = []
            for row in rows:
                items.append({
                    "trade_date": str(row[0]),
                    "index_name": row[1],
                    "open": float(row[2]) if row[2] else 0,
                    "close": float(row[3]) if row[3] else 0,
                    "high": float(row[4]) if row[4] else 0,
                    "low": float(row[5]) if row[5] else 0,
                    "change_pct": float(row[6]) if row[6] else 0,
                    "volume": int(row[7]) if row[7] else 0,
                    "amount": float(row[8]) if row[8] else 0,
                })
            
            return {
                "index_code": code,
                "items": items,
            }
    
    async def get_index_intraday(self, code: str, date: Optional[str] = None) -> Dict:
        """获取指数分时"""
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT trade_time, price, change_pct, volume, amount
                    FROM index_intraday 
                    WHERE index_code = :code AND trade_date = :date
                    ORDER BY trade_time
                """),
                {"code": code, "date": date}
            )
            rows = result.fetchall()
            
            items = []
            for row in rows:
                items.append({
                    "time": str(row[0])[:5] if row[0] else "00:00",
                    "price": float(row[1]) if row[1] else 0,
                    "change_pct": float(row[2]) if row[2] else 0,
                    "volume": int(row[3]) if row[3] else 0,
                    "amount": float(row[4]) if row[4] else 0,
                })
            
            return {
                "index_code": code,
                "date": date,
                "items": items,
            }
    
    async def get_index_snapshot(self, date: str) -> List[Dict]:
        """获取指定日期的指数快照"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT index_code, index_name, close_price, change_pct
                    FROM index_daily 
                    WHERE trade_date = :date
                      AND index_code IN ('000001', '399001', '399006', '000688')
                """),
                {"date": date}
            )
            rows = result.fetchall()
            
            indices = []
            for row in rows:
                indices.append({
                    "index_code": row[0],
                    "index_name": row[1],
                    "close": float(row[2]) if row[2] else 0,
                    "change_pct": float(row[3]) if row[3] else 0,
                })
            
            return indices


# 单例
index_service = IndexService()
