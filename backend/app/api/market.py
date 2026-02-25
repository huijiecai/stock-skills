from fastapi import APIRouter, HTTPException
from datetime import date, datetime
from app.services.data_service import get_data_service

router = APIRouter()


@router.get("/sentiment/{date}")
async def get_market_sentiment(date: str):
    """
    获取市场情绪数据
    
    Args:
        date: 日期（格式：YYYY-MM-DD）
    
    Returns:
        市场情绪数据（涨停/跌停家数、连板高度、市场阶段）
    """
    try:
        data_service = get_data_service()
        market_data = data_service.get_market_status(date)
        return {
            "success": True,
            "date": date,
            "data": market_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sentiment")
async def get_today_market_sentiment():
    """获取今日市场情绪"""
    today = datetime.now().strftime("%Y-%m-%d")
    return await get_market_sentiment(today)
