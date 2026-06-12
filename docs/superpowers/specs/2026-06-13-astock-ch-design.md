# astock — A 股量化数据 CLI 平台设计（ClickHouse 版）

> 本设计文档替代 `2026-05-24-astock-design.md`（旧 PostgreSQL 方案）。
> 落地实施计划见 `../plans/2026-06-13-astock-ch-implementation.md`。

## 一、第一性原理推导

**目标**：一个 Go CLI，通过命令获取各种 A 股数据，本地数据库优先以保证量化分析速度，实时数据直连 API。

从这个目标拆出三个最小必要能力：
1. **数据落库**（sync）：把 TDX 的数据按需/批量灌进本地仓库
2. **历史查询**（query）：从本地仓库快速取出 K 线、元数据、板块成分
3. **实时直取**（live）：盘中报价/分时/今日分钟，绕过仓库直连 TDX

由此推导出三个层次：
- **存储层**：列式仓库（ClickHouse）—— 量化场景压倒性最优
- **采集层**：TDX 客户端封装（基于已有 `injoyai/tdx` v0.0.79）
- **CLI 层**：sync / query / live 三组命令

不需要的东西被砍掉：
- ❌ PostgreSQL（行存对宽表扫描慢 5–10 倍）
- ❌ 东财/腾讯/同花顺/百度/新浪 fallback（TDX 已覆盖 99% 场景，多源徒增维护）
- ❌ 复杂的 query.Router 自动决策（明确分 query/live 命令更直观）
- ❌ 沉重的 ORM（用 `clickhouse-go` 原生即可）

---

## 二、为什么是 ClickHouse

| 维度 | PostgreSQL | ClickHouse | 量化场景影响 |
|------|------------|------------|--------------|
| 存储模型 | 行存 | 列存 | 只读 close 列时 CH 只扫一列 |
| 压缩比 | 1× | 5–10× | 1000 万行日 K：PG ≈ 2 GB / CH ≈ 200 MB |
| 全市场 30 天扫描 | 1–3 s | < 100 ms | 量化筛选实时反馈 |
| 计算所有股票 MA20 | 5–10 s | < 500 ms | 因子计算速度 10× |
| 时序分区 | 需手动 | MergeTree 内建 | 滚动清理零成本 |
| 写入吞吐 | 5 万行/s | 50 万行/s | 历史回填速度 10× |
| 工具生态 | 通用 OLTP | 专为 OLAP / 时序设计 | 与 quant 工作流契合 |

**唯一代价**：CH 不擅长高频小事务、不支持外键约束。但本场景没有事务需求（行情数据天然 append-only），完美匹配。

---

## 三、目标架构

```
┌────────────────────────────────────────────────┐
│              astock CLI (Go 单二进制)           │
├────────────────────────────────────────────────┤
│  sync  │  query  │  live  │  init  │  stats   │
└────┬─────────┬──────────┬───────┬──────┬───────┘
     │         │          │       │      │
     ▼         ▼          ▼       │      ▼
┌─────────────────────┐  ┌─────────────────────┐
│   internal/dwh      │  │   internal/tdx       │
│   ClickHouse 仓库    │  │   TDX 客户端封装      │
│   (clickhouse-go)   │  │   (injoyai/tdx)      │
└──────────┬──────────┘  └──────────┬──────────┘
           │                         │
           ▼                         ▼
   ┌──────────────┐           ┌──────────────┐
   │  ClickHouse  │           │ 通达信行情服务器│
   │  (Docker)    │           │ TCP 7709     │
   └──────────────┘           └──────────────┘

数据流：
  sync  : TDX → 内存批 → ClickHouse (insert)
  query : ClickHouse → CLI 输出
  live  : TDX → CLI 输出（不落库）
```

---

## 四、ClickHouse 表设计

数据库 `astock`，全部使用 MergeTree 系族引擎。

### 4.1 元数据表（变更频率低，用 ReplacingMergeTree）

#### `securities` — 标的身份证表

所有可交易标的（股票/指数/ETF/可转债）共用此表。

