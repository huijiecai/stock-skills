# astock — A 股量化数据 CLI 平台设计

## 一、概述

### 1.1 定位

本地 A 股量化数据 CLI 工具，一人使用，Mac 本机运行。将多数据源的行情数据持久化到 PostgreSQL，通过统一的 CLI 接口对外提供服务，供 AI 工具（Claude Code / Cursor / Qoder）和人类用户查询。

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **单二进制** | 全 Go 实现，零 Python 依赖，CI 产出即用 |
| **读透明** | 历史数据缓存到 PG，盘中实时直连数据源，调用方无感知 |
| **多源统一** | 不同数据源的同一类数据落库后字段语义完全一致 |
| **按需填充** | 冷启动用 `astock sync` 按范围填充，查询 trigger 自动缓存 |

### 1.3 核心约束

- 一人使用，Mac 本机，PostgreSQL 已安装
- 数据保留天数 30 天（可配置）
- 历史分钟 K 线需通达信 TCP 协议，其余均为 HTTP
- CLI 默认输出 `table`，`--json` 供 AI 解析

---

## 二、系统架构

```
┌──────────────────────────────────────────┐
│          AI 工具 / 终端用户                │
│  Claude Code / Cursor / Qoder / shell    │
└──────────────────┬───────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────┐
│             astock CLI                   │
│  daily / minute / rank / info / sync    │
└──────┬───────────────────────────┬───────┘
       │                           │
       ▼                           ▼
┌──────────────┐     ┌──────────────────────────┐
│   查询路由    │     │    批量同步 (sync)        │
│  ┌────────┐  │     │  复用同一套 fetch 逻辑     │
│  │ PG 查  │  │     │                          │
│  │ 有→返回│  │     │  写入                      │
│  │ 无→    │  │     │   │                       │
│  └────┬───┘  │     │   ▼                       │
│       ▼      │     │  ┌────┐                   │
│  ┌────────┐  │     │  │ PG │                   │
│  │ fetch  │  │     │  └────┘                   │
│  │ 数据源  │  │     └──────────────────────────┘
│  └───┬────┘  │
│      │       │
│      ▼       │
│  ┌────────┐  │
│  │ 写 PG  │  │
│  │ (异步)  │  │
│  └────────┘  │
└──────────────┘
       │
       ▼
┌──────────────────────────────────────────┐
│           数据源层 (fetch)                │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌────────┐  │
│  │通达信 │ │东财  │ │腾讯  │ │同花顺   │  │
│  │ TCP  │ │HTTP │ │HTTP │ │HTTP   │  │
│  └──────┘ └──────┘ └──────┘ └────────┘  │
└──────────────────────────────────────────┘
```

### 2.1 查询层（自动决策）

`daily`、`minute`、`rank`、`info`  所有命令操作同一查询层，不感知底层数据源：

```
CLI 命令（daily / minute / rank / info）
          │
          ▼
┌─────────────────────┐
│     查询层           │  自动决策：盘后用 PG、盘中走数据源
│  ┌─────────────────┐ │
│  │ PG 有数据 → 返回 │ │
│  │ PG 无数据       │ │
│  │  → 数据源 fetch  │ │
│  │  → 盘后: 写 PG  │ │
│  │  → 返回         │ │
│  └─────────────────┘ │
│  --force: 跳过 PG    │
└─────────────────────┘
```

**盘中 vs 盘后自动判断逻辑（调用方不感知）：**

| 数据时效 | 行为 |
|----------|------|
| **实时数据**（盘中 daily/minute/rank） | 每次查询都从数据源拉最新数据 |
| **历史数据**（盘后 daily/minute/rank） | 查 PG 缓存，没有则从数据源拉并缓存 |
| **基础信息**（info stocks/concepts） | 查 PG 缓存，没有则从数据源拉并缓存 |
| `--force` | 无论实时还是历史，都从数据源重新拉取并更新缓存 |

**缓存写入规则（避免缓存不完整数据）：**

| 触发场景 | 写入 | 原因 |
|----------|------|------|
| **盘中**（daily/minute/rank） | 不写 PG | 盘中数据不完整，缓存无意义 |
| **盘后 + PG 无数据**（daily/minute/rank） | 异步写 PG | 完整数据，缓存后可复用 |
| `--force` | 异步写 PG | 用户明确要求刷新 |
| `sync` 命令 | 同步写 PG | 主动批量填充 |

**注意：** 盘中实时数据返回后不写入 PG，避免后续盘后查询读到不完整的盘中快照。完整数据通过 `sync --today` 或盘后首次查询触发缓存。

`sync` 是唯一直接操作数据层的命令（绕开查询层，数据源 → 同步写 PG）。

### 2.2 数据源优先级

