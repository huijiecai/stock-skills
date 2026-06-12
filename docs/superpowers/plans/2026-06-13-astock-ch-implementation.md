# astock ClickHouse 重构 — 实施计划

> 配套设计文档：`../specs/2026-06-13-astock-ch-design.md`
> 替代旧实施计划 `2026-05-24-astock-implementation.md`

## 任务总览

按依赖顺序串行推进，每个 Task 必须达到"验证标准"才进入下一个。

| Task | 内容 | 交付物 | 验证标准 |
|------|------|--------|----------|
| **T1 清理与脚手架** | 删除旧 PG 代码与旧文档；重建 cobra 骨架；新 Makefile；`go.mod` 保留 `injoyai/tdx v0.0.79` | `astock --help` | 二进制可跑 |
| **T2 ClickHouse 部署** | `docker-compose.yml`（image `clickhouse/clickhouse-server:24.8`，端口 8123/9000）；`./data/clickhouse` 挂载；时区 `Asia/Shanghai` | `docker compose up -d` | `clickhouse-client` 能连 9000，`SELECT version()` 返回 |
| **T3 TDX 封装层** | `internal/tdx`：client(lazy reconnect) + meta + kline + live + block + xdxr + finance；移植 indexCode 修复 | 包级单元测试 | 茅台日K + 上证指数日K + 深证成指 不 panic；GetXDXR/GetFinance 返回有效数据 |
| **T4 dwh 层** | `internal/dwh`：conn + schema + 9 张表 DDL（securities/blocks/block_constituents/trade_cal/xdxr/finance/kline_daily/kline_minute/sync_log）；批量写入接口（每批 10000 行） | `astock init` 命令 | `SHOW TABLES IN astock` 返回 9 张表 |
| **T5 sync meta + info** | 股票/指数/板块/交易日历同步；F10 公司信息（行业/主营）入 securities 扩展字段 | `astock sync meta`、`astock sync info` | securities 行数 ≥ 5000 且 industry/sector 非空；blocks 行数 ≥ 500 |
| **T6 sync daily + xdxr** | 全市场日K & 单只日K，from→to 滑窗（每次 800 根）；除权除息同步 | `astock sync daily --code 600519 --from 20100101`、`astock sync xdxr --all` | kline_daily 中茅台 ≥ 3000 行；xdxr 表茅台 ≥ 10 行 |
| **T7 sync minute & block & finance** | 分钟K & 板块成分股 & 财务数据；并发 goroutine 池（max=10） | `astock sync minute --all --days 30`、`astock sync block`、`astock sync finance --all` | kline_minute 茅台/平安 ≥ 5000 行；finance 表茅台 ≥ 4 个季度 |
| **T8 sync all + status** | 复合命令（meta+daily+minute+block+xdxr）；sync_log 写入 | `astock sync all --days 1` 可作每日 cron | `astock status` 显示历史任务 |
| **T9 query 命令族** | daily/minute/stock/block/finance/xdxr 六个子命令；daily 支持 `--adjust qfq/hfq/raw` SQL JOIN 复权；stock 支持 `--industry` 筛选；table/json/csv 输出 | 全部 query 子命令 | `query daily 600519 --adjust qfq` 与同花顺前复权价一致 |
| **T10 live 命令族** | quote（含五档盘口展开） / tick（今日+ `--date` 历史） / minute 直连 TDX | live 全部子命令 | 盘中可见报价滚动更新；quote 输出含 bid1–bid5/ask1–ask5；tick --date 返回历史分笔 |
| **T11 stats 与打磨** | stats 行数/分区/磁盘；错误处理；README | 文档 + 发布 | `make build && make test` 通过 |

## 待删除的内容（T1 执行）

- `docs/superpowers/specs/2026-05-24-astock-design.md`（旧 PG 设计）
- `docs/superpowers/plans/2026-05-24-astock-implementation.md`（旧实施计划）
- `astock/internal/db/`（PG 相关 5 个文件）
- `astock/internal/fetch/{baidu,eastmoney,sectors,sina,stocklist,tencent,ths,selector}.go`（多源 fetch）
- `astock/internal/query/`（旧 router/cache）
- `astock/cmd/astock/*.go`（除 main.go 外内容按新结构重写）
- `data/postgres/`（PG 数据目录）

## 保留并复用

- `astock/internal/fetch/tdx.go` → `astock/internal/tdx/`（含 indexCode 修复，T3 种子）
- `astock/internal/model/` 的 Bar/Quote/Stock 类型（按需调整）
- `go.mod` 的 `injoyai/tdx v0.0.79` 依赖

## 里程碑

- **M1（T1–T4）**：脚手架就绪，ClickHouse 起来，schema 落库
- **M2（T5–T8）**：数据可灌进来，全市场基础数据可用
- **M3（T9–T11）**：CLI 全功能可用，发布 v0.1.0

## 验收标准

完成全部 T1–T11 后，下列命令必须全部可用：

```bash
# 部署
docker compose up -d
astock init
astock sync meta
astock sync info                          # F10 公司信息

# 灌数据（一次性）
astock sync daily --all --from 20240101
astock sync minute --all --days 30
astock sync block
astock sync xdxr --all                    # 复权基础
astock sync finance --all                 # 财务（每季跑一次）

# 日常使用
astock sync all --days 1                  # 每日 cron（含 xdxr，不含 finance）
astock query daily 600519 --limit 30
astock query daily 600519 --adjust qfq    # 前复权
astock query stock --industry 白酒
astock query block constituents BK0612
astock query finance 600519               # 财务数据
astock query xdxr 600519                  # 除权除息记录
astock live quote 600519 000001           # 实时报价 + 五档盘口
astock live tick 600519 --date 20240320   # 历史分笔
astock stats
```
