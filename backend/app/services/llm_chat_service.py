"""
LLM 聊天服务 - 基于 DeepAgents + AgentSkills 规范实现

正确的架构：
1. 使用 create_deep_agent 加载 SKILL.md
2. 使用 @tool 定义后端服务工具
3. Skills 自动按需加载（渐进式披露）
4. 阿里云通义千问 Qwen 作为底层模型
"""

import os
import json
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional
from datetime import datetime

from langchain_core.messages import HumanMessage, AIMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from deepagents import create_deep_agent

from app.services.query_service import QueryService

# 全局数据库路径
def get_db_path() -> str:
    """获取数据库路径"""
    # 从当前文件位置计算项目根目录
    current_file = Path(__file__).resolve()
    project_root = current_file.parent.parent.parent.parent
    db_path = project_root / "data" / "dragon_stock.db"
    return str(db_path)


# ==================== 工具定义 ====================

@tool
def get_stock_detail(stock_code: str, date: Optional[str] = None) -> str:
    """
    获取股票详细信息（价格、涨跌幅、成交量等）
    
    Args:
        stock_code: 股票代码（如 000001, 600000）
        date: 查询日期（YYYY-MM-DD），默认为最新交易日
    
    Returns:
        JSON格式的股票详细信息
    """
    try:
        query_service = QueryService(get_db_path())
        date = date or datetime.now().strftime("%Y-%m-%d")
        result = query_service.get_stock_detail(stock_code, date)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def get_market_sentiment(date: Optional[str] = None) -> str:
    """
    获取市场整体情绪（涨停数、跌停数、涨跌比等）
    
    Args:
        date: 查询日期（YYYY-MM-DD），默认为今天
    
    Returns:
        JSON格式的市场情绪数据
    """
    try:
        query_service = QueryService(get_db_path())
        date = date or datetime.now().strftime("%Y-%m-%d")
        result = query_service.get_market_sentiment(date)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def get_popularity_rank(date: Optional[str] = None, limit: int = 10) -> str:
    """
    获取人气股票排行（按成交额排序）
    
    Args:
        date: 查询日期（YYYY-MM-DD），默认为今天
        limit: 返回数量，默认10
    
    Returns:
        JSON格式的人气股票列表
    """
    try:
        query_service = QueryService(get_db_path())
        date = date or datetime.now().strftime("%Y-%m-%d")
        result = query_service.get_popularity_rank(date, limit)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def get_concept_heatmap(date: Optional[str] = None, limit: int = 10) -> str:
    """
    获取概念板块热度排行
    
    Args:
        date: 查询日期（YYYY-MM-DD），默认为今天
        limit: 返回数量，默认10
    
    Returns:
        JSON格式的概念热度数据
    """
    try:
        query_service = QueryService(get_db_path())
        date = date or datetime.now().strftime("%Y-%m-%d")
        result = query_service.get_concept_heatmap(date, limit)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def get_concept_leaders(concept_id: str, date: Optional[str] = None, limit: int = 5) -> str:
    """
    获取概念板块内的龙头股票
    
    Args:
        concept_id: 概念ID（概念名称）
        date: 查询日期（YYYY-MM-DD），默认为今天
        limit: 返回数量，默认5
    
    Returns:
        JSON格式的龙头股票列表
    """
    try:
        query_service = QueryService(get_db_path())
        date = date or datetime.now().strftime("%Y-%m-%d")
        result = query_service.get_concept_leaders_by_id(concept_id, date, limit)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def get_concept_stocks(concept_id: str) -> str:
    """
    获取概念板块包含的所有股票
    
    Args:
        concept_id: 概念ID
    
    Returns:
        JSON格式的股票列表
    """
    try:
        query_service = QueryService(get_db_path())
        result = query_service.get_concept_stocks(concept_id)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def analyze_stock(stock_code: str, date: Optional[str] = None) -> str:
    """
    综合分析个股（价格、成交量、所属概念、概念热度等）
    
    Args:
        stock_code: 股票代码
        date: 查询日期（YYYY-MM-DD），默认为今天
    
    Returns:
        JSON格式的综合分析结果
    """
    try:
        query_service = QueryService(get_db_path())
        date = date or datetime.now().strftime("%Y-%m-%d")
        result = query_service.analyze_stock(stock_code, date)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ==================== LLM 服务 ====================

class LLMChatService:
    """
    DeepAgents 版 LLM 聊天服务
    
    使用 create_deep_agent 自动加载 Skills：
    - Skills 路径：skills/dragon-stock-trading/
    - 自动读取 SKILL.md
    - 按需加载 reference 文档
    - 自带文件系统工具
    """
    
    def __init__(self):
        # 阿里云通义千问 API配置（使用OpenAI兼容模式）
        api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("DASHSCOPE_API_KEY or OPENAI_API_KEY environment variable not set")
        
        model_name = os.getenv("QWEN_MODEL", "qwen-max")
        
        # 初始化通义千问模型（通过OpenAI兼容接口）
        self.llm = ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            streaming=True,
            temperature=0.7
        )
        
        # 定义后端服务工具
        self.tools = [
            get_stock_detail,
            get_market_sentiment,
            get_popularity_rank,
            get_concept_heatmap,
            get_concept_leaders,
            get_concept_stocks,
            analyze_stock
        ]
        
        # Skills 路径
        skills_dir = Path(__file__).parent.parent.parent.parent / "skills" / "dragon-stock-trading"
        
        # 创建 Deep Agent（自动加载 Skills）
        self.agent = create_deep_agent(
            model=self.llm,
            tools=self.tools,
            skills=[str(skills_dir)],  # 传入 skills 目录
            system_prompt=None  # 让 Deep Agent 自动从 SKILL.md 读取
        )
    
    async def chat_stream(
        self,
        messages: List[Dict],
        date: Optional[str] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        流式聊天响应（使用 Deep Agent）
        
        Args:
            messages: 消息历史列表
            date: 可选的日期参数
        
        Yields:
            流式响应chunk
        """
        try:
            # 构建消息列表（Deep Agent 格式）
            agent_messages = []
            
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content", "")
                
                if role == "user":
                    # 如果提供了日期，添加到用户消息
                    if date:
                        content = f"[分析日期: {date}]\n{content}"
                    agent_messages.append({"role": "user", "content": content})
                elif role == "assistant":
                    agent_messages.append({"role": "assistant", "content": content})
            
            # 使用 invoke 获取完整结果
            result = await self.agent.ainvoke({"messages": agent_messages})
            
            # 提取最终消息并一次性输出（不分块）
            if "messages" in result and result["messages"]:
                last_message = result["messages"][-1]
                if hasattr(last_message, "content") and last_message.content:
                    yield {
                        "type": "content",
                        "content": last_message.content
                    }
        
        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            yield {
                "type": "error",
                "content": f"❌ 发生错误: {str(e)}\n{error_detail}"
            }


# 单例
_llm_chat_service: Optional[LLMChatService] = None


def get_llm_chat_service() -> LLMChatService:
    """获取LLM聊天服务单例"""
    global _llm_chat_service
    if _llm_chat_service is None:
        _llm_chat_service = LLMChatService()
    return _llm_chat_service
