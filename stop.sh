#!/bin/bash

# 龙头战法Web平台停止脚本 v2.0

echo "======================================"
echo "停止服务..."
echo "======================================"
echo ""

# 停止后端服务
if [ -f "logs/backend.pid" ]; then
    BACKEND_PID=$(cat logs/backend.pid)
    if kill -0 $BACKEND_PID 2>/dev/null; then
        kill $BACKEND_PID 2>/dev/null
        echo "✅ 后端服务已停止 (PID: $BACKEND_PID)"
    else
        echo "⚠️  后端进程已不存在 (PID: $BACKEND_PID)"
    fi
    rm logs/backend.pid
else
    # 尝试查找并杀死uvicorn进程
    if pgrep -f "uvicorn app.main:app" > /dev/null; then
        pkill -f "uvicorn app.main:app"
        echo "✅ 已终止后端进程"
    else
        echo "⚠️  未找到后端PID文件"
    fi
fi

# 停止前端服务
if [ -f "logs/frontend.pid" ]; then
    FRONTEND_PID=$(cat logs/frontend.pid)
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        kill $FRONTEND_PID 2>/dev/null
        echo "✅ 前端服务已停止 (PID: $FRONTEND_PID)"
    else
        echo "⚠️  前端进程已不存在 (PID: $FRONTEND_PID)"
    fi
    rm logs/frontend.pid
else
    # 尝试查找并杀死react-scripts进程
    if pgrep -f "react-scripts" > /dev/null; then
        pkill -f "react-scripts"
        echo "✅ 已终止前端进程"
    else
        echo "⚠️  未找到前端PID文件"
    fi
fi

echo ""

# 询问是否停止数据库
echo "是否停止 PostgreSQL 数据库容器？ (y/N)"
read -t 5 -n 1 answer
if [[ $answer == "y" || $answer == "Y" ]]; then
    docker stop stock_postgres 2>/dev/null
    echo "✅ PostgreSQL 容器已停止"
else
    echo "⏭️  PostgreSQL 容器保持运行"
fi

echo ""
echo "======================================"
echo "所有服务已停止"
echo "======================================"
