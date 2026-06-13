# astock

A 股量化数据 CLI 工具。多源行情（TDX 通达信为主）持久化到 ClickHouse，统一 cobra 命令树查询。

## 快速开始

```bash
# 1. 启动 ClickHouse（项目根 data/clickhouse 目录已配好）
docker compose up -d

# 2. 设置环境变量（默认值已可用，仅生产覆盖）
export CH_HOST=localhost
export CH_PORT=9000
export CH_DATABASE=astock
export CH_USER=default
export CH_PASSWORD=

# 3. 构建
make build      # 产物：./astock

# 4. 初始化表结构（一次性）
./astock init

# 5. 同步元数据 + 全套数据
./astock sync meta                              # 全市场 securities 元数据
./astock sync kline --code 600519               # 单只历史日 K（默认 freq=daily）
./astock sync kline --code 600519 --freq 5m     # 单只 5 分钟 K
./astock sync all --days 1                      # 每日增量（cron 用）

# 6. 查询
./astock query kline 600519                     # 默认 daily 30 行
./astock query kline 600519 --ma 5,10,20 --json # 加均线 + AI 友好 JSON 输出
./astock query market                           # 市场全景快照
./astock query limit ladder                     # 连板天梯
./astock live quote 600519                      # 盘中实时报价（非交易日自动拒绝）
```

## 命令树速览

```
init                                 建表
sync meta | kline | block | xdxr | finance | info | all | status
query kline | stock | block (list/rank/members) | info | finance | xdxr | market | limit (ladder)
live  quote | tick | minute | block (rank/members)
stats [table]
```

详尽用法见 `astock <verb> --help` 与设计文档。

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `CH_HOST` | `localhost` | ClickHouse 主机 |
| `CH_PORT` | `9000` | TCP 原生端口（非 HTTP 8123） |
| `CH_DATABASE` | `astock` | 库名 |
| `CH_USER` | `default` | 用户名 |
| `CH_PASSWORD` | _空_ | 密码 |

输出格式：所有子命令默认对齐表格，`--json` 切到 AI 友好 JSON，`--csv` 输出 CSV。

## 设计

详见 [设计文档](../docs/superpowers/specs/2026-06-13-astock-ch-design.md)。
