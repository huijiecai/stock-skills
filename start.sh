#!/bin/bash

# 龙头战法Web平台启动脚本 v2.0

echo "======================================"
echo "龙头战法 Web 平台 v2.0"
echo "======================================"
echo ""

# 检查Docker
if ! command -v docker &> /dev/null; then
    echo "❌ Docker未安装"
    exit 1
fi

# 检查Docker是否运行
if ! docker info &> /dev/null; then
    echo "❌ Docker未运行，请先启动Docker"
    exit 1
fi

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3未安装"
    exit 1
fi

# 检查Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js未安装"
    exit 1
fi

echo "✅ 环境检查通过"
echo ""

# 创建必要目录
mkdir -p logs
mkdir -p data/postgres

# 启动PostgreSQL容器
echo "🗄️  启动 PostgreSQL 数据库..."
if docker ps -a | grep -q stock_postgres; then
    if docker ps | grep -q stock_postgres; then
        echo "✅ PostgreSQL 已在运行"
    else
        docker start stock_postgres
        echo "✅ PostgreSQL 已启动"
    fi
else
    cd backend
    docker-compose up -d
    cd ..
    echo "✅ PostgreSQL 容器已创建并启动"
fi

# 等待数据库就绪
echo "⏳ 等待数据库就绪..."
sleep 5

# 检查数据库是否需要初始化
source .venv/bin/activate 2>/dev/null || true

# 检查后端依赖（使用根目录的 .venv）
if [ ! -d ".venv" ]; then
    echo "📦 首次运行，创建Python虚拟环境..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    echo "✅ 后端依赖安装完成"
    
    # 初始化数据库
    echo "📊 初始化数据库表结构..."
    cd backend
    python scripts/pg_init.py
    cd ..
    echo "✅ 数据库初始化完成"
else
    echo "✅ 后端环境已存在"
    source .venv/bin/activate
fi

# 检查前端依赖
if [ ! -d "frontend/node_modules" ]; then
    echo "📦 安装前端依赖..."
    cd frontend
    npm install
    cd ..
    echo "✅ 前端依赖安装完成"
else
    echo "✅ 前端依赖已存在"
fi

echo ""
echo "🚀 启动服务..."
echo ""

# 启动后端
echo "启动后端服务（端口8000）..."
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > ../logs/backend.log 2>&1 &
BACKEND_PID=$!
cd ..
echo "✅ 后端PID: $BACKEND_PID"

# 等待后端启动
sleep 3

# 检查后端是否启动成功
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ 后端服务启动成功"
else
    echo "⚠️  后端服务启动中，请稍后检查日志"
fi

# 启动前端
echo "启动前端服务（端口3000）..."
cd frontend
BROWSER=none npm start > ../logs/frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..
echo "✅ 前端PID: $FRONTEND_PID"

echo ""
echo "======================================"
echo "✅ 服务启动成功！"
echo "======================================"
echo ""
echo "📱 前端地址：http://localhost:3000"
echo "🔌 后端API：http://localhost:8000/docs"
echo ""
echo "日志文件："
echo "  - backend: logs/backend.log"
echo "  - frontend: logs/frontend.log"
echo ""
echo "停止服务："
echo "  ./stop.sh"
echo ""

# 保存PID
echo $BACKEND_PID > logs/backend.pid
echo $FRONTEND_PID > logs/frontend.pid