```sql
CREATE TABLE securities (
    code        String,           -- 6 位代码
    market      LowCardinality(String),  -- sh/sz/bj
    type        LowCardinality(String),  -- stock/index/etf/bond
    name        String,
    list_date   Date,
    delist_date Nullable(Date),
    industry    LowCardinality(String) DEFAULT '',  -- F10：申万二级行业
    sector      LowCardinality(String) DEFAULT '',  -- F10：申万一级行业
    province    LowCardinality(String) DEFAULT '',  -- F10：注册地
    business    String DEFAULT '',                  -- F10：主营业务简述
    updated_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (type, market, code);
```

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `code` | String | 6 位代码（不带市场前缀） | `600519`、`000001`、`399001` |
| `market` | LowCardinality(String) | 交易所 | `sh` / `sz` / `bj` |
| `type` | LowCardinality(String) | 标的类型 | `stock` / `index` / `etf` / `bond` |
| `name` | String | 中文名称 | `贵州茅台`、`上证指数` |
| `list_date` | Date | 上市日期 | `2001-08-27` |
| `delist_date` | Nullable(Date) | 退市日期，未退市为 NULL | `NULL` 或 `2024-05-20` |
| `industry` | LowCardinality(String) | F10：申万二级行业 | `白酒` |
| `sector` | LowCardinality(String) | F10：申万一级行业 | `食品饮料` |
| `province` | LowCardinality(String) | F10：注册地 | `贵州` |
| `business` | String | F10：主营业务简述 | `高端白酒生产与销售` |
| `updated_at` | DateTime | 行版本时间 | `2026-06-13 10:30:00` |

排序键 `(type, market, code)`：典型查询先按类型+市场过滤再定位 code，能走主键扫描。

#### `blocks` — 板块/概念表

TDX 提供的所有板块（概念/地域/风格/指数板）。

```sql
CREATE TABLE blocks (
    code        String,
    name        String,
    type        LowCardinality(String),
    stock_count UInt32,
    updated_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (type, code);
```

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `code` | String | TDX 板块代码 | `880472`（白酒概念） |
| `name` | String | 板块名称 | `白酒概念`、`半导体` |
| `type` | LowCardinality(String) | 板块类型 | `concept`/`region`/`style`/`index` |
| `stock_count` | UInt32 | 成分股数量 | `87` |
| `updated_at` | DateTime | 行版本时间 | 同上 |

#### `block_constituents` — 板块成分股关系

多对多：一只股票可属多个板块。

```sql
CREATE TABLE block_constituents (
    block_code  String,
    stock_code  String,
    updated_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (block_code, stock_code);
```

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `block_code` | String | 板块代码（逻辑外键 → `blocks.code`） | `880472` |
| `stock_code` | String | 股票代码（逻辑外键 → `securities.code`） | `600519` |
| `updated_at` | DateTime | 行版本时间 | — |

注：CH 不支持物理外键约束，关系由应用层保证。

#### `trade_cal` — 交易日历

判断交易日，用于增量同步与跳过休市日。

```sql
CREATE TABLE trade_cal (
    trade_date Date,
    is_open    UInt8
) ENGINE = ReplacingMergeTree
ORDER BY trade_date;
```

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `trade_date` | Date | 日期 | `2026-06-13` |
| `is_open` | UInt8 | 是否开市 | `1` 开市 / `0` 休市 |

### 4.2 公司行为与基本面表

#### `xdxr` — 除权除息（复权计算基础）

**为什么必需**：TDX 返回的 K 线是**不复权原始价**，复权需客户端自算。没有 XDXR，送股/分红日会出现虚假“暴跌”（茂台 2006-05-15 送股后不复权看却 “暴跌 47%”），所有技术指标会全部失效。

