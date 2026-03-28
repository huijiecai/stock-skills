# PostgreSQL 数据中枢架构升级方案

## 一、架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据采集层                                │
├──────────────┬──────────────┬──────────────┬──────────────────┤
│   adata      │   Tushare    │   其他数据源  │   手动配置       │
│  (免费行情)   │  (涨停数据)  │  (期货行情)  │  (概念映射)      │
└──────┬───────┴──────┬───────┴──────┬───────┴────────┬─────────┘
       │              │              │                │
       ▼              ▼              ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PostgreSQL (Docker)                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌───────────┐  │
│  │stock_daily  │ │stock_intraday│ │concept_daily│ │ths_tables │  │
│  │个股日线     │ │个股分时      │ │板块日线     │ │同花顺数据  │  │
│  └─────────────┘ └─────────────┘ └─────────────┘ └───────────┘  │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐                │
│  │index_daily  │ │index_intraday│ │stock_concept│                │
│  │指数日线     │ │指数分时      │ │个股概念映射  │                │
│  └─────────────┘ └─────────────┘ └─────────────┘                │
└─────────────────────────────────────────────────────────────────┘
       ▲              ▲              ▲
       │              │              │
┌──────┴───────┬──────┴───────┬──────┴───────┬──────────────────┐
│   Web前端    │   模拟看盘    │   分析服务   │   其他客户端      │
│  (React)     │  (trading-   │  (LLM/分析)  │                  │
│              │   system)    │              │                  │
└──────────────┴──────────────┴──────────────┴──────────────────┘
```

---

## 二、数据库设计

### 2.1 新增表结构

#### concept_info_east - 东方财富概念板块信息

```sql
CREATE TABLE concept_info_east (
    concept_code VARCHAR(20) PRIMARY KEY,  -- 概念代码 (BK0612)
    concept_name VARCHAR(50) NOT NULL,     -- 概念名称 (锂电池)
    component_count INTEGER DEFAULT 0,     -- 成分股数量
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### concept_info_ths - 同花顺概念板块信息（预留）

```sql
CREATE TABLE concept_info_ths (
    concept_code VARCHAR(20) PRIMARY KEY,  -- 概念代码 (886108)
    concept_name VARCHAR(50) NOT NULL,     -- 概念名称 (AI应用)
    index_code VARCHAR(10),                -- 指数代码 (886108)
    component_count INTEGER DEFAULT 0,     -- 成分股数量
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

> **设计说明**：按数据源分表，便于未来同时支持多数据源，避免代码格式冲突。

#### concept_daily_east - 东方财富概念板块日线

```sql
CREATE TABLE concept_daily_east (
    id SERIAL PRIMARY KEY,                -- 自增主键
    trade_date DATE NOT NULL,             -- 交易日期 (2026-03-28)
    concept_code VARCHAR(20) NOT NULL,    -- 概念代码 (BK0612)
    open_price DECIMAL(10,2),             -- 开盘价
    close_price DECIMAL(10,2),            -- 收盘价
    high_price DECIMAL(10,2),             -- 最高价
    low_price DECIMAL(10,2),              -- 最低价
    change_pct DECIMAL(8,4),              -- 涨跌幅 (%)
    volume BIGINT,                        -- 成交量 (手)
    amount DECIMAL(20,2),                 -- 成交额 (元)
    UNIQUE(trade_date, concept_code)
);
CREATE INDEX idx_concept_daily_east_date ON concept_daily_east(trade_date);
CREATE INDEX idx_concept_daily_east_code ON concept_daily_east(concept_code);
```

#### concept_intraday_east - 东方财富概念板块分时

```sql
CREATE TABLE concept_intraday_east (
    id SERIAL PRIMARY KEY,                -- 自增主键
    trade_date DATE NOT NULL,             -- 交易日期 (2026-03-28)
    concept_code VARCHAR(20) NOT NULL,    -- 概念代码 (BK0612)
    trade_time TIME NOT NULL,             -- 交易时间 (09:30:00)
    price DECIMAL(10,2),                  -- 当前价格
    change_pct DECIMAL(8,4),              -- 涨跌幅 (%)
    volume BIGINT,                        -- 成交量 (手)
    amount DECIMAL(20,2),                 -- 成交额 (元)
    UNIQUE(trade_date, concept_code, trade_time)
);
CREATE INDEX idx_concept_intraday_east ON concept_intraday_east(trade_date, concept_code);
```

#### stock_info - 股票基本信息

```sql
CREATE TABLE stock_info (
    stock_code VARCHAR(10) PRIMARY KEY,   -- 股票代码 (002192)
    stock_name VARCHAR(20) NOT NULL,      -- 股票名称 (融捷股份)
    industry VARCHAR(20),                 -- 所属行业 (有色金属)
    list_date DATE,                       -- 上市日期 (2007-12-05)
    market VARCHAR(10),                   -- 交易市场 (SZ/SH)
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### stock_daily - 股票日线行情

```sql
CREATE TABLE stock_daily (
    id SERIAL PRIMARY KEY,                -- 自增主键
    trade_date DATE NOT NULL,             -- 交易日期 (2026-03-28)
    stock_code VARCHAR(10) NOT NULL,      -- 股票代码 (002192)
    open_price DECIMAL(10,2),             -- 开盘价
    close_price DECIMAL(10,2),            -- 收盘价
    high_price DECIMAL(10,2),             -- 最高价
    low_price DECIMAL(10,2),              -- 最低价
    change_pct DECIMAL(8,4),              -- 涨跌幅 (%)
    volume BIGINT,                        -- 成交量 (手)
    amount DECIMAL(20,2),                 -- 成交额 (元)
    turnover_rate DECIMAL(8,4),           -- 换手率 (%) [基于流通股本]
    turnover_rate_f DECIMAL(8,4),         -- 实际换手率 (%) [基于自由流通股本]
    UNIQUE(trade_date, stock_code)
);
CREATE INDEX idx_stock_daily_date ON stock_daily(trade_date);
CREATE INDEX idx_stock_daily_code ON stock_daily(stock_code);
```

#### stock_intraday - 股票分时行情

```sql
CREATE TABLE stock_intraday (
    id SERIAL PRIMARY KEY,                -- 自增主键
    trade_date DATE NOT NULL,             -- 交易日期 (2026-03-28)
    stock_code VARCHAR(10) NOT NULL,      -- 股票代码 (002192)
    trade_time TIME NOT NULL,             -- 交易时间 (09:30:00)
    price DECIMAL(10,2),                  -- 当前价格
    change_pct DECIMAL(8,4),              -- 涨跌幅 (%)
    volume BIGINT,                        -- 成交量 (手)
    amount DECIMAL(20,2),                 -- 成交额 (元)
    avg_price DECIMAL(10,2),              -- 均价
    UNIQUE(trade_date, stock_code, trade_time)
);
CREATE INDEX idx_stock_intraday ON stock_intraday(trade_date, stock_code);
```

#### index_daily - 指数日线

```sql
CREATE TABLE index_daily (
    id SERIAL PRIMARY KEY,                -- 自增主键
    trade_date DATE NOT NULL,             -- 交易日期 (2026-03-28)
    index_code VARCHAR(10) NOT NULL,      -- 指数代码 (000001上证/399001深证/399006创业板)
    index_name VARCHAR(20),               -- 指数名称 (上证指数)
    open_price DECIMAL(10,2),             -- 开盘价
    close_price DECIMAL(10,2),            -- 收盘价
    high_price DECIMAL(10,2),             -- 最高价
    low_price DECIMAL(10,2),              -- 最低价
    change_pct DECIMAL(8,4),              -- 涨跌幅 (%)
    volume BIGINT,                        -- 成交量 (手)
    amount DECIMAL(20,2),                 -- 成交额 (元)
    UNIQUE(trade_date, index_code)
);
CREATE INDEX idx_index_daily_date ON index_daily(trade_date);
```

#### index_intraday - 指数分时

```sql
CREATE TABLE index_intraday (
    id SERIAL PRIMARY KEY,                -- 自增主键
    trade_date DATE NOT NULL,             -- 交易日期 (2026-03-28)
    index_code VARCHAR(10) NOT NULL,      -- 指数代码 (000001/399001/399006)
    trade_time TIME NOT NULL,             -- 交易时间 (09:30:00)
    price DECIMAL(10,2),                  -- 当前点位
    change_pct DECIMAL(8,4),              -- 涨跌幅 (%)
    volume BIGINT,                        -- 成交量 (手)
    amount DECIMAL(20,2),                 -- 成交额 (元)
    UNIQUE(trade_date, index_code, trade_time)
);
CREATE INDEX idx_index_intraday ON index_intraday(trade_date, index_code);
```

#### stock_concept_mapping_east - 东方财富个股概念映射

```sql
CREATE TABLE stock_concept_mapping_east (
    id SERIAL PRIMARY KEY,                -- 自增主键
    stock_code VARCHAR(10) NOT NULL,      -- 股票代码 (002192)
    concept_code VARCHAR(20) NOT NULL,    -- 概念代码 (BK0612)
    is_core BOOLEAN DEFAULT FALSE,        -- 是否核心标的 (龙头股)
    reason TEXT,                          -- 入选原因 (公司主营业务为...)
    UNIQUE(stock_code, concept_code)
);
CREATE INDEX idx_stock_concept_east_stock ON stock_concept_mapping_east(stock_code);
CREATE INDEX idx_stock_concept_east_concept ON stock_concept_mapping_east(concept_code);
```

#### stock_concept_mapping_ths - 同花顺个股概念映射（预留）

```sql
CREATE TABLE stock_concept_mapping_ths (
    id SERIAL PRIMARY KEY,                -- 自增主键
    stock_code VARCHAR(10) NOT NULL,      -- 股票代码 (002192)
    concept_code VARCHAR(20) NOT NULL,    -- 概念代码 (886108)
    is_core BOOLEAN DEFAULT FALSE,        -- 是否核心标的 (龙头股)
    reason TEXT,                          -- 入选原因
    UNIQUE(stock_code, concept_code)
);
CREATE INDEX idx_stock_concept_ths_stock ON stock_concept_mapping_ths(stock_code);
CREATE INDEX idx_stock_concept_ths_concept ON stock_concept_mapping_ths(concept_code);
```

---

> **注意**：本次升级为全新架构，现有 SQLite 数据库将废弃，不再迁移。

## 三、实现步骤

### Task 1: Docker 环境搭建

**文件**: `backend/docker-compose.yml`, `backend/.env.example`

- 创建 docker-compose.yml
- 配置 PostgreSQL 数据卷持久化
- 创建 .env.example 模板

### Task 2: 数据库初始化脚本

**文件**: `backend/scripts/pg_init.py`

- 创建所有表结构
- 创建索引
- 插入基础数据（概念列表、指数列表）

### Task 3: 数据采集服务重构

**文件**: `backend/app/services/data_collector.py`

- 整合 adata 数据采集逻辑
- 支持 PostgreSQL 写入
- 支持增量采集（避免重复）

### Task 4: 定时任务配置

**文件**: `backend/scripts/cron_tasks.sh`, `backend/scripts/run_collector.py`

- 每日16:30采集日线数据
- 每日16:35采集分时数据
- 每日16:40采集概念板块数据
- 每日16:45更新概念成分股映射

### Task 5: 后端 API 适配

**文件**: `backend/app/services/data_service.py`, `backend/app/api/`

- 将 sqlite3 连接改为 psycopg2
- 新增模拟看盘专用 API
- 新增全局视角查询 API

### Task 6: 模拟看盘数据接口

**文件**: `backend/app/api/simulation.py`

新增 API：

| API | 功能 |
|-----|------|
| `GET /api/simulation/daily-overview` | 当日全景概览 |
| `GET /api/simulation/stock-intraday/{code}` | 个股分时 |
| `GET /api/simulation/concept-intraday/{code}` | 板块分时 |
| `GET /api/simulation/limit-up-stocks` | 当日涨停股 |
| `GET /api/simulation/concept-ranking` | 板块涨幅排行 |

---

## 四、定时任务配置

```bash
# crontab -e
# 每个交易日 16:30 执行数据采集
30 16 * * 1-5 cd /path/to/backend && python scripts/run_collector.py daily >> /var/log/stock/collector.log 2>&1

# 每周一更新概念列表和成分股
0 9 * * 1 cd /path/to/backend && python scripts/run_collector.py concepts >> /var/log/stock/concepts.log 2>&1
```

---

## 五、预期收益

| 功能 | 现状 | 升级后 |
|------|------|--------|
| 数据存储 | SQLite 单文件 | PostgreSQL 服务化 |
| 数据采集 | 手动执行 | 定时自动 |
| 板块数据 | 无 | 完整日线+分时 |
| 个股-概念映射 | 静态配置 | 动态更新 |
| 全局视角 | 无法获取 | 支持涨跌排行 |
| 模拟看盘 | 手动加载JSON | API 即时查询 |

---

## 六、文件变更清单

| 操作 | 文件路径 |
|------|------------|
| 新建 | `backend/docker-compose.yml` |
| 新建 | `backend/scripts/pg_init.py` |
| 新建 | `backend/scripts/run_collector.py` |
| 新建 | `backend/app/services/data_collector.py` |
| 新建 | `backend/app/api/simulation.py` |
| 修改 | `backend/app/services/data_service.py` |
| 修改 | `backend/.env` |
| 修改 | `backend/app/main.py` |
| 删除 | `backend/scripts/db_init.py` (SQLite版废弃) |
| 删除 | `data/dragon_stock.db` (SQLite数据库废弃) |
