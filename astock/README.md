# astock

A 股量化数据 CLI 工具。多数据源行情持久化到 PostgreSQL，统一 CLI 接口查询。

## 快速开始

```bash
# 设置环境变量
export ASTOCK_DB_HOST=localhost
export ASTOCK_DB_PORT=5432
export ASTOCK_DB_NAME=astock
export ASTOCK_DB_USER=postgres
export ASTOCK_DB_PASS=postgres

# 构建
make build

# 查询日K
./build/astock daily 600519

# JSON 输出（供 AI 解析）
./build/astock daily 000001 --json

# 批量同步历史数据
./build/astock sync --today
```

## 命令

| 命令 | 说明 |
|------|------|
| `daily <code>` | 日K线 |
| `minute <code>` | 分钟K线 |
| `rank volume\|limit-up` | 排名 |
| `info stocks\|concepts` | 基础信息 |
| `sync [code...]` | 批量同步 |
| `stats` | 数据统计 |

## 环境变量

| 变量 | 默认值 |
|------|--------|
| `ASTOCK_DB_HOST` | localhost |
| `ASTOCK_DB_PORT` | 5432 |
| `ASTOCK_DB_NAME` | astock |
| `ASTOCK_DB_USER` | postgres |
| `ASTOCK_DB_PASS` | postgres |
| `ASTOCK_RETENTION_DAYS` | 30 |

## 设计

详见 [设计文档](../docs/superpowers/specs/2026-05-24-astock-design.md)。
