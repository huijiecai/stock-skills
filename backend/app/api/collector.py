"""数据采集触发 API"""
from fastapi import APIRouter, BackgroundTasks, Query
from typing import Optional
from datetime import datetime

from app.services.data_collector import data_collector
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/collector", tags=["数据采集"])


def success_response(data=None, message: str = "success"):
    return {"code": 200, "message": message, "data": data}


@router.post("/trigger/daily")
async def trigger_daily_collection(
    background_tasks: BackgroundTasks,
    date: Optional[str] = Query(None, description="日期"),
):
    """触发日线数据采集"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    background_tasks.add_task(data_collector.collect_stock_daily_batch, date)
    background_tasks.add_task(data_collector.collect_index_daily_batch, date)
    
    return success_response(message=f"已触发 {date} 日线数据采集")


@router.post("/trigger/intraday")
async def trigger_intraday_collection(
    background_tasks: BackgroundTasks,
    date: Optional[str] = Query(None, description="日期"),
):
    """触发分时数据采集"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    background_tasks.add_task(data_collector.collect_stock_intraday_batch, date)
    background_tasks.add_task(data_collector.collect_index_intraday_batch, date)
    
    return success_response(message=f"已触发 {date} 分时数据采集")


@router.post("/trigger/concept")
async def trigger_concept_collection(background_tasks: BackgroundTasks):
    """触发概念板块数据采集"""
    background_tasks.add_task(data_collector.collect_concepts)
    return success_response(message="已触发概念板块数据采集")


@router.post("/trigger/limit-list")
async def trigger_limit_list_collection(
    background_tasks: BackgroundTasks,
    date: Optional[str] = Query(None, description="日期"),
):
    """触发涨跌停数据采集"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    background_tasks.add_task(data_collector.collect_limit_list, date)
    return success_response(message=f"已触发 {date} 涨跌停数据采集")


@router.post("/trigger/concept-mapping")
async def trigger_concept_mapping_update(background_tasks: BackgroundTasks):
    """触发概念成分股映射更新"""
    background_tasks.add_task(data_collector.update_concept_mapping)
    return success_response(message="已触发概念成分股映射更新")


@router.post("/trigger/all")
async def trigger_all_collection(
    background_tasks: BackgroundTasks,
    date: Optional[str] = Query(None, description="日期"),
):
    """触发全量数据采集"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    background_tasks.add_task(data_collector.collect_all_daily)
    background_tasks.add_task(data_collector.collect_all_intraday)
    background_tasks.add_task(data_collector.collect_limit_list, date)
    
    return success_response(message=f"已触发 {date} 全量数据采集")
