# API 设计

## API 概览

| 模块 | 数量 | 主要用途 |
|------|------|---------|
| 股票 API | 7 | 个股信息、日线、分时、资金流向 |
| 指数 API | 3 | 指数列表、日线、分时 |
| 概念 API | 6 | 概念列表、详情、日线、分时、成分股、排行 |
| 市场 API | 9 | 个股排行、涨跌停、连板天梯、炸板、市场统计 |
| 采集 API | 6 | 手动触发采集、任务状态 |
| 模拟看盘 API | 5 | 全市场快照、盯盘股快照、时间线、详情页 |
| 账户 API | 5 | 状态、持仓、交易记录、快照 |
| **总计** | **41** | |

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

## API 响应格式统一

### 成功响应
```json
{
    "code": 200,
    "message": "success",
    "data": { ... }
}
```

### 失败响应
```json
{
    "code": 400,
    "message": "错误描述",
    "data": null
}
```

### 分页响应
```json
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

## 股票 API (`/api/stock`)

### 1. 获取股票基本信息

**GET** `/api/stock/info/{code}`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 股票代码（如 002192） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "stock_code": "002192",
    "stock_name": "融捷股份",
    "industry": "有色金属",
    "list_date": "2007-12-05",
    "market": "SZ"
  }
}
```

> **数据来源**：`stock_info` 表，按 code 查询

---

### 2. 获取股票日线行情

**GET** `/api/stock/daily/{code}`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 股票代码 |

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| start_date | string | 否 | 开始日期（默认近30日） |
| end_date | string | 否 | 结束日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "stock_code": "002192",
    "stock_name": "融捷股份",
    "items": [
      {
        "trade_date": "2026-03-27",
        "open": 73.33,
        "high": 78.00,
        "low": 72.72,
        "close": 78.00,
        "pre_close": 70.91,
        "change_pct": 9.99,
        "volume": 421223,
        "amount": 3145292965,
        "turnover_rate": 5.23
      }
    ]
  }
}
```

---

### 3. 获取股票分时数据

**GET** `/api/stock/intraday/{code}`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 股票代码 |

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "stock_code": "002192",
    "stock_name": "融捷股份",
    "date": "2026-03-27",
    "items": [
      {
        "time": "09:30",
        "price": 78.00,
        "change": 7.09,
        "change_pct": 10.00,
        "volume": 10000,
        "amount": 780000,
        "avg_price": 78.50
      }
    ]
  }
}
```

---

### 4. 批量获取实时行情

**POST** `/api/stock/realtime`

> 复杂查询使用 POST，避免 URL 过长

**请求体**：
```json
{
  "codes": ["002192", "000722", "600726"]
}
```

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "items": [
      {
        "code": "002192",
        "name": "融捷股份",
        "price": 78.00,
        "change_pct": 10.00,
        "volume": 421223,
        "amount": 3145292965,
        "high": 78.00,
        "low": 72.72,
        "open": 73.33,
        "pre_close": 70.91
      }
    ]
  }
}
```

---

### 5. 获取资金流向

**GET** `/api/stock/capital-flow/{code}`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 股票代码 |

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "stock_code": "002192",
    "stock_name": "融捷股份",
    "date": "2026-03-27",
    "main_net_inflow": 150000000,
    "main_net_inflow_pct": 5.23,
    "retail_net_inflow": -80000000,
    "retail_net_inflow_pct": -2.78,
    "super_net_inflow": 120000000,
    "big_net_inflow": 30000000,
    "mid_net_inflow": -20000000,
    "small_net_inflow": -60000000
  }
}
```

---

### 6. 获取股票所属概念

**GET** `/api/stock/concepts/{code}`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 股票代码 |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "stock_code": "002192",
    "stock_name": "融捷股份",
    "concepts": [
      {
        "concept_code": "BK0612",
        "concept_name": "锂电池",
        "is_core": true,
        "reason": "公司主营业务为锂矿采选"
      },
      {
        "concept_code": "BK0888",
        "concept_name": "有色金属",
        "is_core": false,
        "reason": "公司所属行业"
      }
    ]
  }
}
```

---

### 7. 搜索股票

**GET** `/api/stock/search`

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keyword | string | 是 | 搜索关键词（股票名称或代码） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "items": [
      {
        "stock_code": "002192",
        "stock_name": "融捷股份",
        "industry": "有色金属",
        "market": "SZ"
      }
    ]
  }
}
```

