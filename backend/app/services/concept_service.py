"""概念板块服务层"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from sqlalchemy import text

from app.core.database import AsyncSessionLocal
from app.core.logger import get_logger

logger = get_logger(__name__)


class ConceptService:
    """概念板块业务服务"""
    
    async def get_concept_list(self, page: int = 1, page_size: int = 20) -> Dict:
        """获取概念板块列表"""
        async with AsyncSessionLocal() as session:
            offset = (page - 1) * page_size
            result = await session.execute(
                text("""
                    SELECT concept_code, concept_name, component_count
                    FROM concept_info_east
                    ORDER BY component_count DESC
                    LIMIT :limit OFFSET :offset
                """),
                {"limit": page_size, "offset": offset}
            )
            rows = result.fetchall()
            
            items = []
            for row in rows:
                items.append({
                    "concept_code": row[0],
                    "concept_name": row[1],
                    "component_count": row[2],
                })
            
            return {"items": items, "page": page, "page_size": page_size}
    
    async def get_concept_info(self, code: str) -> Optional[Dict]:
        """获取概念详情"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT * FROM concept_info_east WHERE concept_code = :code"),
                {"code": code}
            )
            row = result.fetchone()
            if row:
                return {
                    "concept_code": row[0],
                    "concept_name": row[1],
                    "component_count": row[2],
                    "source": "east"
                }
        return None
    
    async def get_concept_daily(
        self, 
        code: str, 
        start_date: Optional[str] = None, 
        end_date: Optional[str] = None
    ) -> Dict:
        """获取概念板块日线"""
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        
        async with AsyncSessionLocal() as session:
            # 获取概念名称
            info_result = await session.execute(
                text("SELECT concept_name FROM concept_info_east WHERE concept_code = :code"),
                {"code": code}
            )
            info_row = info_result.fetchone()
            concept_name = info_row[0] if info_row else ""
            
            result = await session.execute(
                text("""
                    SELECT trade_date, open_price, close_price, high_price, low_price,
                           change_pct, volume, amount
                    FROM concept_daily_east 
                    WHERE concept_code = :code 
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
                    "open": float(row[1]) if row[1] else 0,
                    "close": float(row[2]) if row[2] else 0,
                    "high": float(row[3]) if row[3] else 0,
                    "low": float(row[4]) if row[4] else 0,
                    "change_pct": float(row[5]) if row[5] else 0,
                    "volume": int(row[6]) if row[6] else 0,
                    "amount": float(row[7]) if row[7] else 0,
                })
            
            return {
                "concept_code": code,
                "concept_name": concept_name,
                "items": items,
            }
    
    async def get_concept_intraday(self, code: str, date: Optional[str] = None) -> Dict:
        """获取概念板块分时"""
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT trade_time, price, change_pct, volume, amount
                    FROM concept_intraday_east 
                    WHERE concept_code = :code AND trade_date = :date
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
                "concept_code": code,
                "date": date,
                "items": items,
            }
    
    async def get_concept_components(self, code: str) -> Dict:
        """获取概念板块成分股"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT scm.stock_code, si.stock_name, scm.is_core, scm.reason
                    FROM stock_concept_mapping_east scm
                    LEFT JOIN stock_info si ON scm.stock_code = si.stock_code
                    WHERE scm.concept_code = :code
                """),
                {"code": code}
            )
            rows = result.fetchall()
            
            items = []
            for row in rows:
                items.append({
                    "stock_code": row[0],
                    "stock_name": row[1] or "",
                    "is_core": row[2],
                    "reason": row[3] or "",
                })
            
            return {"concept_code": code, "items": items}
    
    async def get_concept_rank(
        self, 
        date: Optional[str] = None, 
        sort_by: str = "change_pct", 
        order: str = "desc",
        page: int = 1,
        page_size: int = 20
    ) -> Dict:
        """获取概念板块涨幅榜"""
        order_sql = "DESC" if order == "desc" else "ASC"
        sort_field = "change_pct" if sort_by == "change_pct" else "amount"
        
        async with AsyncSessionLocal() as session:
            if not date:
                # 从概念日线表获取最新日期
                result = await session.execute(
                    text("SELECT MAX(trade_date) FROM concept_daily_east")
                )
                latest = result.scalar()
                if latest:
                    query_date = latest
                else:
                    query_date = datetime.now().date()
            else:
                query_date = datetime.strptime(date, "%Y-%m-%d").date()
            
            result = await session.execute(
                text(f"""
                    SELECT cd.concept_code, ci.concept_name, cd.close_price, cd.change_pct,
                           cd.volume, cd.amount
                    FROM concept_daily_east cd
                    JOIN concept_info_east ci ON cd.concept_code = ci.concept_code
                    WHERE cd.trade_date = :date
                    ORDER BY cd.{sort_field} {order_sql}
                    LIMIT :limit OFFSET :offset
                """),
                {"date": query_date, "limit": page_size, "offset": (page - 1) * page_size}
            )
            rows = result.fetchall()
            
            items = []
            for i, row in enumerate(rows, 1):
                items.append({
                    "rank": (page - 1) * page_size + i,
                    "concept_code": row[0],
                    "concept_name": row[1],
                    "close": float(row[2]) if row[2] else 0,
                    "change_pct": float(row[3]) if row[3] else 0,
                    "volume": int(row[4]) if row[4] else 0,
                    "amount": float(row[5]) if row[5] else 0,
                })
            
            return {"date": str(query_date), "items": items, "total": len(items)}
    
    async def search_concept(self, keyword: str) -> Dict:
        """搜索概念板块"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT concept_code, concept_name, component_count
                    FROM concept_info_east
                    WHERE concept_name LIKE :keyword OR concept_code LIKE :keyword
                    LIMIT 20
                """),
                {"keyword": f"%{keyword}%"}
            )
            rows = result.fetchall()
            
            items = []
            for row in rows:
                items.append({
                    "concept_code": row[0],
                    "concept_name": row[1],
                    "component_count": row[2],
                })
            
            return {"items": items}
    
    async def get_hot_concepts(self, date: str, limit: int = 5) -> List[Dict]:
        """获取热门板块（涨幅前N）"""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("""
                    SELECT cd.concept_code, ci.concept_name, cd.change_pct
                    FROM concept_daily_east cd
                    JOIN concept_info_east ci ON cd.concept_code = ci.concept_code
                    WHERE cd.trade_date = :date
                    ORDER BY cd.change_pct DESC
                    LIMIT :limit
                """),
                {"date": date, "limit": limit}
            )
            rows = result.fetchall()
            
            concepts = []
            for row in rows:
                concepts.append({
                    "code": row[0],
                    "name": row[1],
                    "change_pct": float(row[2]) if row[2] else 0,
                })
            
            return concepts


# 单例
concept_service = ConceptService()
