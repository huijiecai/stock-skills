"""概念板块相关 API"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy import text

from app.core.database import get_db_session
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/concept", tags=["概念板块"])


def success_response(data=None, message: str = "success"):
    return {"code": 200, "message": message, "data": data}


@router.get("/list")
async def get_concept_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取概念板块列表"""
    async with get_db_session() as db:
        offset = (page - 1) * page_size
        result = await db.execute(
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
        
        return success_response({"items": items, "page": page, "page_size": page_size})


@router.get("/daily/{code}")
async def get_concept_daily(
    code: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """获取概念板块日线"""
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    async with get_db_session() as db:
        # 获取概念名称
        info_result = await db.execute(
            text("SELECT concept_name FROM concept_info_east WHERE concept_code = :code"),
            {"code": code}
        )
        info_row = info_result.fetchone()
        concept_name = info_row[0] if info_row else ""
        
        result = await db.execute(
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
        
        return success_response({
            "concept_code": code,
            "concept_name": concept_name,
            "items": items,
        })


@router.get("/intraday/{code}")
async def get_concept_intraday(
    code: str,
    date: Optional[str] = Query(None),
):
    """获取概念板块分时"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    async with get_db_session() as db:
        result = await db.execute(
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
        
        return success_response({
            "concept_code": code,
            "date": date,
            "items": items,
        })


@router.get("/components/{code}")
async def get_concept_components(code: str):
    """获取概念板块成分股"""
    async with get_db_session() as db:
        result = await db.execute(
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
        
        return success_response({"concept_code": code, "items": items})


@router.get("/rank")
async def get_concept_rank(
    date: Optional[str] = Query(None),
    sort_by: str = Query("change_pct", description="排序字段"),
    order: str = Query("desc", description="排序方向"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取概念板块涨幅榜"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    order_sql = "DESC" if order == "desc" else "ASC"
    sort_field = "change_pct" if sort_by == "change_pct" else "amount"
    
    async with get_db_session() as db:
        result = await db.execute(
            text(f"""
                SELECT cd.concept_code, ci.concept_name, cd.close_price, cd.change_pct,
                       cd.volume, cd.amount
                FROM concept_daily_east cd
                JOIN concept_info_east ci ON cd.concept_code = ci.concept_code
                WHERE cd.trade_date = :date
                ORDER BY cd.{sort_field} {order_sql}
                LIMIT :limit OFFSET :offset
            """),
            {"date": date, "limit": page_size, "offset": (page - 1) * page_size}
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
        
        return success_response({"date": date, "items": items})


@router.get("/search")
async def search_concept(keyword: str = Query(..., description="搜索关键词")):
    """搜索概念板块"""
    async with get_db_session() as db:
        result = await db.execute(
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
        
        return success_response({"items": items})