---

## 指数 API (`/api/index`)

### 1. 获取指数列表

**GET** `/api/index/list`

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "items": [
      {"index_code": "000001", "index_name": "上证指数"},
      {"index_code": "399001", "index_name": "深证成指"},
      {"index_code": "399006", "index_name": "创业板指"},
      {"index_code": "000688", "index_name": "科创50"}
    ]
  }
}
```

---

### 2. 获取指数日线

**GET** `/api/index/daily/{code}`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 指数代码（如 000001） |

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| start_date | string | 否 | 开始日期 |
| end_date | string | 否 | 结束日期 |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "index_code": "000001",
    "index_name": "上证指数",
    "items": [
      {
        "trade_date": "2026-03-27",
        "open": 3850.00,
        "high": 3892.00,
        "low": 3840.00,
        "close": 3892.00,
        "change_pct": 0.73,
        "volume": 450000000,
        "amount": 52000000000
      }
    ]
  }
}
```

---

### 3. 获取指数分时

**GET** `/api/index/intraday/{code}`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 指数代码 |

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "index_code": "000001",
    "index_name": "上证指数",
    "date": "2026-03-27",
    "items": [
      {
        "time": "09:30",
        "price": 3850.00,
        "change_pct": 0.12,
        "volume": 5000000,
        "amount": 200000000
      }
    ]
  }
}
```

---

## 概念板块 API (`/api/concept`)

### 1. 获取概念列表

**GET** `/api/concept/list`

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| source | string | 否 | 数据源：east（东方财富）/ ths（同花顺），默认 east |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "source": "east",
    "items": [
      {
        "concept_code": "BK0612",
        "concept_name": "锂电池",
        "component_count": 85
      }
    ]
  }
}
```

---

### 2. 获取概念详情

**GET** `/api/concept/info/{code}`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 概念代码（如 BK0612） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "concept_code": "BK0612",
    "concept_name": "锂电池",
    "component_count": 85,
    "source": "east"
  }
}
```

---

### 3. 获取概念日线

**GET** `/api/concept/daily/{code}`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 概念代码 |

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| start_date | string | 否 | 开始日期 |
| end_date | string | 否 | 结束日期 |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "concept_code": "BK0612",
    "concept_name": "锂电池",
    "items": [
      {
        "trade_date": "2026-03-27",
        "open": 1250.00,
        "high": 1290.00,
        "low": 1245.00,
        "close": 1285.00,
        "change_pct": 3.5,
        "volume": 15000000,
        "amount": 850000000
      }
    ]
  }
}
```

---

### 4. 获取概念分时

**GET** `/api/concept/intraday/{code}`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 概念代码 |

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "concept_code": "BK0612",
    "concept_name": "锂电池",
    "date": "2026-03-27",
    "items": [
      {
        "time": "09:30",
        "price": 1250.00,
        "change_pct": 0.5,
        "volume": 50000,
        "amount": 2500000
      }
    ]
  }
}
```

---

### 5. 获取概念成分股

**GET** `/api/concept/constituents/{code}`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 概念代码 |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "concept_code": "BK0612",
    "concept_name": "锂电池",
    "items": [
      {
        "stock_code": "002192",
        "stock_name": "融捷股份",
        "is_core": true,
        "reason": "公司主营业务为锂矿采选"
      },
      {
        "stock_code": "002466",
        "stock_name": "天齐锂业",
        "is_core": true,
        "reason": "锂矿资源龙头"
      }
    ]
  }
}
```

---

### 6. 获取概念涨幅排行

**GET** `/api/concept/ranking`

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |
| top_n | int | 否 | 返回数量（默认20） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "date": "2026-03-27",
    "items": [
      {
        "concept_code": "BK0612",
        "concept_name": "锂电池",
        "change_pct": 3.5,
        "limit_up_count": 3
      },
      {
        "concept_code": "BK0888",
        "concept_name": "商业航天",
        "change_pct": 2.8,
        "limit_up_count": 2
      }
    ]
  }
}
```

---

## 市场数据 API (`/api/market`)

### 1. 获取个股排行

**GET** `/api/market/stock-ranking`

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| sort | string | 否 | 排序字段：`change_pct`(涨跌幅), `amount`(成交额), `turnover_rate`(换手率), `main_inflow`(大单流入), 默认 `change_pct` |
| order | string | 否 | 排序方向：`desc`(降序), `asc`(升序), 默认 `desc` |
| top_n | int | 否 | 返回数量，默认 20 |
| concept_code | string | 否 | 板块筛选，只返回该板块内个股 |
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "date": "2026-03-27",
    "sort": "change_pct",
    "order": "desc",
    "items": [
      {
        "stock_code": "002192",
        "stock_name": "融捷股份",
        "price": 78.00,
        "change_pct": 10.00,
        "amount": 3150000000,
        "turnover_rate": 5.23,
        "main_inflow": 210000000,
        "concept": "锂电池"
      },
      {
        "stock_code": "002361",
        "stock_name": "神剑股份",
        "price": 25.50,
        "change_pct": 10.00,
        "amount": 2820000000,
        "turnover_rate": 8.15,
        "main_inflow": 180000000,
        "concept": "商业航天"
      }
    ]
  }
}
```

