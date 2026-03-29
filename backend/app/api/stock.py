"""股票相关 API"""
from fastapi import APIRouter, Depends, Query
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import text

from app.core.database import get_db_session
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/stock", tags=["股票"])


# ==================== 响应格式 ====================
def success_response(data=None, message: str = "success"):
    return {"code": 200, "message": message, "data": data}


def error_response(code: int, message: str):
    return {"code": code, "message": message, "data": None}


# ==================== 股票 API ====================

@router.get("/info/{code}")
async def get_stock_info(code: str):
    """获取股票基本信息"""
    async with get_db_session() as db:
        result = await db.execute(
            text("SELECT * FROM stock_info WHERE stock_code = :code"),
            {"code": code}
        )
        row = result.fetchone()
        if row:
            return success_response({
                "stock_code": row[0],
                "stock_name": row[1],
                "industry": row[2],
                "list_date": str(row[3]) if row[3] else None,
                "market": row[4],
            })
    return error_response(404, f"股票 {code} 不存在")


@router.get("/daily/{code}")
async def get_stock_daily(
    code: str,
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
):
    """获取股票日线行情"""
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    
    async with get_db_session() as db:
        # 获取股票名称
        info_result = await db.execute(
            text("SELECT stock_name FROM stock_info WHERE stock_code = :code"),
            {"code": code}
        )
        info_row = info_result.fetchone()
        stock_name = info_row[0] if info_row else ""
        
        # 获取日线数据
        result = await db.execute(
            text("""
                SELECT trade_date, open_price, close_price, high_price, low_price,
                       change_pct, volume, amount, turnover_rate
                FROM stock_daily 
                WHERE stock_code = :code 
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
                "turnover_rate": float(row[8]) if row[8] else 0,
            })
        
        return success_response({
            "stock_code": code,
            "stock_name": stock_name,
            "items": items,
        })


@router.get("/intraday/{code}")
async def get_stock_intraday(
    code: str,
    date: Optional[str] = Query(None, description="日期"),
):
    """获取股票分时数据"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    async with get_db_session() as db:
        result = await db.execute(
            text("""
                SELECT trade_time, price, change_pct, volume, amount, avg_price
                FROM stock_intraday 
                WHERE stock_code = :code AND trade_date = :date
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
                "avg_price": float(row[5]) if row[5] else 0,
            })
        
        return success_response({
            "stock_code": code,
            "date": date,
            "items": items,
        })


@router.post("/realtime")
async def get_stock_realtime(codes: List[str]):
    """批量获取实时行情"""
    async with get_db_session() as db:
        result = await db.execute(
            text("""
                SELECT sd.stock_code, si.stock_name, sd.close_price, sd.change_pct,
                       sd.volume, sd.amount, sd.high_price, sd.low_price, sd.open_price
                FROM stock_daily sd
                LEFT JOIN stock_info si ON sd.stock_code = si.stock_code
                WHERE sd.stock_code = ANY(:codes)
                  AND sd.trade_date = (SELECT MAX(trade_date) FROM stock_daily)
            """),
            {"codes": codes}
        )
        rows = result.fetchall()
        
        items = []
        for row in rows:
            items.append({
                "code": row[0],
                "name": row[1],
                "price": float(row[2]) if row[2] else 0,
                "change_pct": float(row[3]) if row[3] else 0,
                "volume": int(row[4]) if row[4] else 0,
                "amount": float(row[5]) if row[5] else 0,
                "high": float(row[6]) if row[6] else 0,
                "low": float(row[7]) if row[7] else 0,
                "open": float(row[8]) if row[8] else 0,
            })
        
        return success_response({"items": items})


@router.get("/capital-flow/{code}")
async def get_stock_capital_flow(
    code: str,
    date: Optional[str] = Query(None, description="日期"),
):
    """获取资金流向"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    async with get_db_session() as db:
        result = await db.execute(
            text("""
                SELECT * FROM capital_flow 
                WHERE stock_code = :code AND trade_date = :date
            """),
            {"code": code, "date": date}
        )
        row = result.fetchone()
        
        if row:
            return success_response({
                "stock_code": code,
                "date": date,
                "main_net_inflow": float(row[3]) if row[3] else 0,
                "main_net_inflow_pct": float(row[4]) if row[4] else 0,
                "retail_net_inflow": float(row[5]) if row[5] else 0,
                "retail_net_inflow_pct": float(row[6]) if row[6] else 0,
                "super_net_inflow": float(row[7]) if row[7] else 0,
                "big_net_inflow": float(row[8]) if row[8] else 0,
                "mid_net_inflow": float(row[9]) if row[9] else 0,
                "small_net_inflow": float(row[10]) if row[10] else 0,
            })
        
    return success_response({
        "stock_code": code,
        "date": date,
        "main_net_inflow": 0,
        "main_net_inflow_pct": 0,
    })


@router.get("/concepts/{code}")
async def get_stock_concepts(code: str):
    """获取股票所属概念"""
    async with get_db_session() as db:
        result = await db.execute(
            text("""
                SELECT scm.concept_code, ci.concept_name, scm.is_core, scm.reason
                FROM stock_concept_mapping_east scm
                JOIN concept_info_east ci ON scm.concept_code = ci.concept_code
                WHERE scm.stock_code = :code
            """),
            {"code": code}
        )
        rows = result.fetchall()
        
        concepts = []
        for row in rows:
            concepts.append({
                "concept_code": row[0],
                "concept_name": row[1],
                "is_core": row[2],
                "reason": row[3],
            })
        
        return success_response({
            "stock_code": code,
            "concepts": concepts,
        })


@router.get("/search")
async def search_stock(keyword: str = Query(..., description="搜索关键词")):
    """搜索股票"""
    async with get_db_session() as db:
        result = await db.execute(
            text("""
                SELECT stock_code, stock_name, industry, market
                FROM stock_info
                WHERE stock_name LIKE :keyword OR stock_code LIKE :keyword
                LIMIT 20
            """),
            {"keyword": f"%{keyword}%"}
        )
        rows = result.fetchall()
        
        items = []
        for row in rows:
            items.append({
                "stock_code": row[0],
                "stock_name": row[1],
                "industry": row[2],
                "market": row[3],
            })
        
        return success_response({"items": items})