| 数据类型 | 场景 | 主源 | 备源 |
|----------|------|------|------|
| 个股日K | 盘后历史 | 通达信 | 东财 |
| 个股日K | 盘中实时 | 东财 | 通达信 |
| 指数日K | 盘后历史 | 通达信 | 东财 |
| 概念日K | 盘后历史 | 通达信 | 同花顺 |
| 分钟K (全历史) | 盘后历史 | 通达信 | — |
| 今日分时 | 盘中实时 | 东财 | 通达信 |
| 个股实时报价 | 盘中实时 | 东财 | 腾讯 |
| 概念列表/成分股 | 基础信息 | 东财 | 同花顺 |
| 股票列表 | 基础信息 | 东财 | 通达信 |
| 成交额 TOP30 | 实时排名 | 东财 | — |
| 涨停天梯 | 实时排名 | 东财 | 通达信 |
| PE/PB/市值 | 估值 | 腾讯 | 东财 |

数据源返回后映射为统一模型，再落 PG 或输出。

---

## 三、数据模型

### 3.1 PostgreSQL 表结构

```sql
CREATE DATABASE astock;

-- 股票基础信息
CREATE TABLE stock_info (
    code       VARCHAR(10) PRIMARY KEY,
    name       VARCHAR(50) NOT NULL,
    exchange   VARCHAR(4) NOT NULL,  -- sh / sz / bj
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 同花顺概念板块
CREATE TABLE concept_info (
    code        VARCHAR(10) PRIMARY KEY,  -- BKxxxx
    name        VARCHAR(50) NOT NULL,
    stock_count INTEGER DEFAULT 0,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 概念成分股
CREATE TABLE concept_constituents (
    concept_code VARCHAR(10) NOT NULL REFERENCES concept_info(code),
    stock_code   VARCHAR(10) NOT NULL REFERENCES stock_info(code),
    PRIMARY KEY (concept_code, stock_code)
);

-- 交易日历
CREATE TABLE trade_cal (
    trade_date DATE PRIMARY KEY,
    is_trade   BOOLEAN NOT NULL DEFAULT TRUE
);

-- 日K (个股/指数/概念统一)
CREATE TABLE daily_k (
    code       VARCHAR(10) NOT NULL,
    trade_date DATE NOT NULL,
    type       VARCHAR(10) NOT NULL DEFAULT 'stock',  -- stock / index / concept
    open       DOUBLE PRECISION,
    high       DOUBLE PRECISION,
    low        DOUBLE PRECISION,
    close      DOUBLE PRECISION,
    pre_close  DOUBLE PRECISION,
    change_pct DOUBLE PRECISION,
    volume     BIGINT,
    amount     DOUBLE PRECISION,
    turnover   DOUBLE PRECISION,
    PRIMARY KEY (code, trade_date, type)
);
CREATE INDEX idx_daily_k_date ON daily_k (trade_date);
CREATE INDEX idx_daily_k_type ON daily_k (type);

-- 分钟K (个股/指数/概念统一)
CREATE TABLE minute_k (
    code      VARCHAR(10) NOT NULL,
    dt        TIMESTAMP NOT NULL,
    freq      VARCHAR(5) NOT NULL,  -- 1m / 5m / 15m / 30m / 60m
    type      VARCHAR(10) NOT NULL DEFAULT 'stock',
    open      DOUBLE PRECISION,
    high      DOUBLE PRECISION,
    low       DOUBLE PRECISION,
    close     DOUBLE PRECISION,
    volume    BIGINT,
    amount    DOUBLE PRECISION,
    avg_price DOUBLE PRECISION,
    PRIMARY KEY (code, dt, freq, type)
);
CREATE INDEX idx_minute_k_dt   ON minute_k (dt);
CREATE INDEX idx_minute_k_freq ON minute_k (freq);
```

### 3.2 数据模型统一说明

不同数据源对同一字段可能有不同命名，落 PG 前统一成上表中的字段：

| 标准字段 | 东财 | 通达信 | 腾讯 |
|----------|------|--------|------|
| `open` | f52/parts[1] | open | 同左 |
| `close` | f53/parts[2] | close | 同左 |
| `volume` | f57/parts[5] | volume | 同左 |
| `amount` | f58/parts[6] | amount | 同左 |
| `turnover` | f62/parts[10] | turnover% | — |

### 3.3 滚动清理

```sql
DELETE FROM daily_k  WHERE trade_date < CURRENT_DATE - 30;
DELETE FROM minute_k WHERE dt < CURRENT_DATE - 30;
```

---

## 四、CLI 命令设计

### 4.1 命令树

