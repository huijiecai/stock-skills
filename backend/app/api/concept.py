"""概念板块相关 API"""
from fastapi import APIRouter, Query
from typing import Optional

from app.services.concept_service import concept_service
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
    result = await concept_service.get_concept_list(page, page_size)
    return success_response(result)


@router.get("/daily/{code}")
async def get_concept_daily(
    code: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """获取概念板块日线"""
    result = await concept_service.get_concept_daily(code, start_date, end_date)
    return success_response(result)


@router.get("/intraday/{code}")
async def get_concept_intraday(
    code: str,
    date: Optional[str] = Query(None),
):
    """获取概念板块分时"""
    result = await concept_service.get_concept_intraday(code, date)
    return success_response(result)


@router.get("/components/{code}")
async def get_concept_components(code: str):
    """获取概念板块成分股"""
    result = await concept_service.get_concept_components(code)
    return success_response(result)


@router.get("/rank")
async def get_concept_rank(
    date: Optional[str] = Query(None),
    sort_by: str = Query("change_pct", description="排序字段"),
    order: str = Query("desc", description="排序方向"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取概念板块涨幅榜"""
    result = await concept_service.get_concept_rank(date, sort_by, order, page, page_size)
    return success_response(result)


@router.get("/search")
async def search_concept(keyword: str = Query(..., description="搜索关键词")):
    """搜索概念板块"""
    result = await concept_service.search_concept(keyword)
    return success_response(result)