---

### 2. 获取涨停股列表

**GET** `/api/market/limit-up`

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "date": "2026-03-27",
    "items": [
      {
        "stock_code": "002192",
        "stock_name": "融捷股份",
        "close_price": 78.00,
        "change_pct": 10.00,
        "first_time": "09:30:00",
        "last_time": "14:50:00",
        "open_times": 0,
        "limit_times": 4,
        "limit_amount": 120000000,
        "is_broken": false,
        "concept": "锂电池"
      },
      {
        "stock_code": "002466",
        "stock_name": "xxx",
        "close_price": 25.50,
        "change_pct": 10.00,
        "first_time": "09:35:00",
        "last_time": "14:50:00",
        "open_times": 2,
        "limit_times": 1,
        "limit_amount": 80000000,
        "is_broken": true,
        "broken_time": "10:30:00",
        "reseal_time": "11:15:00",
        "concept": "锂电池"
      }
    ]
  }
}
```

> **字段说明**：
> - `is_broken`: 是否炸过板（涨停后打开过）
> - `broken_time`: 首次炸板时间
> - `reseal_time`: 回封时间

---

### 3. 获取炸板股列表

**GET** `/api/market/broken-board`

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "date": "2026-03-27",
    "items": [
      {
        "stock_code": "002466",
        "stock_name": "xxx",
        "close_price": 25.50,
        "change_pct": 8.50,
        "first_time": "09:35:00",
        "broken_time": "10:30:00",
        "reseal_time": null,
        "open_times": 3,
        "concept": "锂电池"
      }
    ]
  }
}
```

> **炸板股**：指涨停后打开，且截至收盘未回封的股票。如果回封了则在涨停列表中标记 `is_broken: true`。

---

### 4. 获取跌停股列表

**GET** `/api/market/limit-down`

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：同涨停股列表

---

### 3. 获取连板天梯

**GET** `/api/market/continuous-board`

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "date": "2026-03-27",
    "ladder": [
      {
        "level": 5,
        "count": 1,
        "stocks": [
          {"code": "002192", "name": "融捷股份", "concept": "锂电池"}
        ]
      },
      {
        "level": 4,
        "count": 2,
        "stocks": [
          {"code": "002361", "name": "神剑股份", "concept": "商业航天"},
          {"code": "600118", "name": "xxx", "concept": "商业航天"}
        ]
      },
      {
        "level": 3,
        "count": 5,
        "stocks": [...] 
      },
      {
        "level": 2,
        "count": 12,
        "stocks": [...]
      },
      {
        "level": 1,
        "count": 58,
        "stocks": [...]
      }
    ],
    "max_level": 5,
    "total_count": 78
  }
}
```

---

### 4. 获取连板股查询

**GET** `/api/market/limit-times/{times}`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| times | int | 是 | 连板数（2=2板，3=3板...） |

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "date": "2026-03-27",
    "limit_times": 3,
    "items": [
      {
        "stock_code": "002192",
        "stock_name": "融捷股份",
        "close_price": 78.00,
        "change_pct": 10.00,
        "industry": "有色金属"
      }
    ]
  }
}
```

---

### 4. 获取市场概览

