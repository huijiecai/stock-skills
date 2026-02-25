from fastapi import APIRouter, HTTPException
from datetime import datetime
from app.services.data_service import get_data_service
from app.models.requests import StockConceptAdd, ConceptUpdate, ConceptCreate

router = APIRouter()


@router.get("")
async def get_concepts():
    """获取概念树（从数据库读取）"""
    try:
        data_service = get_data_service()
        concepts = data_service.get_concept_hierarchy()
        return {
            "success": True,
            "data": concepts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_concept(request: ConceptCreate):
    """创建新概念（写入数据库）"""
    try:
        data_service = get_data_service()
        success = data_service.add_concept(
            request.name,
            request.parent,
            request.description
        )
        
        if success:
            return {
                "success": True,
                "message": "创建成功"
            }
        else:
            raise HTTPException(status_code=500, detail="创建失败")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{concept_name}/stocks")
async def get_concept_stocks(concept_name: str):
    """获取概念下的股票"""
    try:
        data_service = get_data_service()
        stocks = data_service.list_concept_stocks(concept_name)
        return {
            "success": True,
            "concept_name": concept_name,
            "total": len(stocks),
            "stocks": stocks
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{concept_name}/stocks")
async def add_stock_to_concept(concept_name: str, request: StockConceptAdd):
    """添加股票到概念"""
    try:
        data_service = get_data_service()
        
        # 构造note（格式：大类/细分）
        # 这里需要从概念名称推断层级路径
        # 简化处理：直接使用概念名称
        note = concept_name
        
        data_service.add_stock_to_concept(
            request.stock_code,
            concept_name,
            request.is_core,
            note
        )
        
        return {
            "success": True,
            "message": "添加成功"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{concept_name}/stocks/{stock_code}")
async def remove_stock_from_concept(concept_name: str, stock_code: str):
    """从概念中移除股票"""
    try:
        data_service = get_data_service()
        data_service.remove_stock_from_concept(stock_code, concept_name)
        return {
            "success": True,
            "message": "移除成功"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/heatmap/{date}")
async def get_concept_heatmap(date: str):
    """获取概念热力图数据"""
    try:
        data_service = get_data_service()
        leaders = data_service.get_concept_leaders(date, min_limit_up=0)
        return {
            "success": True,
            "date": date,
            "data": leaders
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{concept_name}/analysis/{date}")
async def get_concept_analysis(concept_name: str, date: str):
    """获取概念分析"""
    try:
        data_service = get_data_service()
        analysis = data_service.get_concept_analysis(concept_name, date)
        return {
            "success": True,
            "concept_name": concept_name,
            "date": date,
            "data": analysis
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
