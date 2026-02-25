# 龙头战法 Web 平台

基于"龙头战法"的股票分析系统，提供 Web 可视化界面和 LLM Skill 接口。

## 快速开始

### 1. 安装依赖

```bash
# 后端
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 前端
cd frontend
npm install
```

### 2. 初始化数据库

```bash
# 创建数据库表
python backend/scripts/db_init.py

# 迁移配置数据
python backend/scripts/migrate_json_to_db.py
```

### 3. 启动服务

```bash
# 使用启动脚本（推荐）
./start.sh

# 或手动启动
cd backend && uvicorn app.main:app --reload --port 8000  # 终端1
cd frontend && npm start  # 终端2
```

### 4. 配置环境变量（可选，用于 AI 聊天功能）

```bash
# 复制环境变量模板
cp backend/.env.example backend/.env

# 编辑 .env 文件，填写你的 OpenAI API Key
# OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxx
# OPENAI_MODEL=gpt-4
```

### 5. 访问

- **前端**: http://localhost:3000
- **AI 智能分析**: http://localhost:3000/chat ⭐ 新功能
- **后端 API**: http://localhost:8000/docs
- **健康检查**: http://localhost:8000/health

## 项目结构

```
stock/
├── backend/              # FastAPI 后端（端口 8000）
│   ├── app/
│   │   ├── api/         # API 端点
│   │   ├── services/    # 业务逻辑 + 数据访问
│   │   └── models/      # 数据模型
│   └── scripts/         # 数据库管理工具
│
├── frontend/            # React 前端（端口 3000）
│   └── src/
│       ├── pages/       # 页面组件
│       └── services/    # API 调用
│
├── skills/              # LLM Skill
│   └── dragon-stock-trading/
│       ├── SKILL.md                    # Skill 使用说明
│       ├── scripts/
│       │   ├── skill_api_client.py     # Skill API 客户端
│       │   └── collect_market_data_via_api.py  # 数据采集
│       └── reference/                   # 参考文档
│
├── data/                # 数据文件
│   ├── dragon_stock.db  # SQLite 数据库（主数据源）
│   ├── stock_list.json  # 股票池备份
│   └── concepts.json    # 概念配置备份
│
└── logs/                # 日志文件
```

## 核心功能

### Web 平台
- 📊 **市场概览**：涨停/跌停统计、连板高度、历史数据查询
- 📈 **股票池管理**：添加/删除关注股票
- 🏷️ **概念管理**：层级概念配置、股票关联
- 🎯 **龙头分析**：基于龙头战法的个股分析
- 🤖 **AI 智能分析**（⭐ 新功能）：
  - 自然语言对话分析股票（实时 SSE 流式响应）
  - 自动调用 7 个数据工具（市场情绪、人气榜、概念热度等）
  - 主动查阅龙头战法理论文档（`read_reference` 工具）
  - 配置要求：需填写 `backend/.env` 中的 `OPENAI_API_KEY`

### LLM Skill（Cursor IDE）
- 🤖 自然语言查询市场数据
- 📝 智能分析个股
- 🔍 概念龙头识别
- 📊 人气排行榜

## 架构原则

**API 优先 (API-First)**
- 后端是唯一数据访问层
- 所有客户端通过 HTTP API 访问数据
- 保证数据一致性

**单一数据源 (Single Source of Truth)**
- 所有数据存储在 SQLite 数据库
- JSON 文件仅作备份

**职责清晰**
- **Backend**: 数据管理 + 业务逻辑
- **Frontend**: UI 展示 + 用户交互
- **Skills**: LLM 分析 + 数据采集触发

详见：[ARCHITECTURE.md](ARCHITECTURE.md)

## 使用说明

### 数据采集

```bash
cd skills/dragon-stock-trading/scripts

# 采集今日数据
python collect_market_data_via_api.py

# 采集指定日期
python collect_market_data_via_api.py 2026-02-25
```

### Skill 使用

在 Cursor 中使用：
```python
from skill_api_client import SkillAPIClient

client = SkillAPIClient()
stocks = client.get_stock_list()      # 获取股票池
concepts = client.get_concepts()      # 获取概念树
analysis = client.analyze_stock('600000', '2026-02-25')  # 分析个股
```

详见：[skills/dragon-stock-trading/SKILL.md](skills/dragon-stock-trading/SKILL.md)

### API 使用

```bash
# 获取股票池
curl http://localhost:8000/api/stocks

# 获取概念层级
curl http://localhost:8000/api/concepts

# 添加股票
curl -X POST http://localhost:8000/api/stocks \
  -H "Content-Type: application/json" \
  -d '{"code":"600000","name":"浦发银行","market":"SH"}'
```

## 维护

### 停止服务
```bash
./stop.sh
```

### 数据库备份
```bash
cp data/dragon_stock.db data/dragon_stock_backup_$(date +%Y%m%d).db
```

### 数据库重置
```bash
rm data/dragon_stock.db
python backend/scripts/db_init.py
python backend/scripts/migrate_json_to_db.py
```

## 技术栈

**后端**:
- FastAPI - Web 框架
- SQLite - 数据库
- Pydantic - 数据验证

**前端**:
- React 18
- Ant Design 5
- Axios

**数据源**:
- iTick API - 实时行情

## 开发

### 添加 API 端点
```python
# backend/app/api/example.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/example")
async def get_example():
    return {"message": "Hello"}
```

### 添加前端页面
```jsx
// frontend/src/pages/ExamplePage.js
import React from 'react';

export default function ExamplePage() {
  return <div>Example Page</div>;
}
```

## 故障排查

**后端启动失败**
```bash
cd backend
source venv/bin/activate
pip install -r requirements.txt
```

**数据库损坏**
```bash
rm data/dragon_stock.db
python backend/scripts/db_init.py
python backend/scripts/migrate_json_to_db.py
```

**前端无法连接后端**
```bash
# 检查后端是否运行
curl http://localhost:8000/health
```

## 更多文档

- [ARCHITECTURE.md](ARCHITECTURE.md) - 详细架构说明
- [skills/dragon-stock-trading/SKILL.md](skills/dragon-stock-trading/SKILL.md) - Skill 使用文档
- [backend/README.md](backend/README.md) - 后端开发文档
- [frontend/README.md](frontend/README.md) - 前端开发文档

## 许可

MIT License