**GET** `/api/market/overview`

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "date": "2026-03-27",
    "index": {
      "000001": {"name": "上证指数", "price": 3892, "change_pct": 0.73},
      "399001": {"name": "深证成指", "price": 13610, "change_pct": 0.45},
      "399006": {"name": "创业板指", "price": 2188, "change_pct": 0.32}
    },
    "limit_up_count": 78,
    "limit_down_count": 2,
    "total_amount": 210000000000
  }
}
```

---

### 5. 获取涨停方向分布

**GET** `/api/market/limit-up-distribution`

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "date": "2026-03-27",
    "items": [
      {
        "concept_code": "BK0612",
        "concept_name": "锂电池",
        "limit_up_count": 5,
        "stocks": ["002192", "002466", "002460"]
      },
      {
        "concept_code": "BK0888",
        "concept_name": "商业航天",
        "limit_up_count": 3,
        "stocks": ["002361", "600118"]
      }
    ]
  }
}
```

---

### 6. 获取市场统计

**GET** `/api/market/statistics`

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "date": "2026-03-27",
    "limit_up_count": 78,
    "limit_down_count": 2,
    "broken_board_count": 5,
    "max_streak": 5,
    "seal_rate": 93.9,
    "total_amount": 210000000000
  }
}
```

> **数据来源**：
> - `limit_up_count/limit_down_count`：`SELECT COUNT(*) FROM limit_list WHERE trade_date = ? AND limit_type = 'U'/'D'`
> - `broken_board_count`：`SELECT COUNT(*) FROM limit_list WHERE trade_date = ? AND is_broken = TRUE AND reseal_time IS NULL`
> - `max_streak`：`SELECT MAX(limit_times) FROM limit_list WHERE trade_date = ? AND limit_type = 'U'`
> - `seal_rate`：API 层计算 `limit_up_count / (limit_up_count + broken_board_count) * 100`
> - `total_amount`：`SELECT SUM(amount) FROM index_daily WHERE trade_date = ?`

---

## 数据采集触发 API (`/api/collector`)

### 1. 触发股票日线采集

**POST** `/api/collector/stock/daily`

**请求体**：
```json
{
  "code": "002192",
  "start_date": "2026-01-01",
  "end_date": "2026-03-27"
}
```

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "task_id": "task_20260327_001",
    "status": "running"
  }
}
```

---

### 2. 触发股票分时采集

**POST** `/api/collector/stock/intraday`

**请求体**：
```json
{
  "code": "002192",
  "date": "2026-03-27"
}
```

---

### 3. 触发指数日线采集

**POST** `/api/collector/index/daily`

**请求体**：
```json
{
  "code": "000001",
  "start_date": "2026-01-01",
  "end_date": "2026-03-27"
}
```

---

### 4. 触发概念数据采集

**POST** `/api/collector/concept/all`

**请求体**：
```json
{
  "date": "2026-03-27"
}
```

---

### 5. 触发涨跌停采集

**POST** `/api/collector/market/limit`

**请求体**：
```json
{
  "date": "2026-03-27"
}
```

---

### 6. 查询采集任务状态

**GET** `/api/collector/status`

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| task_id | string | 是 | 任务ID |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "task_id": "task_20260327_001",
    "status": "completed",
    "started_at": "2026-03-27T19:30:00",
    "completed_at": "2026-03-27T19:30:15",
    "records_processed": 100
  }
}
```

---

## 模拟看盘专用 API (`/api/simulation`)

### 1. 全市场时间点快照

**POST** `/api/simulation/market-snapshot`

> 复杂查询使用 POST，支持更多参数扩展

**请求体**：
```json
{
  "time": "10:17",
  "date": "2026-03-27",
  "top_n": 10
}
```

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

---

### 2. 盯盘股时间点快照

**POST** `/api/simulation/watchlist-snapshot`

> 批量查询使用 POST

**请求体**：
```json
{
  "time": "10:17",
  "date": "2026-03-27",
  "codes": ["002192", "000722", "600726"]
}
```

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

### 3. 时间线快照序列

**POST** `/api/simulation/timeline`

> 批量查询多个时间点

**请求体**：
```json
{
  "date": "2026-03-27",
  "times": ["09:30", "09:35", "10:00", "10:30", "11:30", "14:00", "15:00"],
  "codes": ["002192", "000722", "600726"]
}
```

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "date": "2026-03-27",
    "snapshots": [
      {
        "time": "09:30",
        "items": [...]
      },
      {
        "time": "09:35",
        "items": [...]
      }
    ]
  }
}
```

---

### 4. 个股详情页

