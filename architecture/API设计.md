# API 设计

## API 概览

| 模块 | 数量 | 主要用途 |
|------|------|---------|
| 股票 API | 7 | 个股信息、日线、分时、资金流向 |
| 指数 API | 3 | 指数列表、日线、分时 |
| 概念 API | 6 | 概念列表、详情、日线、分时、成分股、排行 |
| 市场 API | 6 | 涨跌停、连板、概览、方向分布、统计 |
| 采集 API | 6 | 手动触发采集、任务状态 |
| 模拟看盘 API | 5 | 全市场快照、盯盘股快照、时间线、详情页 |
| 账户 API | 5 | 状态、持仓、交易记录、快照 |
| **总计** | **37** | |

---

## 目录结构

```
backend/app/api/
├── __init__.py
├── stock.py      # 股票相关 API
├── index.py      # 指数相关 API
├── concept.py    # 概念板块 API
├── market.py     # 市场数据 API
├── collector.py  # 数据采集触发 API
├── simulation.py # 模拟看盘专用 API
└── account.py    # 账户管理 API
```

---

## 股票 API (`/api/stock`)

| 方法 | 路径 | 功能 | 参数 |
|------|------|------|------|
| GET | `/api/stock/info/{code}` | 股票基本信息 | code: 股票代码 |
| GET | `/api/stock/daily/{code}` | 股票日线行情 | code, start_date, end_date |
| GET | `/api/stock/intraday/{code}` | 股票分时数据 | code, date |
| GET | `/api/stock/realtime` | 实时行情（批量） | codes: 股票代码列表 |
| GET | `/api/stock/capital-flow/{code}` | 资金流向 | code, date |
| GET | `/api/stock/concepts/{code}` | 股票所属概念 | code |
| GET | `/api/stock/search` | 股票搜索 | keyword: 关键词 |

---

## 指数 API (`/api/index`)

| 方法 | 路径 | 功能 | 参数 |
|------|------|------|------|
| GET | `/api/index/list` | 指数列表 | - |
| GET | `/api/index/daily/{code}` | 指数日线 | code, start_date, end_date |
| GET | `/api/index/intraday/{code}` | 指数分时 | code, date |

---

## 概念板块 API (`/api/concept`)

| 方法 | 路径 | 功能 | 参数 |
|------|------|------|------|
| GET | `/api/concept/list` | 概念列表 | source: east/ths |
| GET | `/api/concept/info/{code}` | 概念详情 | code: 概念代码 |
| GET | `/api/concept/daily/{code}` | 概念日线 | code, start_date, end_date |
| GET | `/api/concept/intraday/{code}` | 概念分时 | code, date |
| GET | `/api/concept/constituents/{code}` | 概念成分股 | code |
| GET | `/api/concept/ranking` | 概念涨幅排行 | date, top_n |

---

## 市场数据 API (`/api/market`)

| 方法 | 路径 | 功能 | 参数 |
|------|------|------|------|
| GET | `/api/market/limit-up` | 涨停股列表 | date |
| GET | `/api/market/limit-down` | 跌停股列表 | date |
| GET | `/api/market/limit-times/{times}` | 连板股查询 | times: 连板数, date |
| GET | `/api/market/overview` | 市场概览 | date |
| GET | `/api/market/limit-up-distribution` | 涨停方向分布 | date |
| GET | `/api/market/statistics` | 市场统计（涨跌家数、封板率） | date |

### 市场统计接口详细说明

