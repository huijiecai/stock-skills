"""市场数据相关 API"""
from fastapi import APIRouter, Query
from typing import Optional

from app.services.market_service import market_service
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/market", tags=["市场"])


def success_response(data=None, message: str = "success"):
    return {"code": 200, "message": message, "data": data}


# ==================== 市场概览 ====================

@router.get("/latest-trade-date")
async def get_latest_trade_date():
    """
    获取最近交易日
    
    返回数据库中有数据的最近交易日
    """
    result = await market_service.get_latest_trade_date()
    return success_response(result)


@router.get("/snapshot")
async def get_market_snapshot(
    date: Optional[str] = Query(None, description="日期"),
):
    """
    获取市场快照
    
    返回涨停家数、跌停家数、炸板家数、封板率等市场情绪指标
    """
    result = await market_service.get_market_snapshot(date)
    return success_response(result)


@router.get("/statistics")
async def get_market_statistics(
    date: Optional[str] = Query(None, description="日期"),
):
    """
    获取市场统计
    
    返回涨停家数、跌停家数、炸板家数、封板率等
    """
    result = await market_service.get_market_snapshot(date)
    return success_response(result)


# ==================== 涨跌停数据 ====================

@router.get("/limit-up")
async def get_limit_up_list(
    date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """获取涨停股列表"""
    result = await market_service.get_limit_up_list(date, page, page_size)
    return success_response(result)


@router.get("/limit-down")
async def get_limit_down_list(
    date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """获取跌停股列表"""
    result = await market_service.get_limit_down_list(date, page, page_size)
    return success_response(result)


# ==================== 连板天梯 ====================

@router.get("/continuous-board")
async def get_continuous_board(
    date: Optional[str] = Query(None),
):
    """获取连板天梯"""
    result = await market_service.get_continuous_board(date)
    return success_response(result)


# ==================== 炸板股 ====================

@router.get("/broken-board")
async def get_broken_board_list(
    date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """获取炸板股列表"""
    result = await market_service.get_broken_board_list(date, page, page_size)
    return success_response(result)


# ==================== 个股排行 ====================

@router.get("/rank")
async def get_stock_rank(
    date: Optional[str] = Query(None),
    rank_type: str = Query("change_pct", description="排行类型: change_pct/amount/capital_flow"),
    direction: str = Query("up", description="up/down"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
):
    """获取个股排行"""
    result = await market_service.get_stock_rank(date, rank_type, direction, page, page_size)
    return success_response(result)


@router.get("/stock-ranking")
async def get_stock_ranking(
    date: Optional[str] = Query(None),
    sort: str = Query("change_pct", description="排序字段"),
    order: str = Query("desc", description="排序方向: desc/asc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取个股排行（前端接口）"""
    # 转换参数
    rank_type = sort
    direction = "up" if order == "desc" else "down"
    result = await market_service.get_stock_rank(date, rank_type, direction, page, page_size)
    return success_response(result)


# ==================== 历史数据查询 ====================

@router.get("/history/seal-rate")
async def get_seal_rate_history(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """获取封板率历史"""
    result = await market_service.get_seal_rate_history(start_date, end_date)
    return success_response(result)


@router.get("/history/limit-times")
async def get_limit_times_history(
    stock_code: str = Query(..., description="股票代码"),
    limit_type: str = Query("U", description="涨停U/跌停D"),
    limit: int = Query(30, ge=1, le=100),
):
    """获取个股连板次数历史"""
    result = await market_service.get_limit_times_history(stock_code, limit_type, limit)
    return success_response(result)