**GET** `/api/simulation/stock-detail/{code}`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 股票代码 |

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "info": {
      "stock_code": "002192",
      "stock_name": "融捷股份",
      "industry": "有色金属"
    },
    "daily": {
      "open": 73.33,
      "high": 78.00,
      "low": 72.72,
      "close": 78.00,
      "change_pct": 9.99,
      "volume": 421223,
      "amount": 3145292965
    },
    "intraday": [...],
    "capital_flow": {...},
    "concepts": [...]
  }
}
```

---

### 5. 概念详情页

**GET** `/api/simulation/concept-detail/{code}`

**路径参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| code | string | 是 | 概念代码 |

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "info": {
      "concept_code": "BK0612",
      "concept_name": "锂电池",
      "component_count": 85
    },
    "daily": {
      "change_pct": 3.5,
      "volume": 15000000,
      "amount": 850000000
    },
    "intraday": [...],
    "constituents": [...]
  }
}
```

---

## 账户管理 API (`/api/account`)

### 1. 获取账户状态

**GET** `/api/account/status`

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "total_asset": 1000000.00,
    "available_cash": 500000.00,
    "market_value": 500000.00,
    "total_profit": 50000.00,
    "total_profit_pct": 5.26
  }
}
```

---

### 2. 获取当前持仓

**GET** `/api/account/positions`

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "items": [
      {
        "stock_code": "002192",
        "stock_name": "融捷股份",
        "quantity": 1000,
        "available": 1000,
        "cost_price": 70.00,
        "current_price": 78.00,
        "market_value": 78000.00,
        "profit": 8000.00,
        "profit_pct": 11.43
      }
    ]
  }
}
```

---

### 3. 获取交易记录

**GET** `/api/account/trades`

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| start_date | string | 否 | 开始日期 |
| end_date | string | 否 | 结束日期 |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "items": [
      {
        "trade_id": "T20260327001",
        "trade_time": "2026-03-27T10:30:00",
        "stock_code": "002192",
        "stock_name": "融捷股份",
        "action": "buy",
        "price": 75.00,
        "quantity": 1000,
        "amount": 75000.00,
        "reason": "突破前高，放量确认"
      }
    ]
  }
}
```

---

### 4. 记录交易

**POST** `/api/account/trade`

**请求体**：
```json
{
  "code": "002192",
  "action": "buy",
  "price": 75.00,
  "quantity": 1000,
  "reason": "突破前高，放量确认"
}
```

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "trade_id": "T20260327001",
    "status": "success"
  }
}
```

---

### 5. 获取每日快照

**GET** `/api/account/snapshot`

**查询参数**：
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| date | string | 否 | 日期（默认今日） |

**返回示例**：
```json
{
  "code": 200,
  "data": {
    "date": "2026-03-27",
    "total_asset": 1000000.00,
    "available_cash": 500000.00,
    "market_value": 500000.00,
    "daily_profit": 5000.00,
    "daily_profit_pct": 0.50,
    "positions": [...]
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
  1. POST /api/simulation/market-snapshot {time: "15:00", date: "昨日"} → 获取昨日收盘全景
  2. GET /api/market/limit-up-distribution?date=昨日 → 涨停方向分布

模拟盘中（逐分钟推进）：
  3. POST /api/simulation/market-snapshot {time: "09:35"} → 全市场视角
  4. POST /api/simulation/watchlist-snapshot {time: "09:35", codes: [...]} → 盯盘股视角
  5. 分析：哪个方向在走强？盯盘股表现如何？
  6. 判断：是否触发交易信号？
  7. POST /api/account/trade → 记录决策（如有）

模拟盘后：
  8. POST /api/simulation/timeline → 获取完整时间线
  9. 复盘：对比预案 vs 实际
```

---

## API 数据来源汇总

### 股票 API 数据来源

| API | 数据表 | 查询逻辑 |
|-----|--------|---------|
| 股票基本信息 | `stock_info` | `SELECT * FROM stock_info WHERE stock_code = ?` |
| 股票日线 | `stock_daily` | `SELECT * FROM stock_daily WHERE stock_code = ? AND trade_date BETWEEN ? AND ?` |
| 股票分时 | `stock_intraday` | `SELECT * FROM stock_intraday WHERE stock_code = ? AND trade_date = ?` |
| 批量实时行情 | `stock_daily` + `stock_info` | 获取最新交易日数据，关联股票名称 |
| 资金流向 | `capital_flow` | `SELECT * FROM capital_flow WHERE stock_code = ? AND trade_date = ?` |
| 股票所属概念 | `stock_concept_mapping_east` + `concept_info_east` | 关联查询，获取概念名称 |
| 搜索股票 | `stock_info` | `SELECT * FROM stock_info WHERE stock_name LIKE ? OR stock_code LIKE ?` |

