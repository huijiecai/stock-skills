#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LLM聊天服务
提供与LLM的交互功能，支持流式响应和Function Calling
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Optional, AsyncGenerator
from openai import AsyncOpenAI
from app.services.analysis_service import get_analysis_service
from app.services.data_service import get_data_service


def _load_skill_core() -> str:
    """
    加载 SKILL.md 的核心部分作为 System Prompt
    只加载前60行核心功能描述，不包含详细的使用方法和技术实现
    """
    skill_path = Path(__file__).parent.parent.parent.parent / "skills" / "dragon-stock-trading" / "SKILL.md"
    
    try:
        with open(skill_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # 读取到 "## 使用方法" 之前的内容（大约前60行）
            core_lines = []
            for line in lines:
                if line.strip().startswith("## 使用方法"):
                    break
                core_lines.append(line)
            
            skill_core = ''.join(core_lines)
            
            # 构建完整的 System Prompt
            system_prompt = f"""{skill_core}

---

**可用工具**：
你可以调用以下工具获取数据和查阅文档：

**数据查询工具**：
- analyze_stock: 分析单只股票是否符合龙头战法
- get_market_sentiment: 获取市场情绪数据（涨停/跌停家数、市场阶段）
- get_popularity_rank: 查看人气榜（成交额排名前N）
- get_concept_heatmap: 查看概念热度（涨停家数分布）
- get_concept_leaders: 获取概念龙头列表
- get_stock_detail: 获取个股详细信息（价格、量能）
- get_concept_stocks: 获取概念下的所有股票

**文档查阅工具**：
- read_reference: 查阅龙头战法参考文档（详细理论、数据API、案例等）
  可查阅的文档：
  * 龙头战法理论.md - 完整的理论框架、决策模型、情绪拐点三板斧
  * 数据查询API.md - 6类数据的详细查询方法和使用示例
  * 技术指标详解.md - 技术分析指标说明
  * 风险控制.md - 风险管理和止损策略
  * 系统架构.md - 系统架构和技术实现

**分析建议**：
1. 先获取市场整体情绪（判断是冰点修复还是增量主升）
2. 查询个股的人气排名和概念归属
3. 如需详细理论指导，使用 read_reference 查阅相关文档
4. 分析是否符合龙头标准（人气、逻辑、地位、确认信号）
5. 给出操作建议

请用清晰、结构化的方式展示分析过程，使用emoji增强可读性。
遇到复杂问题时，主动查阅 reference 文档获取详细指导。"""
            
            return system_prompt
    
    except Exception as e:
        # 如果加载失败，返回一个基础的 prompt
        return """你是龙头战法专家助手，帮助用户分析股票。

核心筛选标准：
1. 人气底线：成交额进入前30
2. 逻辑正宗：概念归属硬核
3. 地位突出：身位最高/领涨性强
4. 市场状态：冰点修复或增量主升
5. 确认信号：分时承接/板块联动

你可以调用工具获取数据，也可以使用 read_reference 查阅详细文档。"""


# 加载 System Prompt
SYSTEM_PROMPT = _load_skill_core()


class LLMChatService:
    """LLM聊天服务"""
    
    def __init__(self):
        self.analysis_service = get_analysis_service()
        self.data_service = get_data_service()
        
        # Reference 文档路径
        self.reference_dir = Path(__file__).parent.parent.parent.parent / "skills" / "dragon-stock-trading" / "reference"
        
        # 初始化OpenAI客户端
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = os.getenv("OPENAI_MODEL", "gpt-4")
        
        # 定义可调用的Function工具
        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_reference",
                    "description": "查阅龙头战法参考文档，获取详细的理论指导、数据查询方法、案例分析等",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "doc_name": {
                                "type": "string",
                                "enum": [
                                    "龙头战法理论.md",
                                    "数据查询API.md",
                                    "技术指标详解.md",
                                    "风险控制.md",
                                    "系统架构.md",
                                    "数据库设计.md",
                                    "概念配置指南.md"
                                ],
                                "description": "要查阅的文档名称"
                            }
                        },
                        "required": ["doc_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_stock",
                    "description": "分析单只股票是否符合龙头战法标准，返回详细的分析结果",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "股票代码，例如：002342"
                            },
                            "date": {
                                "type": "string",
                                "description": "分析日期，格式YYYY-MM-DD，默认今天"
                            }
                        },
                        "required": ["code"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_market_sentiment",
                    "description": "获取市场情绪数据，包括市场阶段、涨停家数、跌停家数、最高连板数",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "日期，格式YYYY-MM-DD，默认今天"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_popularity_rank",
                    "description": "获取人气榜（成交额排行），查看当日最活跃的股票",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "日期，格式YYYY-MM-DD"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "返回前N名，默认30",
                                "default": 30
                            }
                        },
                        "required": ["date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_concept_heatmap",
                    "description": "获取概念热力图，查看各概念的涨停家数和活跃度",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "日期，格式YYYY-MM-DD"
                            }
                        },
                        "required": ["date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_concept_leaders",
                    "description": "获取概念龙头列表，查看各概念的领涨股",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "date": {
                                "type": "string",
                                "description": "日期，格式YYYY-MM-DD"
                            }
                        },
                        "required": ["date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_stock_detail",
                    "description": "获取个股详细信息（价格、涨跌幅、成交额等）",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "股票代码"
                            },
                            "date": {
                                "type": "string",
                                "description": "日期，格式YYYY-MM-DD"
                            }
                        },
                        "required": ["code", "date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_concept_stocks",
                    "description": "获取指定概念下的所有股票列表",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "concept_name": {
                                "type": "string",
                                "description": "概念名称，例如：商业航天"
                            }
                        },
                        "required": ["concept_name"]
                    }
                }
            }
        ]
    
    def _execute_function(self, function_name: str, arguments: Dict) -> str:
        """执行Function Calling"""
        try:
            if function_name == "read_reference":
                doc_name = arguments.get("doc_name")
                doc_path = self.reference_dir / doc_name
                
                if not doc_path.exists():
                    return json.dumps({
                        "error": f"文档不存在: {doc_name}",
                        "available_docs": [
                            "龙头战法理论.md",
                            "数据查询API.md",
                            "技术指标详解.md",
                            "风险控制.md",
                            "系统架构.md",
                            "数据库设计.md",
                            "概念配置指南.md"
                        ]
                    }, ensure_ascii=False)
                
                with open(doc_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                return json.dumps({
                    "doc_name": doc_name,
                    "content": content
                }, ensure_ascii=False)
            
            elif function_name == "analyze_stock":
                result = self.analysis_service.analyze_stock(
                    arguments.get("code"),
                    arguments.get("date", "")
                )
                return json.dumps(result, ensure_ascii=False)
            
            elif function_name == "get_market_sentiment":
                date = arguments.get("date", "")
                result = self.data_service.get_market_status(date)
                return json.dumps(result, ensure_ascii=False)
            
            elif function_name == "get_popularity_rank":
                result = self.data_service.get_stock_popularity_rank(
                    arguments.get("date"),
                    arguments.get("limit", 30)
                )
                return json.dumps(result, ensure_ascii=False)
            
            elif function_name == "get_concept_heatmap":
                result = self.data_service.get_concept_leaders(
                    arguments.get("date"),
                    min_limit_up=0
                )
                return json.dumps(result, ensure_ascii=False)
            
            elif function_name == "get_concept_leaders":
                result = self.data_service.get_concept_leaders(
                    arguments.get("date"),
                    min_limit_up=1
                )
                return json.dumps(result, ensure_ascii=False)
            
            elif function_name == "get_stock_detail":
                result = self.data_service.get_stock_with_concept(
                    arguments.get("code"),
                    arguments.get("date")
                )
                return json.dumps(result, ensure_ascii=False)
            
            elif function_name == "get_concept_stocks":
                result = self.data_service.list_concept_stocks(
                    arguments.get("concept_name")
                )
                return json.dumps(result, ensure_ascii=False)
            
            else:
                return json.dumps({"error": f"Unknown function: {function_name}"})
                
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)
    
    async def chat_stream(
        self,
        messages: List[Dict],
        date: Optional[str] = None
    ) -> AsyncGenerator[Dict, None]:
        """
        流式聊天响应
        
        Args:
            messages: 消息历史列表 [{"role": "user", "content": "..."}]
            date: 可选的日期参数（用于所有查询）
        
        Yields:
            流式响应chunk
        """
        # 添加系统提示
        full_messages = [{"role": "system", "content": SYSTEM_PROMPT}] + messages
        
        # 如果提供了日期，在用户消息中添加上下文
        if date and messages:
            last_message = messages[-1]
            if last_message["role"] == "user":
                last_message["content"] = f"[分析日期: {date}]\n{last_message['content']}"
        
        try:
            # 调用OpenAI API
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=full_messages,
                tools=self.tools,
                tool_choice="auto",
                stream=True
            )
            
            # 处理流式响应
            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                
                if not delta:
                    continue
                
                # 处理工具调用
                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        if tool_call.function:
                            # 收集完整的function call
                            function_name = tool_call.function.name
                            function_args = tool_call.function.arguments
                            
                            if function_name and function_args:
                                try:
                                    args_dict = json.loads(function_args)
                                    # 执行函数调用
                                    result = self._execute_function(function_name, args_dict)
                                    
                                    # 将结果返回给LLM
                                    function_messages = full_messages + [
                                        {
                                            "role": "assistant",
                                            "content": None,
                                            "tool_calls": [{
                                                "id": tool_call.id,
                                                "type": "function",
                                                "function": {
                                                    "name": function_name,
                                                    "arguments": function_args
                                                }
                                            }]
                                        },
                                        {
                                            "role": "tool",
                                            "tool_call_id": tool_call.id,
                                            "content": result
                                        }
                                    ]
                                    
                                    # 继续对话
                                    followup_response = await self.client.chat.completions.create(
                                        model=self.model,
                                        messages=function_messages,
                                        stream=True
                                    )
                                    
                                    async for followup_chunk in followup_response:
                                        followup_delta = followup_chunk.choices[0].delta if followup_chunk.choices else None
                                        if followup_delta and followup_delta.content:
                                            yield {
                                                "type": "content",
                                                "content": followup_delta.content
                                            }
                                
                                except json.JSONDecodeError:
                                    # 参数还不完整，继续收集
                                    pass
                
                # 处理文本内容
                elif delta.content:
                    yield {
                        "type": "content",
                        "content": delta.content
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
