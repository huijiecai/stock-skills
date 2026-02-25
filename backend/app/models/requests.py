from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import date


class StockAdd(BaseModel):
    """添加股票请求"""
    code: str = Field(..., description="股票代码")
    name: str = Field(..., description="股票名称")
    market: str = Field(..., description="市场（SZ/SH）")


class StockConceptAdd(BaseModel):
    """添加股票到概念请求"""
    stock_code: str = Field(..., description="股票代码")
    is_core: bool = Field(default=False, description="是否核心标的")
    note: str = Field(default="", description="备注")


class AnalysisRequest(BaseModel):
    """分析请求"""
    code: str = Field(..., description="股票代码")
    date: Optional[str] = Field(None, description="分析日期（默认今天）")


class ConceptAnalysisRequest(BaseModel):
    """概念分析请求"""
    concept_name: str = Field(..., description="概念名称")
    date: Optional[str] = Field(None, description="分析日期（默认今天）")


class ConceptUpdate(BaseModel):
    """更新概念请求"""
    description: str = Field(..., description="概念描述")
