"""
同花顺概念数据 API
"""
from fastapi import APIRouter, Query, HTTPException
from typing import Optional, List
from pydantic import BaseModel
from app.services.data_service import get_data_service

router = APIRouter(tags=["同花顺数据"])


# ==================== 数据模型 ====================

class ThsConceptItem(BaseModel):
    ts_code: str
    name: str
    concept_type: Optional[str] = None
    component_count: Optional[int] = None
    list_date: Optional[str] = None

class ThsMemberItem(BaseModel):
    concept_code: str
    concept_name: str
    stock_code: str
    stock_name: Optional[str] = None

class ThsConceptDailyItem(BaseModel):
    trade_date: str
    concept_code: str
    concept_name: Optional[str] = None
    pre_close: Optional[float] = None
    open: Optional[float] = None
    close: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    pct_change: Optional[float] = None
    vol: Optional[float] = None
    turnover_rate: Optional[float] = None
    total_mv: Optional[float] = None
    float_mv: Optional[float] = None

class ThsHotRankItem(BaseModel):
    trade_date: str
    rank_time: str
    ts_code: str
    ts_name: Optional[str] = None
    rank: Optional[int] = None
    hot: Optional[float] = None
    pct_change: Optional[float] = None
    current_price: Optional[float] = None
    concept: Optional[str] = None
    rank_reason: Optional[str] = None

class ThsLimitListItem(BaseModel):
    trade_date: str
    ts_code: str
    ts_name: Optional[str] = None
    price: Optional[float] = None
    pct_chg: Optional[float] = None
    limit_type: str
    tag: Optional[str] = None
    status: Optional[str] = None
    lu_desc: Optional[str] = None
    open_num: Optional[int] = None
    first_lu_time: Optional[str] = None
    last_lu_time: Optional[str] = None
    limit_order: Optional[float] = None
    limit_amount: Optional[float] = None
    lu_limit_order: Optional[float] = None
    turnover_rate: Optional[float] = None
    turnover: Optional[float] = None
    free_float: Optional[float] = None
    sum_float: Optional[float] = None
    limit_up_suc_rate: Optional[float] = None
    market_type: Optional[str] = None

class ThsDataBatch(BaseModel):
    concepts: Optional[List[ThsConceptItem]] = None
    members: Optional[List[ThsMemberItem]] = None
    concept_daily: Optional[List[ThsConceptDailyItem]] = None
    hot_rank: Optional[List[ThsHotRankItem]] = None
    limit_list: Optional[List[ThsLimitListItem]] = None


# ==================== 读取 API ====================

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


# ==================== 写入 API ====================

@router.post("/collect")
async def collect_ths_data(data: ThsDataBatch):
    """采集同花顺数据（供数据采集脚本调用）"""
    service = get_data_service()
    result = {}
    
    if data.concepts:
        result['concepts'] = service.save_ths_concepts([c.dict() for c in data.concepts])
    
    if data.members:
        result['members'] = service.save_ths_members([m.dict() for m in data.members])
    
    if data.concept_daily:
        result['concept_daily'] = service.save_ths_concept_daily([d.dict() for d in data.concept_daily])
    
    if data.hot_rank:
        result['hot_rank'] = service.save_ths_hot_rank([h.dict() for h in data.hot_rank])
    
    if data.limit_list:
        result['limit_list'] = service.save_ths_limit_list([l.dict() for l in data.limit_list])
    
    return {"status": "ok", "saved": result}