```sql
CREATE TABLE xdxr (
    code         String,
    ex_date      Date,                        -- 除权除息日
    type         LowCardinality(String),      -- dividend/split/rights
    bonus        Float32 DEFAULT 0,           -- 送股（每 10 股送）
    transfer     Float32 DEFAULT 0,           -- 转增（每 10 股转）
    dividend     Float32 DEFAULT 0,           -- 派息（每 10 股元）
    rights_price Float32 DEFAULT 0,           -- 配股价
    rights_ratio Float32 DEFAULT 0,           -- 配股比例
    updated_at   DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (code, ex_date, type);
```

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `code` | String | 股票代码 | `600519` |
| `ex_date` | Date | 除权除息日 | `2006-05-15` |
| `type` | LowCardinality(String) | 事件类型 | `dividend`（分红）/`split`（送转）/`rights`（配股） |
| `bonus` | Float32 | 每 10 股送股数 | `10` |
| `transfer` | Float32 | 每 10 股转增数 | `10` |
| `dividend` | Float32 | 每 10 股派息（元） | `2.62` |
| `rights_price` | Float32 | 配股价（元） | `0` |
| `rights_ratio` | Float32 | 配股比例 | `0` |

**复权策略**：kline_daily 只存原始不复权价；query 命令在查询时通过 SQL JOIN xdxr 表即时计算前复权/后复权，CH 的 `arrayCumProd` 函数可一行完成。

#### `finance` — 财务数据

存储营收、净利、ROE、总股本/流通股本等基础面数据。流通股本是计算 `kline_daily.turnover`（换手率）与总市值的源泪。

```sql
CREATE TABLE finance (
    code              String,
    report_date       Date,                  -- 报告期（季末）
    revenue           Float64 DEFAULT 0,     -- 营收（元）
    net_profit        Float64 DEFAULT 0,     -- 净利润（元）
    eps               Float32 DEFAULT 0,     -- 每股收益
    bps               Float32 DEFAULT 0,     -- 每股净资产
    roe               Float32 DEFAULT 0,     -- 净资产收益率 %
    total_share       UInt64 DEFAULT 0,      -- 总股本（股）
    float_share       UInt64 DEFAULT 0,      -- 流通股本（股）
    total_assets      Float64 DEFAULT 0,     -- 总资产 
    total_liability   Float64 DEFAULT 0,     -- 总负债
    updated_at        DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (code, report_date);
```

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `code` | String | 股票代码 | `600519` |
| `report_date` | Date | 报告期（季末） | `2026-03-31` |
| `revenue` | Float64 | 营业收入（元） | `5.15e10` |
| `net_profit` | Float64 | 净利润（元） | `2.69e10` |
| `eps` | Float32 | 每股收益 | `21.40` |
| `bps` | Float32 | 每股净资产 | `170.30` |
| `roe` | Float32 | 净资产收益率 % | `12.58` |
| `total_share` | UInt64 | 总股本（股） | `1256197800` |
| `float_share` | UInt64 | 流通股本（股） | `1256197800` |
| `total_assets` | Float64 | 总资产（元） | `2.85e11` |
| `total_liability` | Float64 | 总负债（元） | `4.40e10` |

同步频率：财报起动月份局部同步即可（每季报完后 1–2 个月），日常不需同步。

### 4.3 行情表（写入量大，按时间分区）

#### `kline_daily` — 日 K 线（核心大表）

股票/指数/板块的每日开高低收，量化分析主战场。

```sql
CREATE TABLE kline_daily (
    code        String,
    type        LowCardinality(String),
    trade_date  Date,
    open        Float64,
    high        Float64,
    low         Float64,
    close       Float64,
    pre_close   Float64,
    volume      UInt64,
    amount      Float64,
    turnover    Float32,
    change_pct  Float32 MATERIALIZED if(pre_close > 0, (close - pre_close) / pre_close * 100, 0)
) ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(trade_date)
ORDER BY (type, code, trade_date);
```

| 字段 | 类型 | 含义 | 单位/示例 |
|------|------|------|-----------|
| `code` | String | 标的代码 | `600519` |
| `type` | LowCardinality(String) | 标的类型 | `stock` / `index` / `block` |
| `trade_date` | Date | 交易日期 | `2026-06-13` |
| `open` | Float64 | 开盘价（9:30 第一笔） | 元，`1812.50` |
| `high` | Float64 | 当日最高价 | 元，`1825.00` |
| `low` | Float64 | 当日最低价 | 元，`1808.20` |
| `close` | Float64 | 收盘价（15:00 最后一笔） | 元，`1820.30` |
| `pre_close` | Float64 | 昨收价（用于算涨跌幅） | 元 |
| `volume` | UInt64 | 成交量（成交股数） | 股，`3210000` |
| `amount` | Float64 | 成交额（成交总金额） | 元，`5.82e9` |
| `turnover` | Float32 | 换手率 = 成交量/流通股本 | %，`1.52` |
| `change_pct` | Float32 (MATERIALIZED) | 涨跌幅%，公式自动计算，不占存储 | %，`+0.35` |

