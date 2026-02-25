#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
聊天API路由
提供LLM聊天功能的API端点
"""

import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.models.requests import ChatRequest
from app.services.llm_chat_service import get_llm_chat_service

router = APIRouter()


@router.post("/analyze")
async def chat_analyze(request: ChatRequest):
    """
    LLM聊天分析端点，返回流式响应
    
    Args:
        request: 聊天请求（包含消息历史和可选日期）
    
    Returns:
        SSE流式响应
    """
    try:
        llm_service = get_llm_chat_service()
        
        # 转换消息格式
        messages = [{"role": msg.role, "content": msg.content} for msg in request.messages]
        
        async def event_stream():
            """生成SSE事件流"""
            try:
                async for chunk in llm_service.chat_stream(messages, request.date):
                    # 格式化为SSE格式
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                
                # 发送完成信号
                yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
                
            except Exception as e:
                # 发送错误信息
                error_data = {
                    "type": "error",
                    "content": f"处理失败: {str(e)}"
                }
                yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
        
        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # 禁用nginx缓冲
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器错误: {str(e)}")