```
astock                    # 显示帮助
├── daily <code>          # 查询日K（查询层自动缓存）
│     --type              # stock / index / concept (默认 stock)
│     --start             # 开始日期
│     --end               # 结束日期
│     --limit             # 条数 (默认 30)
│     --force             # 跳过缓存，强制从数据源获取
│     --json              # JSON 输出 (默认 table)
│
├── minute <code>         # 查询分钟K（查询层自动缓存）
│     --type              # stock / index / concept
│     --freq              # 1m / 5m / 15m / 30m / 60m (默认 1m)
│     --date              # 指定日期
│     --force
│     --json
│
├── rank                  # 查询排名（查询层自动缓存）
│     volume              # 成交额 TOP30
│     limit-up            # 涨停天梯
│     --json
│
├── info                  # 基础信息
│     stocks              # 股票列表
│     concepts            # 概念列表
│     --exchange          # 过滤交易所
│     --json
│
├── sync [code...]        # 批量同步历史数据
│     --type              # stock / index / concept / all（默认 all）
│     --days              # 近N天 (默认 30)
│     --start             # 开始日期（与 --end 成对使用）
│     --end               # 结束日期
│     --today             # 今日同步（= --start 今天 --end 今天）
│     --json              # 输出同步结果统计
│
├── stats                 # 数据概况统计
│     --json
│
├── version               # 版本信息
└── help                  # 帮助
```

### 4.2 输出默认格式示例

```bash
$ astock daily 000001

 代码   日期       开盘     收盘     最高     最低     涨幅%    成交量
 000001 2026-05-22 3208.92  3215.38  3230.89  3204.83  +0.35%  3.21亿
 000001 2026-05-23 3215.38  3220.50  3235.12  3210.11  +0.16%  2.98亿
 000001 2026-05-24 3220.50  3198.76  3225.43  3192.08  -0.68%  3.45亿
```

```bash
$ astock daily 000001 --json

{"code":"000001","type":"stock","total":30,"data":[
  {"trade_date":"2026-05-22","open":3208.92,"close":3215.38,...},
  ...
]}
```

---

## 五、数据采集设计

### 5.1 数据源统一接口

```go
// internal/fetch/fetcher.go
type Fetcher interface {
    // 历史日K
    DailyKline(ctx context.Context, code string, tp string, opts ...Option) ([]Bar, error)
    // 历史分钟K
    MinuteKline(ctx context.Context, code string, tp string, freq string, opts ...Option) ([]Bar, error)
    // 今日分时 (盘中)
    TodayMinute(ctx context.Context, code string, tp string) ([]Tick, error)
    // 个股实时报价 (盘中)
    RealTimeQuote(ctx context.Context, codes ...string) ([]Quote, error)
    // 基础信息
    StockList(ctx context.Context) ([]Stock, error)
    ConceptList(ctx context.Context) ([]Concept, error)
    ConceptConstituents(ctx context.Context, code string) ([]string, error)
    // 排名
    RankVolume(ctx context.Context, top int) ([]Quote, error)
    RankLimitUp(ctx context.Context) ([]Quote, error)
}
```

各数据源实现此接口，通过 `internal/fetch/selector.go` 按优先级自动选路 + fallback。

### 5.2 数据源实现

| 数据源 | 实现文件 | 方式 | 关键依赖 |
|--------|---------|------|---------|
| 通达信 | `internal/fetch/tdx.go` | TCP (injoyai/tdx) | `github.com/injoyai/tdx` |
| 东财 | `internal/fetch/eastmoney.go` | HTTP | requests (Go 标准库) |
| 腾讯 | `internal/fetch/tencent.go` | HTTP | requests |
| 同花顺 | `internal/fetch/ths.go` | HTTP | requests |

### 5.3 读路径缓存写入

查询触发 fetch 时，按规则决定是否写入 PG：

```
fetch 得到 []Bar / []Tick / []Quote
  → 返回给调用方 (CLI 输出)
  → 判断是否写入：
      盘中（daily/minute/rank）→ 不写（数据不完整）
      盘后              → goroutine: batch upsert → PG
      --force           → goroutine: batch upsert → PG
  → upsert 用 ON CONFLICT DO UPDATE，幂等安全
```

异步写入失败不影响本次返回结果。写入失败重试 3 次后丢弃并记日志，后续 `sync` 命令负责补全。

**写入规则的核心原则：只缓存完整数据。** 盘中实时数据持续变化，写入 PG 会导致盘后查询读到不完整快照。

### 5.4 同步命令 (sync)

`astock sync` 复用同一套 fetch 逻辑，写入是同步的（保证写完成才退出）：

```
# 单只
astock sync 600519 --days 30
astock sync 000001 --type index --days 30
astock sync BK0612 --type concept --today

# 全量（无 code 时 --type 默认为 all，即 stock+index+concept）
astock sync --type stock --today
astock sync --type concept --days 30
astock sync --today                          # = --type all --today
```

全市场并发同步时，goroutine 池大小限制为 10，避免被数据源封 IP。

---

## 六、Go 项目结构

