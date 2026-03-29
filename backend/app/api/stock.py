"""股票相关 API"""
from fastapi import APIRouter, Query
from typing import Optional, List

from app.services.stock_service import stock_service
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/stock", tags=["股票"])


def success_response(data=None, message: str = "success"):
    return {"code": 200, "message": message, "data": data}


def error_response(code: int, message: str):
    return {"code": code, "message": message, "data": None}


@router.get("/info/{code}")
async def get_stock_info(code: str):
    """获取股票基本信息"""
    result = await stock_service.get_stock_info(code)
    if result:
        return success_response(result)
    return error_response(404, f"股票 {code} 不存在")


@router.get("/daily/{code}")
async def get_stock_daily(
    code: str,
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
):
    """获取股票日线行情"""
    result = await stock_service.get_stock_daily(code, start_date, end_date)
    return success_response(result)


@router.get("/intraday/{code}")
async def get_stock_intraday(
    code: str,
    date: Optional[str] = Query(None, description="日期"),
):
    """获取股票分时数据"""
    result = await stock_service.get_stock_intraday(code, date)
    return success_response(result)


@router.post("/realtime")
async def get_stock_realtime(codes: List[str]):
    """批量获取实时行情"""
    result = await stock_service.get_stock_realtime(codes)
    return success_response(result)


@router.get("/capital-flow/{code}")
async def get_stock_capital_flow(
    code: str,
    date: Optional[str] = Query(None, description="日期"),
):
    """获取资金流向"""
    result = await stock_service.get_stock_capital_flow(code, date)
    return success_response(result)


@router.get("/concepts/{code}")
async def get_stock_concepts(code: str):
    """获取股票所属概念"""
    result = await stock_service.get_stock_concepts(code)
    return success_response(result)


@router.get("/search")
async def search_stock(keyword: str = Query(..., description="搜索关键词")):
    """搜索股票"""
    result = await stock_service.search_stock(keyword)
    return success_response(result)
