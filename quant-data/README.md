# jstock — 量化数据中心

A 股量化数据自包含数据中心，零第三方依赖（不用 adata / tushare / akshare），直连东方财富 + 同花顺原生 HTTP 接口。

## 目录

```
quant-data/
├── collector/        行情采集（HTTP客户端）
│   ├── eastmoney.py  东方财富（个股/指数/概念：日K/分时/列表）
│   └── ths.py        同花顺（日K/周K/月K历史，免鉴权）
├── api/              FastAPI 查询服务
│   └── main.py       端口 8100
├── scripts/          运维脚本
│   ├── import_base_info.py   从 stock 库 bootstrap 基础表
│   ├── init_db.py            全量初始化（东方财富主力）
│   ├── fill_daily_ths.py     同花顺日K采集（备用/主力）
│   └── daily_sync.py         每日增量同步
├── sql/schema.sql    表结构 DDL
├── config.py         数据库配置 + 保留期
└── logs/             日志
```

## 数据库

- **Database**: `jstock`（运行在 `stock_postgres` Docker 实例，5432 端口）
- **连接**: `postgresql://postgres:password@localhost:5432/jstock`

5 张表：

| 表           | 用途                                   | 主键                     |
| ------------ | -------------------------------------- | ------------------------ |
| stock_info   | A股基础信息                            | code                     |
| concept_info | 东方财富概念板块                       | code                     |
| trade_cal    | 交易日历                               | trade_date               |
| daily_k      | 日K（stock / index / concept 统一）    | code, trade_date, type   |
| minute_k     | 分钟K（1m/5m/15m/30m/60m + 分时统一）  | code, dt, freq, type     |

滚动保留 30 天（`config.RETENTION_DAYS`），每次增量后触发清理。

## 数据源

| 源       | 用途                            | 鉴权       | 备注                             |
| -------- | ------------------------------- | ---------- | -------------------------------- |
| 东方财富 | 日K/分时/列表/概念              | 无         | 需 `Referer: quote.eastmoney.com` |
| 同花顺   | 日K/周K/月K（历史 140+ 天）     | 无         | JSONP `/v6/line/last.js`         |

两个源互为备份：东方财富被限流时可直接切同花顺（`fill_daily_ths.py`）。

## 快速开始

```bash
# 1. 建库 & 建表（已完成）
docker exec stock_postgres createdb -U postgres jstock
docker exec -i stock_postgres psql -U postgres -d jstock < sql/schema.sql

# 2. Bootstrap 基础表（从已有 stock 库复用）
.venv/bin/python3 quant-data/scripts/import_base_info.py

# 3. 采集最近 30 天日K（同花顺源，~70 分钟）
.venv/bin/python3 quant-data/scripts/fill_daily_ths.py --days 30

# 4. 或者等东方财富 IP 解封后，全量初始化（含概念、指数日K）
.venv/bin/python3 quant-data/scripts/init_db.py

# 5. 启动查询 API
.venv/bin/python3 quant-data/api/main.py
# http://localhost:8100/docs
```

## 每日维护

建议 crontab 16:30 运行增量：

```
30 16 * * 1-5 cd /Users/huijiecai/Project/stock && .venv/bin/python3 quant-data/scripts/daily_sync.py
```

## API 速查

| 路径                  | 作用                          |
| --------------------- | ----------------------------- |
| `GET /api/stock/list` | 股票列表                      |
| `GET /api/concept/list` | 概念板块列表                |
| `GET /api/stock/{code}` | 单股信息                    |
| `GET /api/daily/{code}?type=stock&limit=30` | 日K  |
| `GET /api/minute/{code}?freq=5m` | 分钟K              |
| `GET /api/trade_cal`  | 交易日历                      |
| `GET /stats`          | 库内数据概况                  |
| `GET /health`         | 健康检查                      |

## 设计约束

1. **零外部库**：只用 `requests + psycopg2 + fastapi`，不依赖 adata/tushare。
2. **统一 secid**：东方财富 3 个端点共用，stock/index/concept 只换前缀。
3. **UPSERT**：所有入库走 `ON CONFLICT ... DO UPDATE`，重复运行无副作用。
4. **滚动清理**：日K/分钟K 超过 `RETENTION_DAYS` 自动删除。
