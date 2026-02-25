from fastapi import APIRouter, HTTPException
from datetime import date, datetime
from app.services.data_service import get_data_service
from app.models.requests import MarketCollectRequest

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


@router.post("/collect")
async def collect_market_data(request: MarketCollectRequest):
    """
    接收数据采集脚本提交的市场数据
    
    供 skills/scripts/market_fetcher.py 调用
    
    Args:
        request: 市场数据采集请求
    
    Returns:
        采集结果
    """
    try:
        data_service = get_data_service()
        
        # 保存市场概况
        market_success = data_service.save_market_sentiment(
            request.date,
            request.market_data
        )
        
        # 保存个股数据
        stock_success_count = 0
        for stock in request.stocks:
            if data_service.save_stock_daily(request.date, stock):
                stock_success_count += 1
        
        return {
            "success": True,
            "date": request.date,
            "market_saved": market_success,
            "stocks_count": len(request.stocks),
            "stocks_saved": stock_success_count
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据采集失败: {str(e)}")
