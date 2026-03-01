from fastapi import APIRouter, HTTPException
from datetime import date, datetime
from app.services.data_service import get_data_service
from app.models.requests import MarketCollectRequest

router = APIRouter()


@router.get("/latest-trading-date")
async def get_latest_trading_date():
    """
    获取最近交易日
    
    Returns:
        最近交易日期（格式：YYYY-MM-DD）
    """
    try:
        data_service = get_data_service()
        latest_date = data_service.get_latest_trading_date()
        return {
            "success": True,
            "date": latest_date
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/collect")
async def collect_market_data(request: MarketCollectRequest):
    """
    接收市场情绪数据（仅市场概况，不包含个股）
    
    供 collect_market_data.py 调用
    
    Args:
        request: 市场数据采集请求
    
    Returns:
        采集结果
    """
    try:
        data_service = get_data_service()
        
        # 只保存市场概况（个股数据通过 /stocks/daily 接口逐个保存）
        market_success = data_service.save_market_sentiment(
            request.date,
            request.market_data
        )
        
        return {
            "success": True,
            "date": request.date,
            "market_saved": market_success
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"市场数据保存失败: {str(e)}")
