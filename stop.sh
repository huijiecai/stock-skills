#!/bin/bash

# 龙头战法Web平台停止脚本

echo "停止服务..."

if [ -f "logs/backend.pid" ]; then
    BACKEND_PID=$(cat logs/backend.pid)
    kill $BACKEND_PID 2>/dev/null
    echo "✅ 后端服务已停止 (PID: $BACKEND_PID)"
    rm logs/backend.pid
else
    echo "⚠️  未找到后端PID文件"
fi

if [ -f "logs/frontend.pid" ]; then
    FRONTEND_PID=$(cat logs/frontend.pid)
    kill $FRONTEND_PID 2>/dev/null
    echo "✅ 前端服务已停止 (PID: $FRONTEND_PID)"
    rm logs/frontend.pid
else
    echo "⚠️  未找到前端PID文件"
fi

echo ""
echo "所有服务已停止"
