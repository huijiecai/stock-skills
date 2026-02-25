from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import List
import json
from pathlib import Path
from app.services.data_service import get_data_service
from app.models.requests import StockAdd

router = APIRouter()
project_root = Path(__file__).parent.parent.parent.parent
stock_list_file = project_root / "skills" / "dragon-stock-trading" / "data" / "stock_list.json"


@router.get("")
async def get_stocks():
    """获取股票池"""
    try:
        with open(stock_list_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return {
            "success": True,
            "total": len(data.get('stocks', [])),
            "stocks": data.get('stocks', [])
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def add_stock(stock: StockAdd):
    """添加股票到股票池"""
    try:
        with open(stock_list_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 检查是否已存在
        stocks = data.get('stocks', [])
        if any(s['code'] == stock.code for s in stocks):
            raise HTTPException(status_code=400, detail="股票已存在")
        
        # 添加股票
        stocks.append({
            "code": stock.code,
            "name": stock.name,
            "market": stock.market
        })
        
        # 保存
        with open(stock_list_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return {
            "success": True,
            "message": "添加成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{code}")
async def delete_stock(code: str):
    """从股票池删除股票"""
    try:
        with open(stock_list_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        stocks = data.get('stocks', [])
        original_length = len(stocks)
        stocks = [s for s in stocks if s['code'] != code]
        
        if len(stocks) == original_length:
            raise HTTPException(status_code=404, detail="股票不存在")
        
        data['stocks'] = stocks
        
        with open(stock_list_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return {
            "success": True,
            "message": "删除成功"
        }
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