```
astock/
├── cmd/
│   └── astock/
│       ├── main.go             # 入口
│       ├── daily.go            # astock daily
│       ├── minute.go           # astock minute
│       ├── rank.go             # astock rank
│       ├── info.go             # astock info
│       ├── sync.go             # astock sync
│       ├── stats.go            # astock stats
│       └── output.go           # table / JSON 输出
│
├── internal/
│   ├── model/
│   │   ├── bar.go              # Bar (K线统一结构)
│   │   ├── quote.go            # Quote (实时行情)
│   │   ├── stock.go            # Stock / Concept
│   │   └── enums.go            # Type / Freq 常量
│   │
│   ├── db/
│   │   ├── pg.go               # 连接池
│   │   ├── daily.go            # daily_k CRUD
│   │   ├── minute.go           # minute_k CRUD
│   │   ├── info.go             # stock_info / concept_info
│   │   └── migrate.go          # DDL 自动建表
│   │
│   ├── fetch/
│   │   ├── fetcher.go          # Fetcher 接口
│   │   ├── selector.go         # 按类型选源 + fallback
│   │   ├── tdx.go              # 通达信 (injoyai/tdx)
│   │   ├── eastmoney.go        # 东财
│   │   ├── tencent.go          # 腾讯
│   │   └── ths.go              # 同花顺 v6
│   │
│   └── query/
│       ├── router.go           # 查询路由 (PG/data source 决策)
│       └── cache.go            # 异步写入 PG
│
├── go.mod
├── go.sum
├── Makefile                    # build / test / lint
└── README.md
```

### 6.1 数据流说明

```
1. astock daily 000001

2. query.Router.Handle（查询层自动决策）
   → 是否 --force           → 是，跳过 PG，走数据源
   → 是否盘中 (09:30-15:00) → 是，直接走数据源
   → 盘后                  → 查 PG

3a. 盘后 + PG 有数据
   → 格式化输出 → 返回

3b. 盘后 + PG 无数据
   → 数据源 fetch（查询层自动选源 + fallback）
   → 返回结果 → 格式化输出
   → goroutine: db.Upsert(...)  // 异步写入 PG

3c. 盘中 / --force
   → 数据源 fetch
   → 返回结果 → 格式化输出
   → --force: goroutine 异步写 PG（用户主动刷新）
   → 盘中: 不写 PG（数据不完整，避免缓存脏数据）

4. CLI 输出 table / JSON
```

---

## 七、配置

```go
// config.go (或环境变量)
type Config struct {
    DBHost     string `env:"ASTOCK_DB_HOST"     default:"localhost"`
    DBPort     int    `env:"ASTOCK_DB_PORT"     default:"5432"`
    DBName     string `env:"ASTOCK_DB_NAME"     default:"astock"`
    DBUser     string `env:"ASTOCK_DB_USER"     default:"postgres"`
    DBPassword string `env:"ASTOCK_DB_PASS"     default:"password"`

    RetentionDays int    `env:"ASTOCK_RETENTION_DAYS" default:"30"`
    LogLevel      string `env:"ASTOCK_LOG_LEVEL"      default:"info"`
}
```

配置通过环境变量或 `.env` 文件，无配置文件依赖。

---

## 八、开发计划

| Phase | 内容 | 交付物 |
|-------|------|--------|
| **1 项目骨架** | go mod init、模型定义、PG 建表 | `astock version` 可用 |
| **2 东财采集** | EastmoneyClient(日K/分时/列表) + db 写入 | `astock daily --force` |
| **3 通达信采集** | injoyai/tdx 集成 + 分钟K | `astock minute` |
| **4 查询路由** | PG 优先读 + --force + 异步写 | read-through 闭环 |
| **5 sync 命令** | 批量同步 + --today + --days | `astock sync --today` |
| **6 输出美化** | table 格式 + JSON 格式 + 颜色 | 输出定型 |
| **7 rank + 信息** | rank / info / stats 命令 | 全命令可用 |
| **8 打磨** | 错误处理、重试、文档、Makefile | 发布 |

---

## 九、设计决策记录

| 决策 | 选择 | 依据 |
|------|------|------|
| 语言 | Go | 单二进制、类型安全、AI 调用零依赖 |
| 实时数据策略 | 查询层自动决策，命令不感知底层数据源 | CLI 命令和 PG 数据层解耦 |
| 历史数据策略 | PG 缓存 + 按需填充 | 冷启动友好，访问频率高的自动缓存 |
| 异步写 | goroutine + upsert | 不阻塞返回，幂等安全 |
| 数据源选路 | 主源 + fallback | 一个挂了自动切，不中断服务 |
| 分钟K | 仅通达信可取全历史 | 东财/同花顺 HTTP 不提供历史分钟 |
| 配置 | 环境变量 | 零配置文件，适合容器化 |
