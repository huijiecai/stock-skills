"""模拟看盘 API"""
from fastapi import APIRouter, Query
from typing import Optional

from app.services.simulation_service import simulation_service
from app.models.requests import MarketSnapshotRequest, WatchlistSnapshotRequest, TimelineRequest
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/simulation", tags=["模拟看盘"])


def success_response(data=None, message: str = "success"):
    return {"code": 200, "message": message, "data": data}


@router.get("/market-overview")
async def get_market_overview(
    date: Optional[str] = Query(None, description="日期"),
):
    """
    模拟看盘 - 市场概览
    
    返回当日市场情绪、主要指数、热门板块
    """
    result = await simulation_service.get_market_overview(date)
    return success_response(result)


@router.get("/ladder-detail")
async def get_ladder_detail(
    date: Optional[str] = Query(None, description="日期"),
):
    """
    模拟看盘 - 连板天梯详情
    
    返回各连板级别的详细信息
    """
    result = await simulation_service.get_ladder_detail(date)
    return success_response(result)


@router.get("/hot-stocks")
async def get_hot_stocks(
    date: Optional[str] = Query(None, description="日期"),
    limit: int = Query(20, ge=1, le=50),
):
    """
    模拟看盘 - 热门个股
    
    返回当日成交额最大的个股
    """
    result = await simulation_service.get_hot_stocks(date, limit)
    return success_response(result)


@router.get("/capital-flow-rank")
async def get_capital_flow_rank(
    date: Optional[str] = Query(None, description="日期"),
    direction: str = Query("in", description="in流入/out流出"),
    limit: int = Query(20, ge=1, le=50),
):
    """
    模拟看盘 - 资金流向排行
    
    返回主力资金流入/流出排行
    """
    result = await simulation_service.get_capital_flow_rank(date, direction, limit)
    return success_response(result)


@router.get("/board-watch")
async def get_board_watch(
    date: Optional[str] = Query(None, description="日期"),
):
    """
    模拟看盘 - 涨停监控
    
    返回今日涨停股监控列表（含炸板情况）
    """
    result = await simulation_service.get_board_watch(date)
    return success_response(result)


# ==================== 时间点快照 API ====================

@router.post("/market-snapshot")
async def get_market_snapshot_by_time(request: MarketSnapshotRequest):
    """
    全市场时间点快照
    
    获取指定时间点的市场全景：指数、市场情绪、涨幅榜、热门板块、涨停列表
    用于模拟看盘按分钟推进
    
    请求示例：
    {
        "time": "10:17",
        "date": "2026-03-27",
        "top_n": 10
    }
    """
    result = await simulation_service.get_market_snapshot_by_time(
        request.time, 
        request.date, 
        request.top_n
    )
    return success_response(result)


@router.post("/watchlist-snapshot")
async def get_watchlist_snapshot(request: WatchlistSnapshotRequest):
    """
    盯盘股时间点快照
    
    获取指定时间点盯盘股的分时数据
    用于模拟看盘监控重点股票
    
    请求示例：
    {
        "time": "10:17",
        "date": "2026-03-27",
        "codes": ["002192", "000722", "600726"]
    }
    """
    result = await simulation_service.get_watchlist_snapshot(
        request.time, 
        request.date, 
        request.codes
    )
    return success_response(result)


@router.post("/timeline")
async def get_timeline_snapshots(request: TimelineRequest):
    """
    时间线快照序列
    
    批量获取多个时间点的盯盘股快照
    用于快速回放某段时间内的股票走势
    
    请求示例：
    {
        "date": "2026-03-27",
        "times": ["09:30", "09:35", "10:00", "10:30", "11:30", "14:00", "15:00"],
        "codes": ["002192", "000722", "600726"]
    }
    """
    result = await simulation_service.get_timeline_snapshots(
        request.date,
        request.times,
        request.codes
    )
    return success_response(result)
