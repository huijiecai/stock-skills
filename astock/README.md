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

## 同步频率分级（每日复盘指南）

按数据变化频率把同步任务分三档，避免每日盘后无差别全量同步浪费 IO：

| 档位 | 数据类型 | 变化频率 | 建议节奏 | 命令 |
|------|---------|---------|---------|------|
| 🔴 高频 | `kline_daily` / `market` 衍生 / `limit` 衍生 / `block_daily` | 每个交易日收盘后 | **每日盘后必跑** | `sync all --all --days 1 --skip-info --skip-finance --skip-xdxr --skip-minute` |
| 🔴 高频（监控股） | `kline_minute` (1m/5m) | 每个交易日 | **每日盘后跑 watch list** | `sync all --code <持仓+候选> --days 1 --skip-info --skip-finance --skip-xdxr`（自动同步 daily+1m+5m） |
| 🟡 中频 | `xdxr`（除权除息）/ `finance`（季报） | 公告日 / 季报披露窗口 | **每周一次 或 事件驱动** | `sync all --all --skip-info --skip-minute`（保留 xdxr+finance） |
| 🟢 低频 | `info`（F10）/ `meta`（标的列表）/ `block`（板块成分） | 月级别 / 上市退市 | **每月一次** | `sync meta` + `sync all --all --skip-finance --skip-xdxr --skip-minute`（仅刷 info+daily） |

**典型每日盘后命令组合**：

```bash
# 1. 全市场 daily K（每个交易日必做，10-30 min）
./astock sync all --all --days 1 --skip-info --skip-finance --skip-xdxr --skip-minute

# 2. 持仓 + 候选股的多频率 K 线（一条走完 daily + 1m + 5m）
./astock sync all --code 600487,002463,002971,600378,002409 --days 1 \
    --skip-info --skip-finance --skip-xdxr
```

### 按需补漏原则（minute K）

minute K 不采取全市场每日全量同步（成本不划算：5500+ 只 × 2 频率 ≈ 30min-1.5h，99% 数据不会被复盘访问）。**采用"盘后跑监控股 + 事后按需补拉"策略**：

```bash
# 复盘时发现某只漏掉了 minute K，随手补一只（几秒钟）
./astock sync kline --code 603893 --freq 1m --days 1

# 补多天历史 5m K（超 800 根会告警截断，5m 上限 ≈16 天）
./astock sync kline --code 603893 --freq 5m --days 16
```

sync 服务一直在跑，不需要提前把所有数据都准备好。

> 💡 如需单频率手动同步（如仅 60m K 有3 个月、或补历史 30m），才走底层：`sync kline --code <code> --freq 60m --days 60`。日常复盘推荐 `sync all` 语义路径。

**注意事项**：
- 当前 `sync all` 是**幂等覆盖式同步**，无"已最新就跳过"的智能分支——每次都会从 TDX 重拉对应区间，请合理使用 `--skip-*` 标志
- `--all` 模式下全市场 5500+ 只 × 6 类数据 ≈ 数小时，**勿在交易时段执行**
- minute K 仅对 `--code` 指定的标的同步（TDX 单次 800 根上限），不支持 `--all` 全市场分钟 K
- `sync all` 默认同步 1m + 5m 两种分钟频率；15m/30m/60m 需手动走底层 `sync kline --freq <freq>`
- `sync kline` 已与 `sync all` 对齐：推荐用 `--days N`（按 freq 自动换算根数，超 800 根会告警截断）；`--count N` 仅作底层 escape hatch，与 `--days` 互斥

## 设计

详见 [设计文档](../docs/superpowers/specs/2026-06-13-astock-ch-design.md)。