### 指数 API 数据来源

| API | 数据表 | 查询逻辑 |
|-----|--------|---------|
| 指数列表 | `index_daily` | `SELECT DISTINCT index_code, index_name FROM index_daily` |
| 指数日线 | `index_daily` | `SELECT * FROM index_daily WHERE index_code = ? AND trade_date BETWEEN ? AND ?` |
| 指数分时 | `index_intraday` | `SELECT * FROM index_intraday WHERE index_code = ? AND trade_date = ?` |

### 概念 API 数据来源

| API | 数据表 | 查询逻辑 |
|-----|--------|---------|
| 概念列表 | `concept_info_east` | `SELECT * FROM concept_info_east` |
| 概念详情 | `concept_info_east` | `SELECT * FROM concept_info_east WHERE concept_code = ?` |
| 概念日线 | `concept_daily_east` | `SELECT * FROM concept_daily_east WHERE concept_code = ? AND trade_date BETWEEN ? AND ?` |
| 概念分时 | `concept_intraday_east` | `SELECT * FROM concept_intraday_east WHERE concept_code = ? AND trade_date = ?` |
| 概念成分股 | `stock_concept_mapping_east` + `stock_info` | 关联查询，获取股票名称和核心标识 |
| 概念涨幅排行 | `concept_daily_east` | 按日期筛选，按 change_pct 排序 |

### 市场 API 数据来源

| API | 数据表 | 查询逻辑 |
|-----|--------|---------|
| 个股排行 | `stock_daily` + `capital_flow` + `stock_concept_mapping_east` | 关联查询，按指定字段排序 |
| 涨停股列表 | `limit_list` | `SELECT * FROM limit_list WHERE trade_date = ? AND limit_type = 'U'` |
| 炸板股列表 | `limit_list` | `SELECT * FROM limit_list WHERE trade_date = ? AND is_broken = TRUE AND reseal_time IS NULL` |
| 跌停股列表 | `limit_list` | `SELECT * FROM limit_list WHERE trade_date = ? AND limit_type = 'D'` |
| 连板天梯 | `limit_list` | `SELECT limit_times, COUNT(*), ARRAY_AGG(stock_code) FROM limit_list WHERE trade_date = ? AND limit_type = 'U' GROUP BY limit_times ORDER BY limit_times DESC` |
| 连板股查询 | `limit_list` | `SELECT * FROM limit_list WHERE trade_date = ? AND limit_times = ?` |
| 市场概览 | `index_daily` + `limit_list` | 聚合指数数据 + 统计涨跌停数 |
| 涨停方向分布 | `limit_list` + `stock_concept_mapping_east` | 关联查询，按概念分组统计涨停数 |
| 市场统计 | `limit_list` + `index_daily` | 聚合统计涨停/跌停/炸板数、最高连板；成交额聚合；封板率API层计算 |

### 模拟看盘 API 数据来源

| API | 数据表 | 查询逻辑 |
|-----|--------|---------|
| 全市场快照 | `index_intraday` + `stock_intraday` + `concept_intraday_east` + `limit_list` | 多表联合查询，按时间点筛选 |
| 盯盘股快照 | `stock_intraday` | `SELECT * FROM stock_intraday WHERE stock_code IN (?) AND trade_date = ? AND trade_time = ?` |
| 时间线快照 | `stock_intraday` | 批量查询多个时间点数据 |
| 个股详情页 | `stock_info` + `stock_daily` + `stock_intraday` + `capital_flow` + `stock_concept_mapping_east` | 多表联合 |
| 概念详情页 | `concept_info_east` + `concept_daily_east` + `concept_intraday_east` + `stock_concept_mapping_east` | 多表联合 |

### 账户 API 数据来源

| API | 数据表 | 查询逻辑 |
|-----|--------|---------|
| 账户状态 | `account_info` | `SELECT * FROM account_info WHERE id = ?` |
| 当前持仓 | `position` + `stock_daily` | 关联查询获取当前价格和市值 |
| 交易记录 | `trade_record` | `SELECT * FROM trade_record WHERE account_id = ? ORDER BY trade_time DESC` |
| 记录交易 | `trade_record` + `position` + `account_info` | 插入交易记录，更新持仓和账户 |
| 每日快照 | `account_snapshot` | `SELECT * FROM account_snapshot WHERE account_id = ? AND snapshot_date = ?` |
