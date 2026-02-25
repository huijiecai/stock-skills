from fastapi import APIRouter, HTTPException
from datetime import datetime
from app.services.analysis_service import get_analysis_service
from app.models.requests import AnalysisRequest, ConceptAnalysisRequest

router = APIRouter()


@router.post("/stock")
async def analyze_stock(request: AnalysisRequest):
    """
    分析单只股票是否符合龙头战法
    
    Args:
        request: 分析请求（股票代码和日期）
    
    Returns:
        分析结果
    """
    date = request.date or datetime.now().strftime("%Y-%m-%d")
    
    try:
        analysis_service = get_analysis_service()
        result = analysis_service.analyze_stock(request.code, date)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/concept")
async def analyze_concept(request: ConceptAnalysisRequest):
    """
    分析概念内所有股票
    
    Args:
        request: 概念分析请求
    
    Returns:
        概念分析结果
    """
    date = request.date or datetime.now().strftime("%Y-%m-%d")
    
    try:
        analysis_service = get_analysis_service()
        result = analysis_service.analyze_concept(request.concept_name, date)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaders/{date}")
async def get_leaders(date: str):
    """
    获取当日龙头候选
    
    Args:
        date: 日期（格式：YYYY-MM-DD）
    
    Returns:
        龙头候选列表
    """
    try:
        analysis_service = get_analysis_service()
        data_service = analysis_service.data_service
        
        # 获取概念龙头
        concept_leaders = data_service.get_concept_leaders(date, min_limit_up=1)
        
        # 获取人气前10
        popularity = data_service.get_stock_popularity_rank(date, 10)
        
        return {
            "success": True,
            "date": date,
            "concept_leaders": concept_leaders,
            "popularity_leaders": popularity
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
