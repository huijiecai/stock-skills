"""
同花顺概念数据 API
"""
from fastapi import APIRouter, Query
from typing import Optional
from app.services.data_service import get_data_service

router = APIRouter(tags=["同花顺数据"])


@router.get("/concepts")
async def get_concepts(
    search: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(100, description="返回数量限制")
):
    """获取同花顺概念列表"""
    service = get_data_service()
    return service.get_ths_concepts(search=search, limit=limit)


@router.get("/concepts/{concept_code}/members")
async def get_concept_members(concept_code: str):
    """获取概念成分股"""
    service = get_data_service()
    return service.get_ths_concept_members(concept_code)


@router.get("/stocks/{stock_code}/concepts")
async def get_stock_concepts(stock_code: str):
    """获取股票所属概念"""
    service = get_data_service()
    return service.get_stock_concepts(stock_code)


@router.get("/concepts/daily")
async def get_concept_daily(
    concept_code: Optional[str] = Query(None, description="概念代码"),
    trade_date: Optional[str] = Query(None, description="交易日期"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    limit: int = Query(100, description="返回数量限制")
):
    """获取概念日行情"""
    service = get_data_service()
    return service.get_ths_concept_daily(
        concept_code=concept_code,
        trade_date=trade_date,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )


@router.get("/hot-rank")
async def get_hot_rank(
    trade_date: Optional[str] = Query(None, description="交易日期"),
    rank_time: Optional[str] = Query(None, description="排行时间"),
    limit: int = Query(100, description="返回数量限制")
):
    """获取个股热榜"""
    service = get_data_service()
    return service.get_ths_hot_rank(
        trade_date=trade_date,
        rank_time=rank_time,
        limit=limit
    )


@router.get("/limit-list")
async def get_limit_list(
    trade_date: Optional[str] = Query(None, description="交易日期"),
    limit_type: Optional[str] = Query(None, description="板单类别"),
    start_date: Optional[str] = Query(None, description="开始日期"),
    end_date: Optional[str] = Query(None, description="结束日期"),
    limit: int = Query(100, description="返回数量限制")
):
    """获取涨跌停榜单"""
    service = get_data_service()
    return service.get_ths_limit_list(
        trade_date=trade_date,
        limit_type=limit_type,
        start_date=start_date,
        end_date=end_date,
        limit=limit
    )


@router.get("/limit-ladder/{trade_date}")
async def get_limit_ladder(trade_date: str):
    """获取连板天梯"""
    service = get_data_service()
    return service.get_limit_ladder(trade_date)