类型选择要点：
- `volume` 用 UInt64：大盘股日成交可能上亿股，UInt32（上限 42 亿）会溢出风险。
- `amount` 用 Float64：金额跨度大、有小数，整型不合适。
- `turnover/change_pct` 用 Float32：百分比 2 位小数足够，省一半存储。
- `MATERIALIZED`：物化字段，写入时不占存储，查询时按公式即时计算。

#### `kline_minute` — 分钟 K 线

多周期共表，靠 `freq` 字段区分。

```sql
CREATE TABLE kline_minute (
    code      String,
    type      LowCardinality(String),
    freq      LowCardinality(String),
    dt        DateTime,
    open      Float64,
    high      Float64,
    low       Float64,
    close     Float64,
    volume    UInt64,
    amount    Float64
) ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(dt)
ORDER BY (type, code, freq, dt);
```

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `code` | String | 标的代码 | `600519` |
| `type` | LowCardinality(String) | 标的类型 | `stock` / `index` / `block` |
| `freq` | LowCardinality(String) | K 线周期 | `1m` / `5m` / `15m` / `30m` / `60m` |
| `dt` | DateTime | K 线起始时间（精确到分钟） | `2026-06-13 09:31:00` |
| `open/high/low/close` | Float64 | 该分钟的开高低收 | 同日 K 含义，时间粒度为分钟 |
| `volume` | UInt64 | 该分钟成交量 | 股 |
| `amount` | Float64 | 该分钟成交额 | 元 |

说明：
- 不含 `pre_close`/`turnover`：分钟级无意义，仅日维度需要。
- 多周期共表的好处：避免 `kline_1m`/`kline_5m` 多表维护，查询用 `WHERE freq='1m'` 即可。
- 30 天分钟 K 全市场约 4000 万行，按月分区可独立删除老数据。

### 4.4 同步状态表

#### `sync_log` — 同步任务记录

每次执行 `astock sync ...` 都写一条；用于排查失败、断点续传、看进度。

```sql
CREATE TABLE sync_log (
    task        String,
    target      String,
    start_at    DateTime,
    end_at      Nullable(DateTime),
    rows        UInt64,
    status      LowCardinality(String),
    err_msg     String DEFAULT ''
) ENGINE = MergeTree
ORDER BY (task, start_at);
```

| 字段 | 类型 | 含义 | 示例 |
|------|------|------|------|
| `task` | String | 任务类型 | `meta` / `info` / `daily` / `minute` / `block` / `xdxr` / `finance` |
| `target` | String | 同步目标 | `all`（全市场） / `600519`（单只） / `880472`（单板块） |
| `start_at` | DateTime | 开始时间 | `2026-06-13 18:00:00` |
| `end_at` | Nullable(DateTime) | 结束时间，进行中为 NULL | `NULL` 或实际时间 |
| `rows` | UInt64 | 写入行数 | `5234` |
| `status` | LowCardinality(String) | 任务状态 | `running` / `success` / `failed` |
| `err_msg` | String | 失败错误信息 | `connection refused` |

注：与元数据表不同，此表用普通 `MergeTree`，要保留全部历史日志，不去重。

---

### 4.5 设计要点速查

- **`ReplacingMergeTree`**：保证幂等，重复 sync 不产生重复行（按 ORDER BY 主键去重）。
- **按月分区**：滚动清理只需 `ALTER TABLE ... DROP PARTITION`，毫秒完成。
- **`LowCardinality(String)`**：枚举类字段（market/type/freq/status）字典编码，压缩约 10×。
- **`MATERIALIZED`**：物化派生字段，查询时按公式即时算出，零存储成本。
- **`Nullable(T)`**：成本是每行多 1 字节 NULL 标记，仅在确实可能为空时才用（如 delist_date、end_at）。

