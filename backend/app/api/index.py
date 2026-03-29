"""指数相关 API"""
from fastapi import APIRouter, Query
from typing import Optional
from datetime import datetime, timedelta
from sqlalchemy import text

from app.core.database import get_db_session
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/index", tags=["指数"])


def success_response(data=None, message: str = "success"):
    return {"code": 200, "message": message, "data": data}


@router.get("/list")
async def get_index_list():
    """获取指数列表"""
    async with get_db_session() as db:
        result = await db.execute(text("""
            SELECT DISTINCT index_code, index_name 
            FROM index_daily 
            WHERE index_code IN ('000001', '399001', '399006', '000688')
        """))
        rows = result.fetchall()
        
        items = [{"index_code": row[0], "index_name": row[1]} for row in rows]
        return success_response({"items": items})


@router.get("/daily/{code}")
async def get_index_daily(
    code: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """获取指数日线"""
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    async with get_db_session() as db:
        result = await db.execute(
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
        
        return success_response({
            "index_code": code,
            "items": items,
        })


@router.get("/intraday/{code}")
async def get_index_intraday(
    code: str,
    date: Optional[str] = Query(None),
):
    """获取指数分时"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    async with get_db_session() as db:
        result = await db.execute(
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
        
        return success_response({
            "index_code": code,
            "date": date,
            "items": items,
        })