**接口**：`GET /api/market/statistics`

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "date": "2026-03-27",
    "up_count": 4300,
    "down_count": 800,
    "flat_count": 200,
    "limit_up_count": 78,
    "limit_down_count": 2,
    "broken_board_count": 5,
    "seal_rate": 93.9,
    "total_amount": 210000000000
  }
}
```

> **封板率计算**：`seal_rate = limit_up_count / (limit_up_count + broken_board_count) * 100`

---

## 数据采集触发 API (`/api/collector`)

| 方法 | 路径 | 功能 | 参数 |
|------|------|------|------|
| POST | `/api/collector/stock/daily` | 触发股票日线采集 | code, start_date, end_date |
| POST | `/api/collector/stock/intraday` | 触发股票分时采集 | code, date |
| POST | `/api/collector/index/daily` | 触发指数日线采集 | code, start_date, end_date |
| POST | `/api/collector/concept/all` | 触发概念数据采集 | date |
| POST | `/api/collector/market/limit` | 触发涨跌停采集 | date |
| GET | `/api/collector/status` | 采集任务状态 | task_id |

---

## 模拟看盘专用 API (`/api/simulation`)

| 方法 | 路径 | 功能 | 说明 |
|------|------|------|------|
| GET | `/api/simulation/market-snapshot` | **全市场时间点快照** | 板块排行+个股排行+市场情绪+涨停列表 |
| GET | `/api/simulation/watchlist-snapshot` | **盯盘股时间点快照** | 指定时间点的盯盘股状态 |
| GET | `/api/simulation/timeline` | **时间线快照序列** | 批量获取多个时间点的完整数据 |
| GET | `/api/simulation/stock-detail/{code}` | 个股详情页 | 基本信息+分时+资金流向+所属概念 |
| GET | `/api/simulation/concept-detail/{code}` | 概念详情页 | 基本信息+分时+成分股 |

### 全市场快照接口详细说明

**接口**：`GET /api/simulation/market-snapshot`

| 参数 | 说明 | 示例 |
|------|------|------|
| time | 时间点（HH:MM） | 10:17 |
| date | 日期 | 2026-03-27 |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "time": "10:17",
    "date": "2026-03-27",
    
    "index": {
      "000001": { "name": "上证指数", "price": 3892, "change_pct": 0.73 },
      "399001": { "name": "深证成指", "price": 13610, "change_pct": 0.45 },
      "399006": { "name": "创业板指", "price": 2188, "change_pct": 0.32 }
    },
    
    "market_sentiment": {
      "up_count": 2800,
      "down_count": 2100,
      "limit_up_count": 45,
      "limit_down_count": 3,
      "seal_rate": 88.2
    },
    
    "top_gainers": [
      { "code": "002192", "name": "融捷股份", "change_pct": 7.25, "concept": "锂电池" },
      { "code": "002361", "name": "神剑股份", "change_pct": 10.00, "concept": "商业航天" }
    ],
    
    "top_concepts": [
      { "code": "BK0612", "name": "锂电池", "change_pct": 3.5, "limit_up_count": 3 },
      { "code": "BK0888", "name": "商业航天", "change_pct": 2.8, "limit_up_count": 2 }
    ],
    
    "limit_up_list": [
      { "code": "002361", "name": "神剑股份", "seal_time": "10:17", "seal_amount": 120000000 }
    ]
  }
}
```

### 盯盘股快照接口详细说明

**接口**：`GET /api/simulation/watchlist-snapshot`

| 参数 | 说明 | 示例 |
|------|------|------|
| time | 时间点（HH:MM） | 10:17 |
| date | 日期 | 2026-03-27 |
| codes | 股票代码列表 | 002192,000722,600726 |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "time": "10:17",
    "date": "2026-03-27",
    "items": [
      {
        "code": "002192",
        "name": "融捷股份",
        "price": 76.05,
        "change_pct": 7.25,
        "volume": 150000,
        "amount": 114000000,
        "volume_ratio": 1.8,
        "status": "强势上涨"
      },
      {
        "code": "000722",
        "name": "湖南发展",
        "price": 17.87,
        "change_pct": -2.24,
        "volume": 80000,
        "amount": 14300000,
        "status": "下跌"
      }
    ]
  }
}
```

---

## 账户管理 API (`/api/account`)

| 方法 | 路径 | 功能 | 参数 |
|------|------|------|------|
| GET | `/api/account/status` | 账户状态 | - |
| GET | `/api/account/positions` | 当前持仓 | - |
| GET | `/api/account/trades` | 交易记录 | start_date, end_date |
| POST | `/api/account/trade` | 记录交易 | code, action, price, quantity, reason |
| GET | `/api/account/snapshot` | 每日快照 | date |

---

## API 响应格式统一

```python
# 成功响应
{
    "code": 200,
    "message": "success",
    "data": { ... }
}

# 失败响应
{
    "code": 400,
    "message": "错误描述",
    "data": null
}

# 分页响应
{
    "code": 200,
    "message": "success",
    "data": {
        "items": [...],
        "total": 100,
        "page": 1,
        "page_size": 20
    }
}
```

---

## API 场景化职责划分

| 场景 | 使用 API |
|------|---------|
| 盘前分析 | 日线级别 API（按 date 查询） |
| 前端展示 | 日线级别 API + 分时 API |
| 模拟看盘 | 分钟级别快照 API（按 time + date 查询） |

---

## 模拟看盘工作流

```
盘前：
  1. GET /api/simulation/market-snapshot?time=15:00&date=昨日 → 获取昨日收盘全景
  2. GET /api/market/limit-up-distribution?date=昨日 → 涨停方向分布

模拟盘中（逐分钟推进）：
  3. GET /api/simulation/market-snapshot?time=09:35 → 全市场视角
  4. GET /api/simulation/watchlist-snapshot?time=09:35&codes=... → 盯盘股视角
  5. 分析：哪个方向在走强？盯盘股表现如何？
  6. 判断：是否触发交易信号？
  7. POST /api/account/trade → 记录决策（如有）

模拟盘后：
  8. GET /api/simulation/timeline → 获取完整时间线
  9. 复盘：对比预案 vs 实际
```
