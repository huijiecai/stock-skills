# 龙头战法Web平台 - 后端

FastAPI后端服务，为龙头战法系统提供REST API。

## 功能

- 市场情绪数据API
- 个股信息查询API
- 股票池管理API
- 概念管理API
- 龙头战法分析API

## 安装

```bash
cd backend
pip install -r requirements.txt
```

## 运行

```bash
# 开发模式（热重载）
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API文档

启动服务后访问：
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API端点

### 市场数据
- `GET /api/market/sentiment/{date}` - 获取市场情绪
- `GET /api/market/sentiment` - 获取今日市场情绪

### 股票管理
- `GET /api/stocks` - 获取股票池
- `POST /api/stocks` - 添加股票
- `DELETE /api/stocks/{code}` - 删除股票
- `GET /api/stocks/{code}/detail` - 股票详情
- `GET /api/stocks/popularity/{date}` - 人气榜

### 概念管理
- `GET /api/concepts` - 获取概念树
- `GET /api/concepts/{name}/stocks` - 概念下的股票
- `POST /api/concepts/{name}/stocks` - 添加股票到概念
- `DELETE /api/concepts/{name}/stocks/{code}` - 移除股票
- `GET /api/concepts/heatmap/{date}` - 概念热力图
- `GET /api/concepts/{name}/analysis/{date}` - 概念分析

### 龙头分析
- `POST /api/analysis/stock` - 分析单只股票
- `POST /api/analysis/concept` - 分析概念
- `GET /api/analysis/leaders/{date}` - 获取龙头候选

## 项目结构

```
backend/
├── app/
│   ├── api/              # API路由
│   ├── services/         # 业务逻辑
│   ├── models/           # 数据模型
│   └── main.py           # 应用入口
├── requirements.txt      # 依赖
└── README.md
```

## 依赖说明

- **FastAPI**: 现代化的Web框架
- **Uvicorn**: ASGI服务器
- **Pydantic**: 数据验证

后端直接复用 `skills/dragon-stock-trading/scripts/` 中的Python模块，无需重复实现数据访问逻辑。
