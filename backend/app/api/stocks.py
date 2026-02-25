from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import List
from app.services.data_service import get_data_service
from app.models.requests import StockAdd, StockPoolAdd

router = APIRouter()


@router.get("")
async def get_stocks():
    """获取股票池（从数据库读取）"""
    try:
        data_service = get_data_service()
        stocks = data_service.get_stock_pool(active_only=True)
        return {
            "success": True,
            "total": len(stocks),
            "stocks": stocks
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def add_stock(stock: StockPoolAdd):
    """添加股票到股票池（写入数据库）"""
    try:
        data_service = get_data_service()
        
        # 检查是否已存在
        existing_stocks = data_service.get_stock_pool(active_only=False)
        if any(s['code'] == stock.code for s in existing_stocks):
            raise HTTPException(status_code=400, detail="股票已存在")
        
        # 添加股票
        success = data_service.add_stock_to_pool(
            stock.code,
            stock.name,
            stock.market,
            stock.note
        )
        
        if success:
            return {
                "success": True,
                "message": "添加成功"
            }
        else:
            raise HTTPException(status_code=500, detail="添加失败")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{code}")
async def delete_stock(code: str):
    """从股票池删除股票（软删除）"""
    try:
        data_service = get_data_service()
        success = data_service.remove_stock_from_pool(code)
        
        if success:
            return {
                "success": True,
                "message": "删除成功"
            }
        else:
            raise HTTPException(status_code=404, detail="股票不存在")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{code}/detail")
async def get_stock_detail(code: str, date: str = None):
    """获取股票详情"""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    
    try:
        data_service = get_data_service()
        stock_data = data_service.get_stock_with_concept(code, date)
        return {
            "success": True,
            "data": stock_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/popularity/{date}")
async def get_popularity(date: str, limit: int = 30):
    """获取人气榜"""
    try:
        data_service = get_data_service()
        popularity_data = data_service.get_stock_popularity_rank(date, limit)
        return {
            "success": True,
            "date": date,
            "limit": limit,
            "data": popularity_data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
