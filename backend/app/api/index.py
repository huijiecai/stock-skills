"""指数相关 API"""
from fastapi import APIRouter, Query
from typing import Optional

from app.services.index_service import index_service
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/index", tags=["指数"])


def success_response(data=None, message: str = "success"):
    return {"code": 200, "message": message, "data": data}


@router.get("/list")
async def get_index_list():
    """获取指数列表"""
    result = await index_service.get_index_list()
    return success_response(result)


@router.get("/daily/{code}")
async def get_index_daily(
    code: str,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """获取指数日线"""
    result = await index_service.get_index_daily(code, start_date, end_date)
    return success_response(result)


@router.get("/intraday/{code}")
async def get_index_intraday(
    code: str,
    date: Optional[str] = Query(None),
):
    """获取指数分时"""
    result = await index_service.get_index_intraday(code, date)
    return success_response(result)