### 4.6 CH 数据类型选择速查

| 类型 | 占用 | 用途 |
|------|------|------|
| `LowCardinality(String)` | 字典编码后约 1–2 字节 | 枚举值少（< 几千个）的字符串 |
| `Float64` | 8 字节 | 价格、成交额（高精度浮点） |
| `Float32` | 4 字节 | 百分比类（精度要求不高） |
| `UInt64` | 8 字节 | 成交量、行数（大数值） |
| `UInt32` | 4 字节 | 中等数值（板块成分股数等） |
| `UInt8` | 1 字节 | 布尔/小枚举（0/1） |
| `Date` | 2 字节 | 日期 |
| `DateTime` | 4 字节 | 秒级时间戳 |
| `Nullable(T)` | 类型字节 + 1 字节 | 允许空值的字段 |

---

## 五、CLI 命令设计

```
astock
├── init                              初始化 CH 表结构（首次部署）
│
├── sync                              数据同步（TDX → CH）
│   ├── meta                          股票/指数/板块列表 + 交易日历
│   ├── info                          F10 公司信息（行业/主营）→ securities 扩展字段
│   ├── daily   --code a,b,c|--all [--count 800]
│   ├── minute  --code a,b,c [--freq 5m] [--count 800]
│   ├── block                         板块成分股
│   ├── xdxr    --code a,b,c|--all    除权除息（复权基础）
│   ├── finance --code a,b,c|--all    财务数据（每季跑一次）
│   └── all     --code a,b,c [--count 800] [--freq 5m]   对每只执行 daily+minute+xdxr
│
├── query                             本地仓库查询
│   ├── daily   <code> [--from] [--to] [--limit 30] [--adjust qfq|none]
│   ├── minute  <code> [--freq 1m|5m|15m|30m|60m] [--date YYYYMMDD] [--limit 240]
│   ├── count   <table>                              查表行数
│   ├── stock   [--type stock|index|etf] [--market sh|sz|bj] [--industry 白酒] [--keyword 茅台]
│   ├── block   list [--keyword 光通信]               列出概念/行业板块
│   │           members <block_code>                  查某板块成分股
│   ├── finance <code>                                查询财务数据
│   └── xdxr    <code>                                查询除权除息记录
│
├── live                              实时直连 TDX（不落库）
│   ├── quote   <code...>                              实时报价 + 五档盘口
│   ├── tick    <code> [--date YYYYMMDD]               分笔成交（今日或历史）
│   └── minute  <code> [--freq 1m]                     今日 N 分钟
│
├── stats                             仓库统计（行数/磁盘/最新日期）
└── status                            最近同步任务状态

全局选项：--json | --table（默认）| --csv
```

**用法示例：**
```bash
astock init                                 # 一次性
astock sync meta                            # 同步全市场元数据
astock sync daily --all --from 20200101     # 全市场日K回填
astock sync daily --code 600519 --from 20100101  # 单只全历史
astock sync all --days 1                    # 每日增量（cron 用）

astock query daily 600519 --limit 30        # 默认 table 输出
astock query daily 600519 --adjust qfq      # 前复权日K（查询时实时计算）
astock query daily 600519 --json            # AI 友好
astock query stock --industry 白酒          # 按行业筛选
astock live quote 600519 000001 399001      # 多个标的实时报价（含五档盘口）
astock live tick 600519 --date 20240320     # 历史某日分笔（直连 TDX 不落库）
```

---

## 六、Go 项目结构（完全重写）

