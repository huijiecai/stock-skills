#!/bin/bash

# 龙头战法Web平台启动脚本

echo "======================================"
echo "龙头战法Web平台"
echo "======================================"
echo ""

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

# 检查后端依赖
if [ ! -d "backend/venv" ]; then
    echo "📦 首次运行，创建Python虚拟环境..."
    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cd ..
    echo "✅ 后端依赖安装完成"
else
    echo "✅ 后端环境已存在"
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
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 > ../logs/backend.log 2>&1 &
BACKEND_PID=$!
cd ..
echo "✅ 后端PID: $BACKEND_PID"

# 等待后端启动
sleep 3

# 启动前端
echo "启动前端服务（端口3000）..."
cd frontend
npm start > ../logs/frontend.log 2>&1 &
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
echo "  kill $BACKEND_PID $FRONTEND_PID"
echo ""
echo "或使用："
echo "  ./stop.sh"
echo ""

# 保存PID
mkdir -p logs
echo $BACKEND_PID > logs/backend.pid
echo $FRONTEND_PID > logs/frontend.pid
