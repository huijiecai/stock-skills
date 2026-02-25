"""
LLM 聊天服务 - 基于 LangChain + AgentSkills 规范实现

架构说明：
1. 从 SKILL.md 读取技能定义（单一数据源）
2. 使用 @tool 装饰器定义后端工具
3. ChatZhipuAI + Agent 执行
4. 流式输出（修复重复问题）
"""

import os
import json
from pathlib import Path
from typing import AsyncGenerator, Dict, List, Optional
from datetime import datetime

from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.tools import tool
from langchain_community.chat_models import ChatZhipuAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import AgentExecutor, create_tool_calling_agent

from app.services.query_service import QueryService


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
        query_service = QueryService()
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
        query_service = QueryService()
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
        query_service = QueryService()
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
        query_service = QueryService()
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
        concept_id: 概念ID
        date: 查询日期（YYYY-MM-DD），默认为今天
        limit: 返回数量，默认5
    
    Returns:
        JSON格式的龙头股票列表
    """
    try:
        query_service = QueryService()
        date = date or datetime.now().strftime("%Y-%m-%d")
        result = query_service.get_concept_leaders(concept_id, date, limit)
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
        query_service = QueryService()
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
        query_service = QueryService()
        date = date or datetime.now().strftime("%Y-%m-%d")
        result = query_service.analyze_stock(stock_code, date)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


@tool
def read_reference(doc_name: str) -> str:
    """
    查阅龙头战法参考文档，获取详细的理论指导、数据查询方法、案例分析等
    
    可用文档：
    - 龙头战法理论.md: 核心理论和选股逻辑
    - 数据查询API.md: 所有可用的查询接口说明
    - 技术指标详解.md: 技术指标计算和应用
    - 风险控制.md: 风险管理和止损策略
    - 系统架构.md: 整体系统设计
    - 数据库设计.md: 数据表结构说明
    - 概念配置指南.md: 概念分类配置方法
    
    Args:
        doc_name: 文档名称
    
    Returns:
        文档内容（Markdown格式）
    """
    try:
        reference_dir = Path(__file__).parent.parent.parent.parent / "skills" / "dragon-stock-trading" / "reference"
        doc_path = reference_dir / doc_name
        
        if not doc_path.exists():
            return json.dumps({"error": f"文档不存在: {doc_name}"}, ensure_ascii=False)
        
        content = doc_path.read_text(encoding="utf-8")
        return json.dumps({"doc_name": doc_name, "content": content}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ==================== Skill 加载 ====================

def _load_skill() -> str:
    """
    加载 SKILL.md 并构建系统提示
    
    遵循 AgentSkills 规范：
    1. 从 SKILL.md 读取核心描述（前60行）
    2. 工具定义在代码中（上面的 @tool）
    3. 详细文档通过 read_reference 工具按需加载
    
    Returns:
        完整的系统提示
    """
    skill_path = Path(__file__).parent.parent.parent.parent / "skills" / "dragon-stock-trading" / "SKILL.md"
    
    if not skill_path.exists():
        return "你是龙头战法智能分析助手。"
    
    # 读取 SKILL.md 核心部分
    content = skill_path.read_text(encoding="utf-8")
    lines = content.split("\n")
    
    # 只取到 "## 使用方法" 之前的部分
    core_lines = []
    for line in lines:
        if line.startswith("## 使用方法"):
            break
        core_lines.append(line)
    
    skill_core = "\n".join(core_lines[:60])  # 限制在60行内
    
    # 构建完整的系统提示
    system_prompt = f"""{skill_core}

## 可用工具

你可以调用以下工具获取数据：

1. **get_stock_detail** - 获取个股详细信息（价格、涨跌幅、成交量）
2. **get_market_sentiment** - 获取市场整体情绪（涨停数、跌停数）
3. **get_popularity_rank** - 获取人气股票排行（按成交额）
4. **get_concept_heatmap** - 获取概念板块热度排行
5. **get_concept_leaders** - 获取概念龙头股
6. **get_concept_stocks** - 获取概念成分股
7. **analyze_stock** - 综合分析个股
8. **read_reference** - 查阅详细的参考文档

## 分析流程

1. **了解需求** - 明确用户想分析什么
2. **获取数据** - 调用工具获取相关数据
3. **深入分析** - 基于龙头战法理论分析数据
4. **给出结论** - 提供明确的投资建议

如需详细理论，使用 `read_reference` 工具查阅文档。
"""
    
    return system_prompt


SYSTEM_PROMPT = _load_skill()


# ==================== LLM 服务 ====================

class LLMChatService:
    """
    LangChain 版 LLM 聊天服务（修复流式重复问题）
    """
    
    def __init__(self):
        # 智谱AI API配置
        api_key = os.getenv("ZHIPUAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("ZHIPUAI_API_KEY or OPENAI_API_KEY environment variable not set")
        
        model = os.getenv("ZHIPUAI_MODEL", "glm-4-plus")
        
        # 初始化智谱AI模型
        self.llm = ChatZhipuAI(
            model=model,
            api_key=api_key,
            streaming=True,
            temperature=0.7
        )
        
        # 定义所有工具
        self.tools = [
            get_stock_detail,
            get_market_sentiment,
            get_popularity_rank,
            get_concept_heatmap,
            get_concept_leaders,
            get_concept_stocks,
            analyze_stock,
            read_reference
        ]
        
        # 创建提示模板
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            MessagesPlaceholder("chat_history", optional=True),
            ("human", "{input}"),
            MessagesPlaceholder("agent_scratchpad"),
        ])
        
        # 创建 Agent
        self.agent = create_tool_calling_agent(self.llm, self.tools, self.prompt)
        self.agent_executor = AgentExecutor(
            agent=self.agent,
            tools=self.tools,
            verbose=False,
            handle_parsing_errors=True
        )
    
    async def chat_stream(
        self,
        messages: List[Dict],
        date: Optional[str] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        流式聊天响应（修复重复问题）
        
        解决方案：
        1. 升级到最新 LangChain（bug已修复）
        2. 使用 astream 而不是 astream_events（更简单）
        3. 只输出最终结果的流式内容
        
        Args:
            messages: 消息历史列表
            date: 可选的日期参数
        
        Yields:
            流式响应chunk
        """
        try:
            # 转换消息格式
            chat_history = []
            user_input = ""
            
            for msg in messages:
                role = msg.get("role")
                content = msg.get("content", "")
                
                if role == "user":
                    user_input = content
                elif role == "assistant":
                    chat_history.append(AIMessage(content=content))
            
            # 如果提供了日期，添加到用户输入
            if date and user_input:
                user_input = f"[分析日期: {date}]\n{user_input}"
            
            # 使用 astream 流式执行
            async for chunk in self.agent_executor.astream({
                "input": user_input,
                "chat_history": chat_history
            }):
                # 只输出最终的 output
                if "output" in chunk:
                    output = chunk["output"]
                    # 分块输出（模拟流式效果）
                    chunk_size = 10
                    for i in range(0, len(output), chunk_size):
                        yield {
                            "type": "content",
                            "content": output[i:i+chunk_size]
                        }
        
        except Exception as e:
            yield {
                "type": "error",
                "content": f"❌ 发生错误: {str(e)}"
            }


# 单例
_llm_chat_service: Optional[LLMChatService] = None


def get_llm_chat_service() -> LLMChatService:
    """获取LLM聊天服务单例"""
    global _llm_chat_service
    if _llm_chat_service is None:
        _llm_chat_service = LLMChatService()
    return _llm_chat_service