```
astock/
├── cmd/astock/
│   ├── main.go                 cobra 入口
│   ├── init.go                 astock init
│   ├── sync_*.go               sync meta/daily/minute/block/all
│   ├── query_*.go              query daily/minute/stock/block
│   ├── live_*.go               live quote/tick/minute
│   ├── stats.go
│   └── status.go
│
├── internal/
│   ├── config/                 .env / 环境变量
│   ├── model/                  Bar / Quote / Stock / Block (POGO)
│   ├── tdx/                    injoyai/tdx 封装
│   │   ├── client.go           连接管理（lazy + reconnect）
│   │   ├── meta.go             股票列表/指数/板块
│   │   ├── kline.go            日K/分钟K（含 indexCode bug 修复）
│   │   ├── live.go             实时报价/分时
│   │   └── block.go            GetBlockData / GetBlockDataWithIndex
│   ├── dwh/                    ClickHouse 数据仓库
│   │   ├── conn.go             clickhouse-go 连接池
│   │   ├── schema.go           DDL（init 命令使用）
│   │   ├── securities.go       元数据 + F10 CRUD
│   │   ├── kline.go            kline_daily / kline_minute 批量写入与复权查询
│   │   ├── xdxr.go             除权除息 CRUD
│   │   ├── finance.go          财务数据 CRUD
│   │   ├── blocks.go
│   │   └── stats.go            行数/分区/磁盘统计
│   └── output/                 table / json / csv 渲染
│
├── docker-compose.yml          ClickHouse 单机
├── Makefile
├── go.mod
└── README.md
```

**docker-compose.yml**：
```yaml
services:
  clickhouse:
    image: clickhouse/clickhouse-server:24.8
    ports: ["8123:8123", "9000:9000"]
    volumes:
      - ./data/clickhouse:/var/lib/clickhouse
    ulimits:
      nofile: { soft: 262144, hard: 262144 }
```

---

## 七、关键技术决策

| 决策 | 选择 | 依据 |
|------|------|------|
| 数据库 | ClickHouse 24.8 | 列存压缩 + OLAP 查询，量化场景最优 |
| 部署 | Docker 单机 | 启停干净，data 目录挂本机 |
| 数据源 | 仅 TDX | 免费免限流，覆盖 99% 需求，简化代码 |
| TDX 库 | injoyai/tdx v0.0.79 | 已踩坑过，含板块支持 |
| CH 驱动 | clickhouse-go/v2 | 官方维护，原生协议（端口 9000） |
| CLI 框架 | spf13/cobra | Go CLI 事实标准 |
| 配置 | .env + envconfig | 零配置文件 |
| 命令分层 | sync / query / live | 分而治之，调用者无歧义（不再"自动决策"） |
| 写入幂等 | ReplacingMergeTree | 重复 sync 不污染 |
| 历史保留 | 行情按月分区，可永久保留；CH 上 10 年 1300 万行 < 200 MB | 不再做 30 天滚动清理 |
| 元数据更新 | ReplacingMergeTree(updated_at) | OPTIMIZE TABLE 自动收敛最新版本 |

---

## 八、风险与备注

1. **TDX 历史日K 上限**：每次请求 800 根，全历史需多次滑窗，T6 任务需要妥善处理分页与去重（ReplacingMergeTree 兜底）。
2. **TDX 服务器并发**：经验上 10 并发安全，更高可能触发限流。T7 的 goroutine 池上限设 10。
3. **ClickHouse 时区**：使用 `DateTime` 默认 UTC，建议在 `clickhouse-server/config.xml` 配 `Asia/Shanghai`，或写入时显式时区。
4. **数据范围**：DDL 和 sync 命令支持任意时间范围，初次只回填近期数据（如 1 年），后续按需扩展，无需修改架构。
5. **盘中查询行为**：`query daily` 不返回今日不完整数据；今日数据请走 `live` 命令，避免缓存脏数据。
6. **分笔数据不落库**：分笔成交数据量极大（茂台单日几万笔，全市场单日约 10 亿笔），且使用频率低。采用「live 命令直连 TDX」方式，不进入 sync 不落库，避免仓库肨胀。
7. **复权计算**：kline_daily 只存原始价；复权查询通过 SQL `JOIN xdxr` 在查询时计算。供 `--adjust qfq|hfq|raw` 参数选择。
8. **五档盘口**：包含在 TDX `get_security_quotes` 返回中，`live quote` 命令直接展开输出（bid1–bid5/ask1–ask5），不落库。
9. **财务同步频率**：中报/三季报/年报公布后的月份跑一次即可，不进入每日 `sync all`。
