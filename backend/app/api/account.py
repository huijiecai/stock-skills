"""账户管理 API"""
from fastapi import APIRouter, Query
from typing import Optional

from app.services.account_service import account_service
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/account", tags=["账户管理"])


def success_response(data=None, message: str = "success"):
    return {"code": 200, "message": message, "data": data}


def error_response(code: int, message: str):
    return {"code": code, "message": message, "data": None}


# ==================== 账户信息 ====================

@router.get("/info")
async def get_account_info():
    """获取账户信息"""
    result = await account_service.get_account_info()
    return success_response(result)


@router.put("/info")
async def update_account_info(
    account_name: Optional[str] = Query(None),
    initial_capital: Optional[float] = Query(None),
):
    """更新账户信息"""
    updated = await account_service.update_account_info(account_name, initial_capital)
    if not updated:
        return error_response(400, "没有要更新的内容")
    return success_response(message="账户信息更新成功")


# ==================== 持仓管理 ====================

@router.get("/positions")
async def get_positions():
    """获取持仓列表"""
    result = await account_service.get_positions()
    return success_response(result)


@router.post("/positions/update-price")
async def update_position_prices():
    """更新持仓价格"""
    await account_service.update_position_prices()
    return success_response(message="持仓价格更新成功")


# ==================== 交易记录 ====================

@router.get("/trades")
async def get_trade_records(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """获取交易记录"""
    result = await account_service.get_trade_records(start_date, end_date, page, page_size)
    return success_response(result)


@router.post("/trade")
async def execute_trade(
    stock_code: str = Query(..., description="股票代码"),
    action: str = Query(..., description="buy/sell"),
    price: float = Query(..., gt=0, description="价格"),
    quantity: int = Query(..., gt=0, description="数量"),
    reason: Optional[str] = Query(None, description="交易原因"),
):
    """执行交易"""
    try:
        result = await account_service.execute_trade(stock_code, action, price, quantity, reason)
        return success_response(result)
    except ValueError as e:
        return error_response(400, str(e))


# ==================== 每日快照 ====================

@router.get("/snapshots")
async def get_account_snapshots(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
):
    """获取账户每日快照"""
    result = await account_service.get_account_snapshots(start_date, end_date, limit)
    return success_response(result)


@router.post("/snapshot/create")
async def create_daily_snapshot():
    """创建当日快照"""
    try:
        message = await account_service.create_daily_snapshot()
        return success_response(message=message)
    except ValueError as e:
        return error_response(400, str(e))
