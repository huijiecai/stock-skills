from fastapi import APIRouter, HTTPException
from datetime import datetime
from typing import List, Dict
from app.services.data_service import get_data_service
from app.models.requests import StockAdd, StockPoolAdd
from pydantic import BaseModel

router = APIRouter()


class StockInfoSync(BaseModel):
    """股票信息同步模型"""
    stock_code: str
    stock_name: str
    market: str
    board_type: str


class IntradayDataRequest(BaseModel):
    """分时数据请求模型"""
    date: str
    stock_code: str
    intraday_data: List[Dict]


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


@router.post("/sync-info")
async def sync_stock_info(stocks: List[StockInfoSync]):
    """批量同步股票信息到 stock_info 表"""
    try:
        data_service = get_data_service()
        
        # 转换为字典列表
        stocks_data = [
            {
                'stock_code': s.stock_code,
                'stock_name': s.stock_name,
                'market': s.market,
                'board_type': s.board_type
            }
            for s in stocks
        ]
        
        success_count, failed_count = data_service.batch_sync_stock_info(stocks_data)
        
        return {
            "success": True,
            "message": f"同步完成",
            "success_count": success_count,
            "failed_count": failed_count,
            "total": len(stocks)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/intraday")
async def save_intraday_data(data: IntradayDataRequest):
    """保存分时数据"""
    try:
        data_service = get_data_service()
        success = data_service.save_intraday_data(
            data.date,
            data.stock_code,
            data.intraday_data
        )
        
        if success:
            return {
                "success": True,
                "message": f"保存成功 {len(data.intraday_data)} 条数据"
            }
        else:
            raise HTTPException(status_code=500, detail="保存失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intraday/{stock_code}/{date}")
async def get_intraday_data(stock_code: str, date: str):
    """获取分时数据"""
    try:
        data_service = get_data_service()
        data = data_service.get_intraday_data(stock_code, date)
        return {
            "success": True,
            "data": data,
            "total": len(data)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/intraday-exists/{stock_code}/{date}")
async def check_intraday_exists(stock_code: str, date: str):
    """检查指定股票指定日期的分时数据是否存在"""
    try:
        data_service = get_data_service()
        exists = data_service.check_intraday_exists(stock_code, date)
        return {
            "success": True,
            "exists": exists
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{code}/quote")
async def get_stock_quote(code: str):
    """获取股票实时行情"""
    try:
        data_service = get_data_service()
        quote = data_service.get_stock_quote(code)
        
        if not quote:
            raise HTTPException(status_code=404, detail="未找到股票行情数据")
        
        return {
            "success": True,
            "data": quote
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{code}/daily")
async def get_stock_daily(code: str, start_date: str = None, end_date: str = None):
    """获取股票日K线数据"""
    try:
        data_service = get_data_service()
        
        # 如果没有指定日期范围，默认返回最近1年
        if not end_date:
            end_date = datetime.now().strftime("%Y-%m-%d")
        if not start_date:
            # 计算1年前的日期
            from datetime import timedelta
            one_year_ago = datetime.now() - timedelta(days=365)
            start_date = one_year_ago.strftime("%Y-%m-%d")
        
        daily_data = data_service.get_stock_daily(code, start_date, end_date)
        
        return {
            "success": True,
            "data": daily_data,
            "total": len(daily_data)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-quote")
async def batch_get_quote(request: Dict):
    """批量获取股票行情"""
    try:
        codes = request.get('codes', [])
        if not codes:
            raise HTTPException(status_code=400, detail="codes参数不能为空")
        
        data_service = get_data_service()
        quotes = data_service.batch_get_stock_quote(codes)
        
        return {
            "success": True,
            "data": quotes,
            "total": len(quotes)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
