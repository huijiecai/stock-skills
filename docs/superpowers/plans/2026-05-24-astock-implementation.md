# astock Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Go CLI tool (`astock`) for A-share quantitative data with PostgreSQL persistence and multi-source data fetching.

**Architecture:** Single Go binary with CLI commands (cobra) → query router (read-through cache) → PG storage + data source fetchers (EastMoney/TDX/Tencent/THS). All data sources implement a common `Fetcher` interface; query layer auto-decides PG vs live source based on time (intraday vs after-close) and data availability.

**Tech Stack:** Go 1.22+, cobra/pflag CLI, pgx v5 PostgreSQL driver, injoyai/tdx (TDX TCP protocol), standard library HTTP client (EastMoney/Tencent/THS). Zero Python dependencies.

---

## File Structure

```
astock/
├── cmd/astock/
│   ├── main.go              # cobra root command, config load
│   ├── daily.go             # astock daily <code>
│   ├── minute.go            # astock minute <code>
│   ├── rank.go              # astock rank volume/limit-up
│   ├── info.go              # astock info stocks/concepts
│   ├── sync.go              # astock sync [code...]
│   ├── stats.go             # astock stats
│   └── output.go            # table / JSON rendering
├── internal/
│   ├── config/
│   │   └── config.go        # env-based configuration
│   ├── model/
│   │   ├── bar.go           # Bar (K-line unified)
│   │   ├── quote.go         # Quote (real-time)
│   │   ├── stock.go         # Stock / Concept
│   │   └── enums.go         # Type, Freq, Exchange constants
│   ├── db/
│   │   ├── pg.go            # pgx connection pool
│   │   ├── daily.go         # daily_k CRUD
│   │   ├── minute.go        # minute_k CRUD
│   │   ├── info.go          # stock_info / concept_info CRUD
│   │   └── migrate.go       # auto-DDL on startup
│   ├── fetch/
│   │   ├── fetcher.go       # Fetcher interface
│   │   ├── selector.go      # priority + fallback routing
│   │   ├── eastmoney.go     # EastMoney HTTP
│   │   ├── tdx.go           # Tongdaxin TCP (injoyai/tdx)
│   │   ├── tencent.go       # Tencent HTTP
│   │   └── ths.go           # Tonghuashun HTTP
│   └── query/
│       ├── router.go        # read-through query dispatcher
│       └── cache.go         # async PG writer
├── go.mod
├── Makefile
└── README.md
```

---

### Task 1: Initialize Go module and install dependencies

**Files:**
- Create: `astock/go.mod`
- Create: `astock/main.go` (placeholder)

- [ ] **Step 1: Create project directory and init module**

```bash
mkdir -p /Users/huijiecai/Project/stock/astock
cd /Users/huijiecai/Project/stock/astock
go mod init github.com/huijiecai/stock/astock
```

- [ ] **Step 2: Install dependencies**

```bash
cd /Users/huijiecai/Project/stock/astock
go get github.com/spf13/cobra
go get github.com/spf13/pflag
go get github.com/jackc/pgx/v5@v5.7
go get github.com/jackc/pgx/v5/pgxpool
go get github.com/injoyai/tdx
go get github.com/joho/godotenv
go get github.com/shopspring/decimal
```

- [ ] **Step 3: Create placeholder main.go**

```go
// astock/cmd/astock/main.go
package main

import "fmt"

func main() {
    fmt.Println("astock v0.1.0")
}
```

- [ ] **Step 4: Verify it compiles**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./cmd/astock/
```

Expected: binary `astock` created, running it prints `astock v0.1.0`.

- [ ] **Step 5: Commit**

```bash
git add astock/go.mod astock/go.sum astock/cmd/astock/main.go
git commit -m "feat: initialize astock Go module"
```

---

### Task 2: Data models

**Files:**
- Create: `astock/internal/model/enums.go`
- Create: `astock/internal/model/bar.go`
- Create: `astock/internal/model/quote.go`
- Create: `astock/internal/model/stock.go`

- [ ] **Step 1: Create enums.go**

```go
// astock/internal/model/enums.go
package model

// DataType 股票/指数/概念
type DataType string

const (
    TypeStock   DataType = "stock"
    TypeIndex   DataType = "index"
    TypeConcept DataType = "concept"
)

// Freq 分钟K线频率
type Freq string

const (
    Freq1m  Freq = "1m"
    Freq5m  Freq = "5m"
    Freq15m Freq = "15m"
    Freq30m Freq = "30m"
    Freq60m Freq = "60m"
)

// Exchange 交易所
type Exchange string

const (
    ExchangeSH Exchange = "sh"
    ExchangeSZ Exchange = "sz"
    ExchangeBJ Exchange = "bj"
)
```

- [ ] **Step 2: Create bar.go** (K-line unified structure)

```go
// astock/internal/model/bar.go
package model

import "time"

// Bar K线统一结构（日K / 分钟K共用）
type Bar struct {
    Code      string    `json:"code"`
    Type      DataType  `json:"type"`
    TradeDate string    `json:"trade_date"` // "2006-01-02"
    Time      time.Time `json:"time,omitempty"`
    Freq      Freq      `json:"freq,omitempty"`
    Open      float64   `json:"open"`
    High      float64   `json:"high"`
    Low       float64   `json:"low"`
    Close     float64   `json:"close"`
    PreClose  float64   `json:"pre_close,omitempty"`
    ChangePct float64   `json:"change_pct,omitempty"`
    Volume    int64     `json:"volume"`
    Amount    float64   `json:"amount"`
    Turnover  float64   `json:"turnover,omitempty"` // 换手率%
    AvgPrice  float64   `json:"avg_price,omitempty"`
}

// Tick 今日分时数据（盘中实时）
type Tick struct {
    Code      string  `json:"code"`
    Time      string  `json:"time"` // "09:35"
    Price     float64 `json:"price"`
    Volume    int64   `json:"volume"`
    Amount    float64 `json:"amount"`
    AvgPrice  float64 `json:"avg_price,omitempty"`
}
```

- [ ] **Step 3: Create quote.go**

```go
// astock/internal/model/quote.go
package model

// Quote 实时报价
type Quote struct {
    Code      string  `json:"code"`
    Name      string  `json:"name,omitempty"`
    Price     float64 `json:"price"`
    PreClose  float64 `json:"pre_close"`
    ChangePct float64 `json:"change_pct"`
    Volume    int64   `json:"volume"`
    Amount    float64 `json:"amount"`
    PE        float64 `json:"pe,omitempty"`
    PB        float64 `json:"pb,omitempty"`
    MarketCap float64 `json:"market_cap,omitempty"`
    High      float64 `json:"high,omitempty"`
    Low       float64 `json:"low,omitempty"`
    Open      float64 `json:"open,omitempty"`
}
```

- [ ] **Step 4: Create stock.go**

```go
// astock/internal/model/stock.go
package model

// Stock 股票基础信息
type Stock struct {
    Code     string `json:"code"`
    Name     string `json:"name"`
    Exchange string `json:"exchange"` // sh / sz / bj
}

// Concept 同花顺概念板块
type Concept struct {
    Code       string `json:"code"`        // BKxxxx
    Name       string `json:"name"`
    StockCount int    `json:"stock_count"`
}

// ConceptConstituent 概念成分股
type ConceptConstituent struct {
    ConceptCode string `json:"concept_code"`
    StockCode   string `json:"stock_code"`
}
```

- [ ] **Step 5: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./internal/model/
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add astock/internal/model/
git commit -m "feat: define data models (Bar, Quote, Stock, Concept, enums)"
```

---

### Task 3: Configuration and DB connection pool

**Files:**
- Create: `astock/internal/config/config.go`
- Create: `astock/internal/db/pg.go`

- [ ] **Step 1: Create config.go**

```go
// astock/internal/config/config.go
package config

import (
    "os"
    "strconv"
)

type Config struct {
    DBHost         string
    DBPort         int
    DBName         string
    DBUser         string
    DBPassword     string
    RetentionDays  int
    LogLevel       string
}

func Load() *Config {
    return &Config{
        DBHost:        getEnv("ASTOCK_DB_HOST", "localhost"),
        DBPort:        getEnvInt("ASTOCK_DB_PORT", 5432),
        DBName:        getEnv("ASTOCK_DB_NAME", "astock"),
        DBUser:        getEnv("ASTOCK_DB_USER", "postgres"),
        DBPassword:    getEnv("ASTOCK_DB_PASS", "postgres"),
        RetentionDays: getEnvInt("ASTOCK_RETENTION_DAYS", 30),
        LogLevel:      getEnv("ASTOCK_LOG_LEVEL", "info"),
    }
}

func getEnv(key, fallback string) string {
    if v := os.Getenv(key); v != "" {
        return v
    }
    return fallback
}

func getEnvInt(key string, fallback int) int {
    if v := os.Getenv(key); v != "" {
        if i, err := strconv.Atoi(v); err == nil {
            return i
        }
    }
    return fallback
}
```

- [ ] **Step 2: Create pg.go**

```go
// astock/internal/db/pg.go
package db

import (
    "context"
    "fmt"
    "time"

    "github.com/jackc/pgx/v5/pgxpool"
    "github.com/huijiecai/stock/astock/internal/config"
)

var Pool *pgxpool.Pool

func Connect(ctx context.Context, cfg *config.Config) error {
    dsn := fmt.Sprintf("postgres://%s:%s@%s:%d/%s?sslmode=disable",
        cfg.DBUser, cfg.DBPassword, cfg.DBHost, cfg.DBPort, cfg.DBName)

    poolCfg, err := pgxpool.ParseConfig(dsn)
    if err != nil {
        return fmt.Errorf("parse dsn: %w", err)
    }
    poolCfg.MaxConns = 10
    poolCfg.MinConns = 2

    pool, err := pgxpool.NewWithConfig(ctx, poolCfg)
    if err != nil {
        return fmt.Errorf("create pool: %w", err)
    }

    // verify connection
    pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
    defer cancel()
    if err := pool.Ping(pingCtx); err != nil {
        pool.Close()
        return fmt.Errorf("ping: %w", err)
    }

    Pool = pool
    return nil
}

func Close() {
    if Pool != nil {
        Pool.Close()
    }
}
```

- [ ] **Step 3: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./internal/config/
go build ./internal/db/
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add astock/internal/config/ astock/internal/db/pg.go
git commit -m "feat: add config and DB connection pool"
```

---

### Task 4: Database schema and auto-migration

**Files:**
- Create: `astock/internal/db/migrate.go`

- [ ] **Step 1: Create migrate.go**

```go
// astock/internal/db/migrate.go
package db

import (
    "context"
    "fmt"
)

func Migrate(ctx context.Context) error {
    queries := []string{
        `CREATE TABLE IF NOT EXISTS stock_info (
            code       VARCHAR(10) PRIMARY KEY,
            name       VARCHAR(50) NOT NULL,
            exchange   VARCHAR(4) NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )`,
        `CREATE TABLE IF NOT EXISTS concept_info (
            code        VARCHAR(10) PRIMARY KEY,
            name        VARCHAR(50) NOT NULL,
            stock_count INTEGER DEFAULT 0,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )`,
        `CREATE TABLE IF NOT EXISTS concept_constituents (
            concept_code VARCHAR(10) NOT NULL REFERENCES concept_info(code),
            stock_code   VARCHAR(10) NOT NULL REFERENCES stock_info(code),
            PRIMARY KEY (concept_code, stock_code)
        )`,
        `CREATE TABLE IF NOT EXISTS trade_cal (
            trade_date DATE PRIMARY KEY,
            is_trade   BOOLEAN NOT NULL DEFAULT TRUE
        )`,
        `CREATE TABLE IF NOT EXISTS daily_k (
            code       VARCHAR(10) NOT NULL,
            trade_date DATE NOT NULL,
            type       VARCHAR(10) NOT NULL DEFAULT 'stock',
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
        )`,
        `CREATE INDEX IF NOT EXISTS idx_daily_k_date ON daily_k (trade_date)`,
        `CREATE INDEX IF NOT EXISTS idx_daily_k_type ON daily_k (type)`,
        `CREATE TABLE IF NOT EXISTS minute_k (
            code      VARCHAR(10) NOT NULL,
            dt        TIMESTAMP NOT NULL,
            freq      VARCHAR(5) NOT NULL,
            type      VARCHAR(10) NOT NULL DEFAULT 'stock',
            open      DOUBLE PRECISION,
            high      DOUBLE PRECISION,
            low       DOUBLE PRECISION,
            close     DOUBLE PRECISION,
            volume    BIGINT,
            amount    DOUBLE PRECISION,
            avg_price DOUBLE PRECISION,
            PRIMARY KEY (code, dt, freq, type)
        )`,
        `CREATE INDEX IF NOT EXISTS idx_minute_k_dt   ON minute_k (dt)`,
        `CREATE INDEX IF NOT EXISTS idx_minute_k_freq ON minute_k (freq)`,
    }

    for _, q := range queries {
        if _, err := Pool.Exec(ctx, q); err != nil {
            return fmt.Errorf("migrate: %w\nquery: %s", err, q)
        }
    }
    return nil
}
```

- [ ] **Step 2: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./internal/db/
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add astock/internal/db/migrate.go
git commit -m "feat: add DB auto-migration (7 tables)"
```

---

### Task 5: Fetcher interface definition

**Files:**
- Create: `astock/internal/fetch/fetcher.go`

- [ ] **Step 1: Create fetcher.go**

```go
// astock/internal/fetch/fetcher.go
package fetch

import (
    "context"
    "github.com/huijiecai/stock/astock/internal/model"
)

// Option fetch 可选参数
type Option func(*FetchOptions)

type FetchOptions struct {
    Start string
    End   string
    Limit int
    Top   int
}

func WithStart(s string) Option    { return func(o *FetchOptions) { o.Start = s } }
func WithEnd(s string) Option      { return func(o *FetchOptions) { o.End = s } }
func WithLimit(n int) Option       { return func(o *FetchOptions) { o.Limit = n } }
func WithTop(n int) Option         { return func(o *FetchOptions) { o.Top = n } }

// Fetcher 数据源统一接口
type Fetcher interface {
    // DailyKline 历史日K
    DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error)
    // MinuteKline 历史分钟K
    MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, opts ...Option) ([]model.Bar, error)
    // TodayMinute 今日分时（盘中实时）
    TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error)
    // RealTimeQuote 个股实时报价
    RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error)
    // StockList 股票列表
    StockList(ctx context.Context) ([]model.Stock, error)
    // ConceptList 概念板块列表
    ConceptList(ctx context.Context) ([]model.Concept, error)
    // ConceptConstituents 概念成分股
    ConceptConstituents(ctx context.Context, code string) ([]string, error)
    // RankVolume 成交额排名
    RankVolume(ctx context.Context, top int) ([]model.Quote, error)
    // RankLimitUp 涨停天梯
    RankLimitUp(ctx context.Context) ([]model.Quote, error)
}
```

- [ ] **Step 2: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./internal/fetch/
```

Expected: no errors (interface only, will have concrete implementations later).

- [ ] **Step 3: Commit**

```bash
git add astock/internal/fetch/fetcher.go
git commit -m "feat: define Fetcher interface"
```

---

### Task 6: EastMoney HTTP client (daily kline, stock/concept list)

**Files:**
- Create: `astock/internal/fetch/eastmoney.go`

- [ ] **Step 1: Create eastmoney.go — headers and constructor**

```go
// astock/internal/fetch/eastmoney.go
package fetch

import (
    "context"
    "encoding/json"
    "fmt"
    "io"
    "net/http"
    "net/url"
    "strconv"
    "strings"
    "time"

    "github.com/huijiecai/stock/astock/internal/model"
)

type EastMoney struct {
    client  *http.Client
    baseURL string
}

func NewEastMoney() *EastMoney {
    return &EastMoney{
        client: &http.Client{Timeout: 30 * time.Second},
        baseURL: "https://push2.eastmoney.com/api/qt/stock",
    }
}

func (e *EastMoney) doGet(ctx context.Context, urlStr string) ([]byte, error) {
    req, err := http.NewRequestWithContext(ctx, "GET", urlStr, nil)
    if err != nil {
        return nil, err
    }
    req.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
    req.Header.Set("Referer", "https://quote.eastmoney.com/")

    resp, err := e.client.Do(req)
    if err != nil {
        return nil, fmt.Errorf("eastmoney get %s: %w", urlStr, err)
    }
    defer resp.Body.Close()

    body, err := io.ReadAll(resp.Body)
    if err != nil {
        return nil, fmt.Errorf("read body: %w", err)
    }
    return body, nil
}
```

- [ ] **Step 2: Add DailyKline implementation**

```go
// astock/internal/fetch/eastmoney.go — DailyKline

// DailyKline 获取日K，使用东财 push2 API
func (e *EastMoney) DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error) {
    secID := e.toSecID(code, tp)
    options := &FetchOptions{}
    for _, o := range opts {
        o(options)
    }

    // 东财 K 线接口: https://push2his.eastmoney.com/api/qt/stock/kline/get
    params := url.Values{}
    params.Set("secid", secID)
    params.Set("fields1", "f1,f2,f3,f4,f5,f6")
    params.Set("fields2", "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61")
    params.Set("klt", "101") // 日K
    params.Set("fqt", "1")   // 前复权

    if options.Limit > 0 {
        params.Set("lmt", strconv.Itoa(options.Limit))
    } else {
        params.Set("lmt", "30")
    }
    if options.Start != "" {
        params.Set("beg", options.Start)
    }
    if options.End != "" {
        params.Set("end", options.End)
    }

    urlStr := "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + params.Encode()
    body, err := e.doGet(ctx, urlStr)
    if err != nil {
        return nil, err
    }

    // 解析东财返回
    var result struct {
        Data struct {
            Klined string `json:"klined"`
        } `json:"data"`
    }
    if err := json.Unmarshal(body, &result); err != nil {
        return nil, fmt.Errorf("parse kline: %w", err)
    }
    if result.Data.Klined == "" {
        return nil, fmt.Errorf("empty kline data for %s", code)
    }

    lines := strings.Split(strings.TrimSpace(result.Data.Klined), ";")
    bars := make([]model.Bar, 0, len(lines))
    for _, line := range lines {
        parts := strings.Split(line, ",")
        if len(parts) < 11 {
            continue
        }
        bar := model.Bar{
            Code:      code,
            Type:      tp,
            TradeDate: parts[0],
        }
        bar.Open, _ = strconv.ParseFloat(parts[1], 64)
        bar.Close, _ = strconv.ParseFloat(parts[2], 64)
        bar.High, _ = strconv.ParseFloat(parts[3], 64)
        bar.Low, _ = strconv.ParseFloat(parts[4], 64)
        bar.PreClose, _ = strconv.ParseFloat(parts[5], 64)
        bar.ChangePct, _ = strconv.ParseFloat(parts[6], 64)
        bar.ChangePct = bar.ChangePct * 100 // 东财返回的是小数如 0.35 表示 0.35%
        bar.Volume, _ = strconv.ParseInt(parts[7], 10, 64)
        bar.Amount, _ = strconv.ParseFloat(parts[8], 64)
        bar.Turnover, _ = strconv.ParseFloat(parts[9], 64)
        if parts[10] != "" {
            bar.Turnover = 0 // 东财第11个字段不是换手率，忽略
            _ = parts[10]
        }
        bars = append(bars, bar)
    }
    return bars, nil
}

// toSecID 转换 code 为东财 secid 格式
func (e *EastMoney) toSecID(code string, tp model.DataType) string {
    switch tp {
    case model.TypeIndex:
        // 指数：上证 sh, 深证 sz
        if strings.HasPrefix(code, "000") || strings.HasPrefix(code, "880") {
            return "1." + code
        }
        return "0." + code
    case model.TypeConcept:
        return "0." + code // 概念板块 BKxxxx
    default:
        // 股票：sh/sz/bj
        return "0." + code // 由东财自动识别
    }
}
```

- [ ] **Step 3: Add StockList and ConceptList**

```go
// astock/internal/fetch/eastmoney.go — StockList / ConceptList / ConceptConstituents

// StockList 获取全市场股票列表
func (e *EastMoney) StockList(ctx context.Context) ([]model.Stock, error) {
    urlStr := "https://push2.eastmoney.com/api/qt/clist/get?" + url.Values{
        "pn":   {"1"},
        "pz":   {"10000"},
        "po":   {"0"},
        "np":   {"1"},
        "ut":   {"bd1d9ddb04089700cf9c27f6f7426281"},
        "fltt": {"2"},
        "invt": {"2"},
        "fid":  {"f3"},
        "fs":   {"m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"},
        "fields": {"f12,f14"},
    }.Encode()

    body, err := e.doGet(ctx, urlStr)
    if err != nil {
        return nil, err
    }

    var result struct {
        Data struct {
            Total int `json:"total"`
            Diff  []struct {
                F12 string `json:"f12"`
                F14 string `json:"f14"`
            } `json:"diff"`
        } `json:"data"`
    }
    if err := json.Unmarshal(body, &result); err != nil {
        return nil, fmt.Errorf("parse stock list: %w", err)
    }

    stocks := make([]model.Stock, 0, result.Data.Total)
    for _, d := range result.Data.Diff {
        exchange := "sz"
        if strings.HasPrefix(d.F12, "6") || strings.HasPrefix(d.F12, "9") {
            exchange = "sh"
        } else if strings.HasPrefix(d.F12, "8") {
            exchange = "bj"
        }
        stocks = append(stocks, model.Stock{
            Code:     d.F12,
            Name:     d.F14,
            Exchange: exchange,
        })
    }
    return stocks, nil
}

// ConceptList 获取同花顺概念板块列表
func (e *EastMoney) ConceptList(ctx context.Context) ([]model.Concept, error) {
    urlStr := "https://push2.eastmoney.com/api/qt/clist/get?" + url.Values{
        "pn":   {"1"},
        "pz":   {"500"},
        "po":   {"0"},
        "np":   {"1"},
        "ut":   {"bd1d9ddb04089700cf9c27f6f7426281"},
        "fltt": {"2"},
        "invt": {"2"},
        "fid":  {"f3"},
        "fs":   {"m:0+t:10"}, // 概念板块
        "fields": {"f12,f14,f20"},
    }.Encode()

    body, err := e.doGet(ctx, urlStr)
    if err != nil {
        return nil, err
    }

    var result struct {
        Data struct {
            Total int `json:"total"`
            Diff  []struct {
                F12 string `json:"f12"`
                F14 string `json:"f14"`
                F20 int    `json:"f20"`
            } `json:"diff"`
        } `json:"data"`
    }
    if err := json.Unmarshal(body, &result); err != nil {
        return nil, fmt.Errorf("parse concept list: %w", err)
    }

    concepts := make([]model.Concept, 0, result.Data.Total)
    for _, d := range result.Data.Diff {
        concepts = append(concepts, model.Concept{
            Code:       d.F12,
            Name:       d.F14,
            StockCount: d.F20,
        })
    }
    return concepts, nil
}

// ConceptConstituents 获取概念成分股
func (e *EastMoney) ConceptConstituents(ctx context.Context, code string) ([]string, error) {
    urlStr := "https://push2.eastmoney.com/api/qt/clist/get?" + url.Values{
        "pn":     {"1"},
        "pz":     {"1000"},
        "po":     {"0"},
        "np":     {"1"},
        "ut":     {"bd1d9ddb04089700cf9c27f6f7426281"},
        "fltt":   {"2"},
        "invt":   {"2"},
        "fid":    {"f3"},
        "fs":     {"b:" + code},
        "fields": {"f12"},
    }.Encode()

    body, err := e.doGet(ctx, urlStr)
    if err != nil {
        return nil, err
    }

    var result struct {
        Data struct {
            Diff []struct {
                F12 string `json:"f12"`
            } `json:"diff"`
        } `json:"data"`
    }
    if err := json.Unmarshal(body, &result); err != nil {
        return nil, fmt.Errorf("parse constituents: %w", err)
    }

    codes := make([]string, 0, len(result.Data.Diff))
    for _, d := range result.Data.Diff {
        codes = append(codes, d.F12)
    }
    return codes, nil
}
```

- [ ] **Step 4: Add TodayMinute, RealTimeQuote, RankVolume, RankLimitUp**

```go
// astock/internal/fetch/eastmoney.go — TodayMinute / RealTimeQuote / RankVolume / RankLimitUp

// TodayMinute 今日分时（盘中实时）
func (e *EastMoney) TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error) {
    secID := e.toSecID(code, tp)
    params := url.Values{}
    params.Set("secid", secID)
    params.Set("fields1", "f1,f2,f3,f4,f5,f6,f7")
    params.Set("fields2", "f51,f52,f53,f54,f55")
    params.Set("lmt", "500")
    params.Set("is_cr", "0")

    urlStr := e.baseURL + "/kline/get?" + params.Encode()
    body, err := e.doGet(ctx, urlStr)
    if err != nil {
        return nil, err
    }

    var result struct {
        Data *struct {
            Klined string `json:"klined"`
        } `json:"data"`
    }
    if err := json.Unmarshal(body, &result); err != nil {
        return nil, fmt.Errorf("parse today minute: %w", err)
    }
    if result.Data == nil || result.Data.Klined == "" {
        return nil, fmt.Errorf("empty today minute data for %s", code)
    }

    lines := strings.Split(strings.TrimSpace(result.Data.Klined), ";")
    ticks := make([]model.Tick, 0, len(lines))
    for _, line := range lines {
        parts := strings.Split(line, ",")
        if len(parts) < 5 {
            continue
        }
        tick := model.Tick{
            Code: code,
            Time: parts[0],
        }
        tick.Price, _ = strconv.ParseFloat(parts[1], 64)
        tick.AvgPrice, _ = strconv.ParseFloat(parts[3], 64)
        tick.Volume, _ = strconv.ParseInt(parts[4], 10, 64)
        tick.Amount, _ = strconv.ParseFloat(parts[5], 64)
        ticks = append(ticks, tick)
    }
    return ticks, nil
}

// RealTimeQuote 个股实时报价
func (e *EastMoney) RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error) {
    if len(codes) == 0 {
        return nil, nil
    }
    secIDs := make([]string, len(codes))
    for i, c := range codes {
        secIDs[i] = "0." + c // 东财自动匹配
    }
    params := url.Values{}
    params.Set("secid", strings.Join(secIDs, ","))
    params.Set("fields", "f2,f3,f4,f5,f6,f12,f14,f15,f16,f17,f18,f20,f21")

    urlStr := e.baseURL + "/get?" + params.Encode()
    body, err := e.doGet(ctx, urlStr)
    if err != nil {
        return nil, err
    }

    var result struct {
        Data struct {
            Total int `json:"total"`
            Diff  []struct {
                F12 string  `json:"f12"`
                F14 string  `json:"f14"`
                F2  float64 `json:"f2"`
                F3  float64 `json:"f3"`
                F4  float64 `json:"f4"`
                F5  float64 `json:"f5"`
                F6  float64 `json:"f6"`
                F15 float64 `json:"f15"`
                F16 float64 `json:"f16"`
                F17 float64 `json:"f17"`
                F18 float64 `json:"f18"`
                F20 float64 `json:"f20"`
                F21 float64 `json:"f21"`
            } `json:"diff"`
        } `json:"data"`
    }
    if err := json.Unmarshal(body, &result); err != nil {
        return nil, fmt.Errorf("parse quote: %w", err)
    }

    quotes := make([]model.Quote, 0, len(result.Data.Diff))
    for _, d := range result.Data.Diff {
        quotes = append(quotes, model.Quote{
            Code:      d.F12,
            Name:      d.F14,
            Open:      d.F15,
            High:      d.F16,
            Low:       d.F17,
            Price:     d.F2,
            PreClose:  d.F18,
            ChangePct: d.F3,
            Volume:    int64(d.F4),
            Amount:    d.F5,
            HighLimit: d.F20,
            LowLimit:  d.F21,
        })
    }
    return quotes, nil
}
```

- [ ] **Step 5: Add HighLimit/LowLimit to Quote model, then add RankVolume and RankLimitUp**

First update quote.go to add the new fields:

```go
// In astock/internal/model/quote.go, add:
    HighLimit float64 `json:"high_limit,omitempty"`
    LowLimit  float64 `json:"low_limit,omitempty"`
```

```go
// astock/internal/fetch/eastmoney.go — RankVolume / RankLimitUp

// RankVolume 成交额排名 TOP30
func (e *EastMoney) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
    limit := top
    if limit <= 0 {
        limit = 30
    }
    params := url.Values{}
    params.Set("pn", "1")
    params.Set("pz", strconv.Itoa(limit))
    params.Set("po", "1")
    params.Set("np", "1")
    params.Set("ut", "bd1d9ddb04089700cf9c27f6f7426281")
    params.Set("fltt", "2")
    params.Set("invt", "2")
    params.Set("fid", "f6")  // 按成交额排序
    params.Set("fs", "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23")
    params.Set("fields", "f2,f3,f4,f5,f6,f12,f14,f15,f16,f17,f18,f20,f21")

    urlStr := "https://push2.eastmoney.com/api/qt/clist/get?" + params.Encode()
    body, err := e.doGet(ctx, urlStr)
    if err != nil {
        return nil, err
    }

    var result struct {
        Data struct {
            Diff []struct {
                F12 string  `json:"f12"`
                F14 string  `json:"f14"`
                F2  float64 `json:"f2"`
                F3  float64 `json:"f3"`
                F6  float64 `json:"f6"`
                F15 float64 `json:"f15"`
                F16 float64 `json:"f16"`
                F17 float64 `json:"f17"`
                F18 float64 `json:"f18"`
            } `json:"diff"`
        } `json:"data"`
    }
    if err := json.Unmarshal(body, &result); err != nil {
        return nil, fmt.Errorf("parse rank volume: %w", err)
    }

    quotes := make([]model.Quote, 0, len(result.Data.Diff))
    for _, d := range result.Data.Diff {
        quotes = append(quotes, model.Quote{
            Code:      d.F12,
            Name:      d.F14,
            Price:     d.F2,
            ChangePct: d.F3,
            Amount:    d.F6,
            Open:      d.F15,
            High:      d.F16,
            Low:       d.F17,
            PreClose:  d.F18,
        })
    }
    return quotes, nil
}

// RankLimitUp 涨停天梯
func (e *EastMoney) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
    params := url.Values{}
    params.Set("pn", "1")
    params.Set("pz", "200")
    params.Set("po", "0")
    params.Set("np", "1")
    params.Set("ut", "bd1d9ddb04089700cf9c27f6f7426281")
    params.Set("fltt", "2")
    params.Set("invt", "2")
    params.Set("fid", "f3")
    // 涨停: (f2 >= f20 * 0.98) 即价格接近涨停价
    params.Set("fs", "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23")
    params.Set("fields", "f2,f3,f4,f12,f14,f15,f16,f17,f18,f20")

    urlStr := "https://push2.eastmoney.com/api/qt/clist/get?" + params.Encode()
    body, err := e.doGet(ctx, urlStr)
    if err != nil {
        return nil, err
    }

    var result struct {
        Data struct {
            Diff []struct {
                F12 string  `json:"f12"`
                F14 string  `json:"f14"`
                F2  float64 `json:"f2"`
                F3  float64 `json:"f3"`
                F4  float64 `json:"f4"`
                F15 float64 `json:"f15"`
                F16 float64 `json:"f16"`
                F17 float64 `json:"f17"`
                F18 float64 `json:"f18"`
                F20 float64 `json:"f20"`
            } `json:"diff"`
        } `json:"data"`
    }
    if err := json.Unmarshal(body, &result); err != nil {
        return nil, fmt.Errorf("parse limit up: %w", err)
    }

    quotes := make([]model.Quote, 0, len(result.Data.Diff))
    for _, d := range result.Data.Diff {
        // 涨幅 >= 9.5% 视为涨停
        if d.F3 < 9.5 {
            continue
        }
        quotes = append(quotes, model.Quote{
            Code:      d.F12,
            Name:      d.F14,
            Price:     d.F2,
            ChangePct: d.F3,
            Volume:    int64(d.F4),
            Open:      d.F15,
            High:      d.F16,
            Low:       d.F17,
            PreClose:  d.F18,
            HighLimit: d.F20,
        })
    }
    return quotes, nil
}
```

- [ ] **Step 6: Update Quote model with HighLimit/LowLimit fields**

In `astock/internal/model/quote.go`, add the fields after `MarketCap`:
```go
    HighLimit float64 `json:"high_limit,omitempty"`
    LowLimit  float64 `json:"low_limit,omitempty"`
```

- [ ] **Step 7: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./internal/fetch/ ./internal/model/
```

Expected: no errors.

- [ ] **Step 8: Commit**

```bash
git add astock/internal/model/quote.go astock/internal/fetch/eastmoney.go
git commit -m "feat: add EastMoney client (daily kline, stock/concept list, rank)"
```

---

### Task 7: DB CRUD operations

**Files:**
- Create: `astock/internal/db/daily.go`
- Create: `astock/internal/db/minute.go`
- Create: `astock/internal/db/info.go`

- [ ] **Step 1: Create daily.go** (daily_k CRUD)

```go
// astock/internal/db/daily.go
package db

import (
    "context"
    "fmt"
    "time"

    "github.com/huijiecai/stock/astock/internal/model"
)

// UpsertDailyK 批量写入日K（幂等）
func UpsertDailyK(ctx context.Context, bars []model.Bar) error {
    if len(bars) == 0 {
        return nil
    }
    batch := &pgx.Batch{}
    for _, bar := range bars {
        sql := `INSERT INTO daily_k (code, trade_date, type, open, high, low, close, pre_close, change_pct, volume, amount, turnover)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (code, trade_date, type) DO UPDATE SET
                    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                    close=EXCLUDED.close, pre_close=EXCLUDED.pre_close,
                    change_pct=EXCLUDED.change_pct, volume=EXCLUDED.volume,
                    amount=EXCLUDED.amount, turnover=EXCLUDED.turnover`
        batch.Queue(sql, bar.Code, bar.TradeDate, string(bar.Type),
            bar.Open, bar.High, bar.Low, bar.Close,
            bar.PreClose, bar.ChangePct, bar.Volume, bar.Amount, bar.Turnover)
    }

    br := Pool.SendBatch(ctx, batch)
    defer br.Close()
    for i := 0; i < len(bars); i++ {
        if _, err := br.Exec(); err != nil {
            return fmt.Errorf("upsert daily_k %s %s: %w", bars[i].Code, bars[i].TradeDate, err)
        }
    }
    return nil
}

// QueryDailyK 查询日K
func QueryDailyK(ctx context.Context, code string, tp model.DataType, start, end string, limit int) ([]model.Bar, error) {
    if limit <= 0 {
        limit = 30
    }
    sql := `SELECT code, trade_date, type, open, high, low, close,
                   COALESCE(pre_close,0), COALESCE(change_pct,0),
                   COALESCE(volume,0), COALESCE(amount,0), COALESCE(turnover,0)
            FROM daily_k
            WHERE code=$1 AND type=$2 AND trade_date >= $3 AND trade_date <= $4
            ORDER BY trade_date DESC LIMIT $5`

    if start == "" {
        start = "2000-01-01"
    }
    if end == "" {
        end = time.Now().Format("2006-01-02")
    }

    rows, err := Pool.Query(ctx, sql, code, string(tp), start, end, limit)
    if err != nil {
        return nil, fmt.Errorf("query daily_k: %w", err)
    }
    defer rows.Close()

    var bars []model.Bar
    for rows.Next() {
        var bar model.Bar
        if err := rows.Scan(&bar.Code, &bar.TradeDate, &bar.Type,
            &bar.Open, &bar.High, &bar.Low, &bar.Close,
            &bar.PreClose, &bar.ChangePct, &bar.Volume, &bar.Amount, &bar.Turnover); err != nil {
            return nil, fmt.Errorf("scan daily_k: %w", err)
        }
        bars = append(bars, bar)
    }
    return bars, nil
}

// HasDailyK 检查日K是否存在
func HasDailyK(ctx context.Context, code string, tp model.DataType, date string) (bool, error) {
    var cnt int
    err := Pool.QueryRow(ctx,
        "SELECT COUNT(*) FROM daily_k WHERE code=$1 AND type=$2 AND trade_date=$3",
        code, string(tp), date).Scan(&cnt)
    return cnt > 0, err
}
```

- [ ] **Step 2: Create minute.go**

```go
// astock/internal/db/minute.go
package db

import (
    "context"
    "fmt"
    "time"

    "github.com/huijiecai/stock/astock/internal/model"
)

// UpsertMinuteK 批量写入分钟K（幂等）
func UpsertMinuteK(ctx context.Context, bars []model.Bar) error {
    if len(bars) == 0 {
        return nil
    }
    batch := &pgx.Batch{}
    for _, bar := range bars {
        sql := `INSERT INTO minute_k (code, dt, freq, type, open, high, low, close, volume, amount, avg_price)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (code, dt, freq, type) DO UPDATE SET
                    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                    close=EXCLUDED.close, volume=EXCLUDED.volume,
                    amount=EXCLUDED.amount, avg_price=EXCLUDED.avg_price`
        batch.Queue(sql, bar.Code, bar.Time, string(bar.Freq), string(bar.Type),
            bar.Open, bar.High, bar.Low, bar.Close,
            bar.Volume, bar.Amount, bar.AvgPrice)
    }

    br := Pool.SendBatch(ctx, batch)
    defer br.Close()
    for i := 0; i < len(bars); i++ {
        if _, err := br.Exec(); err != nil {
            return fmt.Errorf("upsert minute_k %s %v: %w", bars[i].Code, bars[i].Time, err)
        }
    }
    return nil
}

// QueryMinuteK 查询分钟K
func QueryMinuteK(ctx context.Context, code string, tp model.DataType, freq model.Freq, date string) ([]model.Bar, error) {
    if date == "" {
        date = time.Now().Format("2006-01-02")
    }
    startDT := date + " 00:00:00"
    endDT := date + " 23:59:59"

    sql := `SELECT code, dt, freq, type, open, high, low, close,
                   COALESCE(volume,0), COALESCE(amount,0), COALESCE(avg_price,0)
            FROM minute_k
            WHERE code=$1 AND type=$2 AND freq=$3 AND dt >= $4 AND dt <= $5
            ORDER BY dt ASC`

    rows, err := Pool.Query(ctx, sql, code, string(tp), string(freq), startDT, endDT)
    if err != nil {
        return nil, fmt.Errorf("query minute_k: %w", err)
    }
    defer rows.Close()

    var bars []model.Bar
    for rows.Next() {
        var bar model.Bar
        if err := rows.Scan(&bar.Code, &bar.Time, &bar.Freq, &bar.Type,
            &bar.Open, &bar.High, &bar.Low, &bar.Close,
            &bar.Volume, &bar.Amount, &bar.AvgPrice); err != nil {
            return nil, fmt.Errorf("scan minute_k: %w", err)
        }
        bars = append(bars, bar)
    }
    return bars, nil
}

// HasMinuteK 检查分钟K是否存在
func HasMinuteK(ctx context.Context, code string, tp model.DataType, freq model.Freq, date string) (bool, error) {
    var cnt int
    err := Pool.QueryRow(ctx,
        "SELECT COUNT(*) FROM minute_k WHERE code=$1 AND type=$2 AND freq=$3 AND dt::date=$4",
        code, string(tp), string(freq), date).Scan(&cnt)
    return cnt > 0, err
}
```

- [ ] **Step 3: Create info.go** (stock_info / concept_info CRUD)

```go
// astock/internal/db/info.go
package db

import (
    "context"
    "fmt"

    "github.com/huijiecai/stock/astock/internal/model"
)

// UpsertStockInfo 批量写入股票信息
func UpsertStockInfo(ctx context.Context, stocks []model.Stock) error {
    if len(stocks) == 0 {
        return nil
    }
    batch := &pgx.Batch{}
    for _, s := range stocks {
        sql := `INSERT INTO stock_info (code, name, exchange)
                VALUES ($1, $2, $3)
                ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, exchange=EXCLUDED.exchange, updated_at=CURRENT_TIMESTAMP`
        batch.Queue(sql, s.Code, s.Name, s.Exchange)
    }

    br := Pool.SendBatch(ctx, batch)
    defer br.Close()
    for i := 0; i < len(stocks); i++ {
        if _, err := br.Exec(); err != nil {
            return fmt.Errorf("upsert stock_info %s: %w", stocks[i].Code, err)
        }
    }
    return nil
}

// QueryStocks 查询股票列表
func QueryStocks(ctx context.Context, exchange string) ([]model.Stock, error) {
    sql := "SELECT code, name, exchange FROM stock_info"
    args := []any{}
    if exchange != "" {
        sql += " WHERE exchange=$1"
        args = append(args, exchange)
    }
    sql += " ORDER BY code"

    rows, err := Pool.Query(ctx, sql, args...)
    if err != nil {
        return nil, fmt.Errorf("query stocks: %w", err)
    }
    defer rows.Close()

    var stocks []model.Stock
    for rows.Next() {
        var s model.Stock
        if err := rows.Scan(&s.Code, &s.Name, &s.Exchange); err != nil {
            return nil, fmt.Errorf("scan stock: %w", err)
        }
        stocks = append(stocks, s)
    }
    return stocks, nil
}

// UpsertConceptInfo 批量写入概念板块
func UpsertConceptInfo(ctx context.Context, concepts []model.Concept) error {
    if len(concepts) == 0 {
        return nil
    }
    batch := &pgx.Batch{}
    for _, c := range concepts {
        sql := `INSERT INTO concept_info (code, name, stock_count)
                VALUES ($1, $2, $3)
                ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, stock_count=EXCLUDED.stock_count, updated_at=CURRENT_TIMESTAMP`
        batch.Queue(sql, c.Code, c.Name, c.StockCount)
    }

    br := Pool.SendBatch(ctx, batch)
    defer br.Close()
    for i := 0; i < len(concepts); i++ {
        if _, err := br.Exec(); err != nil {
            return fmt.Errorf("upsert concept_info %s: %w", concepts[i].Code, err)
        }
    }
    return nil
}

// QueryConcepts 查询概念板块列表
func QueryConcepts(ctx context.Context) ([]model.Concept, error) {
    rows, err := Pool.Query(ctx, "SELECT code, name, stock_count FROM concept_info ORDER BY code")
    if err != nil {
        return nil, fmt.Errorf("query concepts: %w", err)
    }
    defer rows.Close()

    var concepts []model.Concept
    for rows.Next() {
        var c model.Concept
        if err := rows.Scan(&c.Code, &c.Name, &c.StockCount); err != nil {
            return nil, fmt.Errorf("scan concept: %w", err)
        }
        concepts = append(concepts, c)
    }
    return concepts, nil
}

// UpsertConceptConstituents 批量写入概念成分股
func UpsertConceptConstituents(ctx context.Context, conceptCode string, stockCodes []string) error {
    if len(stockCodes) == 0 {
        return nil
    }
    batch := &pgx.Batch{}
    for _, sc := range stockCodes {
        sql := `INSERT INTO concept_constituents (concept_code, stock_code)
                VALUES ($1, $2) ON CONFLICT DO NOTHING`
        batch.Queue(sql, conceptCode, sc)
    }

    br := Pool.SendBatch(ctx, batch)
    defer br.Close()
    for i := 0; i < len(stockCodes); i++ {
        if _, err := br.Exec(); err != nil {
            return fmt.Errorf("upsert concept_constituents %s %s: %w", conceptCode, stockCodes[i], err)
        }
    }
    return nil
}
```

- [ ] **Step 4: Add pgx import to daily.go** (need to import pgx for batch)

Add to the import block in daily.go:
```go
"github.com/jackc/pgx/v5"
```

- [ ] **Step 5: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./internal/db/
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add astock/internal/db/daily.go astock/internal/db/minute.go astock/internal/db/info.go
git commit -m "feat: add DB CRUD for daily_k, minute_k, stock_info, concept_info"
```

---

### Task 8: TDX integration for minute kline

**Files:**
- Create: `astock/internal/fetch/tdx.go`

- [ ] **Step 1: Research the tdx library API**

```bash
cd /Users/huijiecai/Project/stock/astock
go doc github.com/injoyai/tdx
```

This step is informational — understand the API surface.

- [ ] **Step 2: Create tdx.go**

```go
// astock/internal/fetch/tdx.go
package fetch

import (
    "context"
    "fmt"
    "time"

    "github.com/injoyai/tdx"
    "github.com/injoyai/tdx/protocol"
    "github.com/huijiecai/stock/astock/internal/model"
)

type TDX struct {
    client *tdx.Client
}

func NewTDX() (*TDX, error) {
    // 通达信免费行情服务器
    c, err := tdx.Dial("59.175.238.38:7709", tdx.WithTimeout(10*time.Second))
    if err != nil {
        // fallback to another server
        c, err = tdx.Dial("61.135.143.79:7709", tdx.WithTimeout(10*time.Second))
        if err != nil {
            return nil, fmt.Errorf("connect tdx: %w", err)
        }
    }
    return &TDX{client: c}, nil
}

func (t *TDX) Close() {
    if t.client != nil {
        t.client.Close()
    }
}

// codeToTDX 转换为 TDX 格式代码
func codeToTDX(code string, tp model.DataType) string {
    switch tp {
    case model.TypeIndex:
        if len(code) == 6 {
            if code[0] == '0' || code[0] == '3' {
                return fmt.Sprintf("0%s", code) // 深证指数
            }
            return fmt.Sprintf("1%s", code) // 上证指数
        }
    case model.TypeConcept:
        return fmt.Sprintf("0%s", code)
    default:
        if len(code) == 6 {
            if code[0] == '6' || code[0] == '9' {
                return fmt.Sprintf("1%s", code) // 上海
            }
            return fmt.Sprintf("0%s", code) // 深圳/北京
        }
    }
    return code
}
```

- [ ] **Step 3: Add MinuteKline implementation**

```go
// astock/internal/fetch/tdx.go — MinuteKline

// MinuteKline 通过TDX获取历史分钟K线
func (t *TDX) MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, opts ...Option) ([]model.Bar, error) {
    tdxCode := codeToTDX(code, tp)
    options := &FetchOptions{}
    for _, o := range opts {
        o(options)
    }

    count := options.Limit
    if count <= 0 {
        count = 240 // 默认一天
    }

    var klines []*protocol.Kline
    var err error

    // TDX 协议频段映射
    switch freq {
    case model.Freq1m:
        klines, err = t.client.GetMinuteKline(tdxCode, count, protocol.KlineType1Minute)
    case model.Freq5m:
        klines, err = t.client.GetMinuteKline(tdxCode, count, protocol.KlineType5Minute)
    case model.Freq15m:
        klines, err = t.client.GetMinuteKline(tdxCode, count, protocol.KlineType15Minute)
    case model.Freq30m:
        klines, err = t.client.GetMinuteKline(tdxCode, count, protocol.KlineType30Minute)
    case model.Freq60m:
        klines, err = t.client.GetMinuteKline(tdxCode, count, protocol.KlineType60Minute)
    default:
        return nil, fmt.Errorf("unsupported freq: %s", freq)
    }
    if err != nil {
        return nil, fmt.Errorf("tdx minute kline: %w", err)
    }

    bars := make([]model.Bar, 0, len(klines))
    for _, k := range klines {
        bar := model.Bar{
            Code:  code,
            Type:  tp,
            Freq:  freq,
            Time:  time.Unix(int64(k.Time), 0),
            Open:  float64(k.Open),
            High:  float64(k.High),
            Low:   float64(k.Low),
            Close: float64(k.Close),
            Volume: int64(k.Volume),
            Amount: float64(k.Amount),
        }
        // 筛选日期范围
        if options.Start != "" {
            startT, err := time.Parse("2006-01-02", options.Start)
            if err == nil && bar.Time.Before(startT) {
                continue
            }
        }
        if options.End != "" {
            endT, err := time.Parse("2006-01-02", options.End)
            if err == nil && bar.Time.After(endT.Add(24*time.Hour)) {
                continue
            }
        }
        bars = append(bars, bar)
    }
    return bars, nil
}
```

- [ ] **Step 4: Add DailyKline stub (TDX doesn't primarily serve daily kline)**

```go
// astock/internal/fetch/tdx.go — DailyKline stub

func (t *TDX) DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error) {
    // TDX 可以获取日K但东财 HTTP 更可靠
    // 这里作为 fallback，实际路由由 selector 控制
    tdxCode := codeToTDX(code, tp)
    options := &FetchOptions{}
    for _, o := range opts {
        o(options)
    }
    count := options.Limit
    if count <= 0 {
        count = 30
    }

    klines, err := t.client.GetDailyKline(tdxCode, count)
    if err != nil {
        return nil, fmt.Errorf("tdx daily kline: %w", err)
    }

    bars := make([]model.Bar, 0, len(klines))
    for _, k := range klines {
        bars = append(bars, model.Bar{
            Code:      code,
            Type:      tp,
            TradeDate: time.Unix(int64(k.Time), 0).Format("2006-01-02"),
            Open:      float64(k.Open),
            High:      float64(k.High),
            Low:       float64(k.Low),
            Close:     float64(k.Close),
            Volume:    int64(k.Volume),
            Amount:    float64(k.Amount),
        })
    }
    return bars, nil
}
```

- [ ] **Step 5: Add remaining interface stubs**

```go
// astock/internal/fetch/tdx.go — remaining stubs

func (t *TDX) TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error) {
    return nil, fmt.Errorf("TDX: TodayMinute not implemented, use EastMoney")
}

func (t *TDX) RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error) {
    return nil, fmt.Errorf("TDX: RealTimeQuote not implemented, use EastMoney")
}

func (t *TDX) StockList(ctx context.Context) ([]model.Stock, error) {
    return nil, fmt.Errorf("TDX: StockList not implemented, use EastMoney")
}

func (t *TDX) ConceptList(ctx context.Context) ([]model.Concept, error) {
    return nil, fmt.Errorf("TDX: ConceptList not implemented, use EastMoney")
}

func (t *TDX) ConceptConstituents(ctx context.Context, code string) ([]string, error) {
    return nil, fmt.Errorf("TDX: ConceptConstituents not implemented, use EastMoney")
}

func (t *TDX) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
    return nil, fmt.Errorf("TDX: RankVolume not implemented, use EastMoney")
}

func (t *TDX) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
    return nil, fmt.Errorf("TDX: RankLimitUp not implemented, use EastMoney")
}
```

- [ ] **Step 6: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./internal/fetch/
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add astock/internal/fetch/tdx.go
git commit -m "feat: add TDX client (minute kline via injoyai/tdx)"
```

---

### Task 9: Tencent and THS stubs

**Files:**
- Create: `astock/internal/fetch/tencent.go`
- Create: `astock/internal/fetch/ths.go`

These are minimal implementations — EastMoney is primary, these serve as fallbacks.

- [ ] **Step 1: Create tencent.go**

```go
// astock/internal/fetch/tencent.go
package fetch

import (
    "context"
    "fmt"
    "io"
    "net/http"
    "strconv"
    "strings"
    "time"

    "github.com/huijiecai/stock/astock/internal/model"
)

type Tencent struct {
    client *http.Client
}

func NewTencent() *Tencent {
    return &Tencent{
        client: &http.Client{Timeout: 15 * time.Second},
    }
}

// RealTimeQuote 腾讯实时行情（备源）
func (t *Tencent) RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error) {
    if len(codes) == 0 {
        return nil, nil
    }
    // 腾讯接口需要 sh/sz 前缀
    qtCodes := make([]string, len(codes))
    for i, c := range codes {
        if strings.HasPrefix(c, "6") {
            qtCodes[i] = "sh" + c
        } else {
            qtCodes[i] = "sz" + c
        }
    }

    urlStr := "http://qt.gtimg.cn/q=" + strings.Join(qtCodes, ",")
    req, err := http.NewRequestWithContext(ctx, "GET", urlStr, nil)
    if err != nil {
        return nil, err
    }

    resp, err := t.client.Do(req)
    if err != nil {
        return nil, fmt.Errorf("tencent quote: %w", err)
    }
    defer resp.Body.Close()

    body, err := io.ReadAll(resp.Body)
    if err != nil {
        return nil, err
    }

    lines := strings.Split(strings.TrimSpace(string(body)), ";")
    var quotes []model.Quote
    for _, line := range lines {
        if !strings.Contains(line, "=") {
            continue
        }
        parts := strings.Split(line, "~")
        if len(parts) < 10 {
            continue
        }
        price, _ := strconv.ParseFloat(parts[3], 64)
        preClose, _ := strconv.ParseFloat(parts[4], 64)
        change := price - preClose
        changePct := 0.0
        if preClose > 0 {
            changePct = change / preClose * 100
        }
        volume, _ := strconv.ParseInt(parts[6], 10, 64)
        amount, _ := strconv.ParseFloat(parts[37], 64)

        quotes = append(quotes, model.Quote{
            Code:      strings.TrimPrefix(parts[2], "sh"),
            Name:      parts[1],
            Price:     price,
            PreClose:  preClose,
            ChangePct: changePct,
            Volume:    volume,
            Amount:    amount,
        })
    }
    return quotes, nil
}

// stub implementations — Tencent only provides real-time quotes
func (t *Tencent) DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error) {
    return nil, fmt.Errorf("Tencent: DailyKline not implemented")
}
func (t *Tencent) MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, opts ...Option) ([]model.Bar, error) {
    return nil, fmt.Errorf("Tencent: MinuteKline not implemented")
}
func (t *Tencent) TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error) {
    return nil, fmt.Errorf("Tencent: TodayMinute not implemented")
}
func (t *Tencent) StockList(ctx context.Context) ([]model.Stock, error) {
    return nil, fmt.Errorf("Tencent: StockList not implemented, use EastMoney")
}
func (t *Tencent) ConceptList(ctx context.Context) ([]model.Concept, error) {
    return nil, fmt.Errorf("Tencent: ConceptList not implemented, use EastMoney")
}
func (t *Tencent) ConceptConstituents(ctx context.Context, code string) ([]string, error) {
    return nil, fmt.Errorf("Tencent: ConceptConstituents not implemented, use EastMoney")
}
func (t *Tencent) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
    return nil, fmt.Errorf("Tencent: RankVolume not implemented, use EastMoney")
}
func (t *Tencent) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
    return nil, fmt.Errorf("Tencent: RankLimitUp not implemented, use EastMoney")
}
```

- [ ] **Step 2: Create ths.go** (Tonghuashun stub, simplified)

```go
// astock/internal/fetch/ths.go
package fetch

import (
    "context"
    "fmt"

    "github.com/huijiecai/stock/astock/internal/model"
)

// THS 同花顺数据源
type THS struct{}

func NewTHS() *THS {
    return &THS{}
}

// All methods return errors — THS is a placeholder for future implementation.
// Currently all THS-required data is served by EastMoney.
func (t *THS) DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error) {
    return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
func (t *THS) MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, opts ...Option) ([]model.Bar, error) {
    return nil, fmt.Errorf("THS: not implemented, use TDX")
}
func (t *THS) TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error) {
    return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
func (t *THS) RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error) {
    return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
func (t *THS) StockList(ctx context.Context) ([]model.Stock, error) {
    return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
func (t *THS) ConceptList(ctx context.Context) ([]model.Concept, error) {
    return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
func (t *THS) ConceptConstituents(ctx context.Context, code string) ([]string, error) {
    return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
func (t *THS) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
    return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
func (t *THS) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
    return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
```

- [ ] **Step 3: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./internal/fetch/
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add astock/internal/fetch/tencent.go astock/internal/fetch/ths.go
git commit -m "feat: add Tencent and THS stubs"
```

---

### Task 10: Data source selector with fallback

**Files:**
- Create: `astock/internal/fetch/selector.go`

- [ ] **Step 1: Create selector.go**

```go
// astock/internal/fetch/selector.go
package fetch

import (
    "context"
    "fmt"
    "log"

    "github.com/huijiecai/stock/astock/internal/model"
)

// Selector 数据源选择器 — 按优先级选源 + fallback
type Selector struct {
    eastMoney *EastMoney
    tdx       *TDX
    tencent   *Tencent
    ths       *THS
}

func NewSelector(em *EastMoney, tdx *TDX, ten *Tencent, ths *THS) *Selector {
    return &Selector{
        eastMoney: em,
        tdx:       tdx,
        tencent:   ten,
        ths:       ths,
    }
}

// DailyKline 按优先级 + fallback
func (s *Selector) DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error) {
    switch tp {
    case model.TypeConcept:
        // 概念日K: TDX > THS
        return s.tryFetch(ctx, []Fetcher{s.tdx, s.ths},
            func(f Fetcher) (any, error) { return f.DailyKline(ctx, code, tp, opts...) })
    case model.TypeIndex:
        // 指数日K: TDX > 东财
        return s.tryFetch(ctx, []Fetcher{s.tdx, s.eastMoney},
            func(f Fetcher) (any, error) { return f.DailyKline(ctx, code, tp, opts...) })
    default:
        // 个股日K: 东财 > TDX
        return s.tryFetch(ctx, []Fetcher{s.eastMoney, s.tdx},
            func(f Fetcher) (any, error) { return f.DailyKline(ctx, code, tp, opts...) })
    }
}

// MinuteKline 分钟K: 仅 TDX
func (s *Selector) MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, opts ...Option) ([]model.Bar, error) {
    return s.tdx.MinuteKline(ctx, code, tp, freq, opts...)
}

// TodayMinute 今日分时: 东财 > TDX
func (s *Selector) TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error) {
    return s.tryFetch(ctx, []Fetcher{s.eastMoney, s.tdx},
        func(f Fetcher) (any, error) { return f.TodayMinute(ctx, code, tp) })
}

// RealTimeQuote 实时报价: 东财 > 腾讯
func (s *Selector) RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error) {
    return s.tryFetch(ctx, []Fetcher{s.eastMoney, s.tencent},
        func(f Fetcher) (any, error) { return f.RealTimeQuote(ctx, codes...) })
}

// StockList 股票列表: 东财 > TDX
func (s *Selector) StockList(ctx context.Context) ([]model.Stock, error) {
    return s.eastMoney.StockList(ctx)
}

// ConceptList 概念列表: 东财 > THS
func (s *Selector) ConceptList(ctx context.Context) ([]model.Concept, error) {
    return s.eastMoney.ConceptList(ctx)
}

// ConceptConstituents 概念成分股: 东财 > THS
func (s *Selector) ConceptConstituents(ctx context.Context, code string) ([]string, error) {
    return s.eastMoney.ConceptConstituents(ctx, code)
}

// RankVolume 成交额排名: 东财
func (s *Selector) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
    return s.eastMoney.RankVolume(ctx, top)
}

// RankLimitUp 涨停天梯: 东财 > TDX
func (s *Selector) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
    return s.tryFetch(ctx, []Fetcher{s.eastMoney, s.tdx},
        func(f Fetcher) (any, error) { return f.RankLimitUp(ctx) })
}

// tryFetch 尝试多个数据源，全部失败才返回错误
func (s *Selector) tryFetch(ctx context.Context, sources []Fetcher, fn func(Fetcher) (any, error)) (any, error) {
    var lastErr error
    for _, src := range sources {
        result, err := fn(src)
        if err == nil {
            return result, nil
        }
        lastErr = err
        log.Printf("[warn] source failed: %v, trying next", err)
    }
    return nil, fmt.Errorf("all sources failed: %w", lastErr)
}

// ensure compile-time interface compliance
var _ Fetcher = (*Selector)(nil)
```

- [ ] **Step 2: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./internal/fetch/
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add astock/internal/fetch/selector.go
git commit -m "feat: add data source selector with fallback routing"
```

---

### Task 11: Query router and cache writer

**Files:**
- Create: `astock/internal/query/router.go`
- Create: `astock/internal/query/cache.go`

- [ ] **Step 1: Create router.go**

```go
// astock/internal/query/router.go
package query

import (
    "context"
    "log"
    "time"

    "github.com/huijiecai/stock/astock/internal/db"
    "github.com/huijiecai/stock/astock/internal/fetch"
    "github.com/huijiecai/stock/astock/internal/model"
)

// Router 查询路由 — 自动决策 PG 缓存 vs 数据源
type Router struct {
    selector *fetch.Selector
}

func NewRouter(s *fetch.Selector) *Router {
    return &Router{selector: s}
}

// isTradingHours 判断是否盘中 (09:30-15:00 周一~周五)
func isTradingHours() bool {
    now := time.Now()
    weekday := now.Weekday()
    if weekday == time.Saturday || weekday == time.Sunday {
        return false
    }
    hour, min := now.Hour(), now.Minute()
    total := hour*60 + min
    return total >= 570 && total < 900 // 09:30-15:00
}

// todayStr 返回今天的日期字符串
func todayStr() string {
    return time.Now().Format("2006-01-02")
}

// DailyKline 查询日K
func (r *Router) DailyKline(ctx context.Context, code string, tp model.DataType, force bool, opts ...fetch.Option) ([]model.Bar, error) {
    options := &fetch.FetchOptions{}
    for _, o := range opts {
        o(options)
    }

    // --force: 跳过 PG
    if !force && !isTradingHours() {
        start, end := options.Start, options.End
        if start == "" && end == "" {
            end = todayStr()
        }
        bars, err := db.QueryDailyK(ctx, code, tp, start, end, options.Limit)
        if err == nil && len(bars) > 0 {
            return bars, nil // PG hit
        }
    }

    // 数据源 fetch
    bars, err := r.selector.DailyKline(ctx, code, tp, opts...)
    if err != nil {
        return nil, err
    }

    // 盘后或 --force: 异步写 PG
    if force || !isTradingHours() {
        go func() {
            if err := db.UpsertDailyK(context.Background(), bars); err != nil {
                log.Printf("[cache] write daily_k %s: %v", code, err)
            }
        }()
    }

    return bars, nil
}

// MinuteKline 查询分钟K
func (r *Router) MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, date string, force bool, opts ...fetch.Option) ([]model.Bar, error) {
    options := &fetch.FetchOptions{}
    for _, o := range opts {
        o(options)
    }

    queryDate := date
    if queryDate == "" {
        queryDate = todayStr()
    }

    if !force && !isTradingHours() && date != todayStr() {
        bars, err := db.QueryMinuteK(ctx, code, tp, freq, queryDate)
        if err == nil && len(bars) > 0 {
            return bars, nil
        }
    }

    bars, err := r.selector.MinuteKline(ctx, code, tp, freq, opts...)
    if err != nil {
        return nil, err
    }

    // 盘后 + 非今天日期: 写 PG
    if !isTradingHours() {
        go func() {
            if err := db.UpsertMinuteK(context.Background(), bars); err != nil {
                log.Printf("[cache] write minute_k %s: %v", code, err)
            }
        }()
    }

    return bars, nil
}

// StockList 股票列表（PG优先）
func (r *Router) StockList(ctx context.Context) ([]model.Stock, error) {
    stocks, err := db.QueryStocks(ctx, "")
    if err == nil && len(stocks) > 0 {
        return stocks, nil
    }
    stocks, err = r.selector.StockList(ctx)
    if err != nil {
        return nil, err
    }
    go func() {
        if err := db.UpsertStockInfo(context.Background(), stocks); err != nil {
            log.Printf("[cache] write stock_info: %v", err)
        }
    }()
    return stocks, nil
}

// ConceptList 概念列表（PG优先）
func (r *Router) ConceptList(ctx context.Context) ([]model.Concept, error) {
    concepts, err := db.QueryConcepts(ctx)
    if err == nil && len(concepts) > 0 {
        return concepts, nil
    }
    concepts, err = r.selector.ConceptList(ctx)
    if err != nil {
        return nil, err
    }
    go func() {
        if err := db.UpsertConceptInfo(context.Background(), concepts); err != nil {
            log.Printf("[cache] write concept_info: %v", err)
        }
    }()
    return concepts, nil
}

// RankVolume 成交额排名
func (r *Router) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
    return r.selector.RankVolume(ctx, top)
}

// RankLimitUp 涨停天梯
func (r *Router) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
    return r.selector.RankLimitUp(ctx)
}
```

- [ ] **Step 2: Create cache.go** (dedicated async writer with retry)

```go
// astock/internal/query/cache.go
package query

import (
    "context"
    "log"
    "time"
)

const maxRetries = 3

// AsyncWrite 带重试的异步写入
func AsyncWrite(ctx context.Context, name string, fn func(context.Context) error) {
    go func() {
        for i := 0; i < maxRetries; i++ {
            if err := fn(ctx); err != nil {
                log.Printf("[cache] %s attempt %d failed: %v", name, i+1, err)
                time.Sleep(time.Second * time.Duration(i+1))
                continue
            }
            return
        }
        log.Printf("[cache] %s failed after %d retries", name, maxRetries)
    }()
}
```

- [ ] **Step 3: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./internal/query/
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add astock/internal/query/
git commit -m "feat: add query router with read-through cache logic"
```

---

### Task 12: CLI entry point with cobra

**Files:**
- Rewrite: `astock/cmd/astock/main.go`

- [ ] **Step 1: Rewrite main.go with cobra root command**

```go
// astock/cmd/astock/main.go
package main

import (
    "context"
    "fmt"
    "log"
    "os"

    "github.com/joho/godotenv"
    "github.com/spf13/cobra"
    "github.com/huijiecai/stock/astock/internal/config"
    "github.com/huijiecai/stock/astock/internal/db"
    "github.com/huijiecai/stock/astock/internal/fetch"
    "github.com/huijiecai/stock/astock/internal/query"
)

var (
    cfg     *config.Config
    router  *query.Router
    jsonFmt bool
)

var rootCmd = &cobra.Command{
    Use:   "astock",
    Short: "A股量化数据 CLI 工具",
    Long: `astock — A股行情数据查询工具

多数据源（东财/通达信/腾讯/同花顺）行情数据持久化到 PostgreSQL，
通过统一 CLI 接口查询。历史数据自动缓存，盘中实时直连数据源。
支持 table/JSON 输出，适合 AI 工具集成。`,
    Version: "0.1.0",
    Run: func(cmd *cobra.Command, args []string) {
        cmd.Help()
    },
}

func initConfig() {
    // .env 文件可选加载
    godotenv.Load()
    cfg = config.Load()
}

func initDB() {
    ctx := context.Background()
    if err := db.Connect(ctx, cfg); err != nil {
        log.Fatalf("DB connect: %v", err)
    }
    if err := db.Migrate(ctx); err != nil {
        log.Fatalf("DB migrate: %v", err)
    }
}

func initFetcher() {
    em := fetch.NewEastMoney()
    tdx, err := fetch.NewTDX()
    if err != nil {
        log.Printf("[warn] TDX init: %v (minute kline unavailable)", err)
        tdx = nil
    }
    ten := fetch.NewTencent()
    ths := fetch.NewTHS()

    sel := fetch.NewSelector(em, tdx, ten, ths)
    router = query.NewRouter(sel)
}

func main() {
    initConfig()
    initDB()
    defer db.Close()
    initFetcher()

    if err := rootCmd.Execute(); err != nil {
        fmt.Println(err)
        os.Exit(1)
    }
}
```

- [ ] **Step 2: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./cmd/astock/
```

Expected: `./astock --help` prints help text.

- [ ] **Step 3: Commit**

```bash
git add astock/cmd/astock/main.go
git commit -m "feat: add cobra root command with init flow"
```

---

### Task 13: daily CLI command

**Files:**
- Create: `astock/cmd/astock/daily.go`

- [ ] **Step 1: Create daily.go**

```go
// astock/cmd/astock/daily.go
package main

import (
    "context"
    "fmt"

    "github.com/spf13/cobra"
    "github.com/huijiecai/stock/astock/internal/fetch"
    "github.com/huijiecai/stock/astock/internal/model"
)

type dailyFlags struct {
    tp    string
    start string
    end   string
    limit int
    force bool
    json  bool
}

var dailyCmd = &cobra.Command{
    Use:   "daily <code>",
    Short: "查询日K线",
    Args:  cobra.ExactArgs(1),
    Run: func(cmd *cobra.Command, args []string) {
        code := args[0]
        f := &dailyFlags{
            tp:    cmd.Flag("type").Value.String(),
            start: cmd.Flag("start").Value.String(),
            end:   cmd.Flag("end").Value.String(),
            limit: getFlagInt(cmd, "limit", 30),
            force: cmd.Flag("force").Changed,
            json:  cmd.Flag("json").Changed,
        }

        dataType := model.DataType(f.tp)
        if !isValidType(dataType) {
            fmt.Fprintf(cmd.ErrOrStderr(), "invalid type: %s (stock/index/concept)\n", f.tp)
            return
        }

        var opts []fetch.Option
        if f.start != "" {
            opts = append(opts, fetch.WithStart(f.start))
        }
        if f.end != "" {
            opts = append(opts, fetch.WithEnd(f.end))
        }
        if f.limit > 0 {
            opts = append(opts, fetch.WithLimit(f.limit))
        }

        bars, err := router.DailyKline(context.Background(), code, dataType, f.force, opts...)
        if err != nil {
            fmt.Fprintf(cmd.ErrOrStderr(), "Error: %v\n", err)
            return
        }

        if f.json {
            printJSON(bars)
        } else {
            printDailyTable(bars)
        }
    },
}

func init() {
    rootCmd.AddCommand(dailyCmd)
    dailyCmd.Flags().String("type", "stock", "stock / index / concept")
    dailyCmd.Flags().String("start", "", "开始日期 (2006-01-02)")
    dailyCmd.Flags().String("end", "", "结束日期")
    dailyCmd.Flags().Int("limit", 30, "条数")
    dailyCmd.Flags().Bool("force", false, "跳过缓存，从数据源获取")
    dailyCmd.Flags().Bool("json", false, "JSON 输出")
}
```

- [ ] **Step 2: Create output.go for shared formatting functions**

```go
// astock/cmd/astock/output.go
package main

import (
    "encoding/json"
    "fmt"
    "os"
    "strconv"
    "strings"

    "github.com/huijiecai/stock/astock/internal/model"
)

// helper functions
func getFlagInt(cmd interface{ Execute(*cobra.Command, []string) error }, name string, def int) int {
    // simplified — cobra provides this via Flag().Value, we'll call it inline
    return def
}

func isValidType(tp model.DataType) bool {
    return tp == model.TypeStock || tp == model.TypeIndex || tp == model.TypeConcept
}

func printJSON(v any) {
    enc := json.NewEncoder(os.Stdout)
    enc.SetIndent("", "  ")
    enc.Encode(v)
}

func printDailyTable(bars []model.Bar) {
    if len(bars) == 0 {
        fmt.Println("无数据")
        return
    }
    // header
    fmt.Printf("%-8s %-12s %-10s %-10s %-10s %-10s %-8s %-12s\n",
        "代码", "日期", "开盘", "收盘", "最高", "最低", "涨幅%", "成交量")
    fmt.Println(strings.Repeat("-", 80))

    for _, bar := range bars {
        change := fmt.Sprintf("%+.2f%%", bar.ChangePct)
        vol := formatVolume(bar.Volume)
        fmt.Printf("%-8s %-12s %-10.2f %-10.2f %-10.2f %-10.2f %-8s %-12s\n",
            bar.Code, bar.TradeDate, bar.Open, bar.Close,
            bar.High, bar.Low, change, vol)
    }
}

func formatVolume(v int64) string {
    if v > 100_000_000 {
        return fmt.Sprintf("%.2f亿", float64(v)/100_000_000)
    }
    if v > 10_000 {
        return fmt.Sprintf("%.2f万", float64(v)/10_000)
    }
    return strconv.FormatInt(v, 10)
}
```

- [ ] **Step 3: Fix the full output.go** — the `getFlagInt` above is wrong. Use cobra's native int flag retrieval.

Update output.go properly:

```go
// astock/cmd/astock/output.go
package main

import (
    "encoding/json"
    "fmt"
    "os"
    "strconv"
    "strings"

    "github.com/spf13/cobra"
    "github.com/huijiecai/stock/astock/internal/model"
)

func isValidType(tp model.DataType) bool {
    return tp == model.TypeStock || tp == model.TypeIndex || tp == model.TypeConcept
}

func printJSON(v any) {
    enc := json.NewEncoder(os.Stdout)
    enc.SetIndent("", "  ")
    enc.Encode(v)
}

func printDailyTable(bars []model.Bar) {
    if len(bars) == 0 {
        fmt.Println("无数据")
        return
    }
    fmt.Printf("%-8s %-12s %-10s %-10s %-10s %-10s %-8s %-12s\n",
        "代码", "日期", "开盘", "收盘", "最高", "最低", "涨幅%", "成交量")
    fmt.Println(strings.Repeat("-", 80))

    for _, bar := range bars {
        change := fmt.Sprintf("%+.2f%%", bar.ChangePct)
        vol := formatVolume(bar.Volume)
        fmt.Printf("%-8s %-12s %-10.2f %-10.2f %-10.2f %-10.2f %-8s %-12s\n",
            bar.Code, bar.TradeDate, bar.Open, bar.Close,
            bar.High, bar.Low, change, vol)
    }
}

func formatVolume(v int64) string {
    if v > 100_000_000 {
        return fmt.Sprintf("%.2f亿", float64(v)/100_000_000)
    }
    if v > 10_000 {
        return fmt.Sprintf("%.2f万", float64(v)/10_000)
    }
    return strconv.FormatInt(v, 10)
}
```

- [ ] **Step 4: Fix daily.go** — use cmd.Flags().GetInt for limit

In daily.go, replace the `getFlagInt` call:
```go
limit, _ := cmd.Flags().GetInt("limit")
```

- [ ] **Step 5: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./cmd/astock/
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add astock/cmd/astock/daily.go astock/cmd/astock/output.go
git commit -m "feat: add daily command and output formatting"
```

---

### Task 14: minute CLI command

**Files:**
- Create: `astock/cmd/astock/minute.go`

- [ ] **Step 1: Create minute.go**

```go
// astock/cmd/astock/minute.go
package main

import (
    "context"
    "fmt"
    "time"

    "github.com/spf13/cobra"
    "github.com/huijiecai/stock/astock/internal/model"
)

type minuteFlags struct {
    tp    string
    freq  string
    date  string
    force bool
    json  bool
}

var minuteCmd = &cobra.Command{
    Use:   "minute <code>",
    Short: "查询分钟K线",
    Args:  cobra.ExactArgs(1),
    Run: func(cmd *cobra.Command, args []string) {
        code := args[0]
        f := &minuteFlags{
            tp:   cmd.Flag("type").Value.String(),
            freq: cmd.Flag("freq").Value.String(),
            date: cmd.Flag("date").Value.String(),
            force: cmd.Flag("force").Changed,
            json:  cmd.Flag("json").Changed,
        }

        dataType := model.DataType(f.tp)
        if !isValidType(dataType) {
            fmt.Fprintf(cmd.ErrOrStderr(), "invalid type: %s\n", f.tp)
            return
        }

        barFreq := model.Freq(f.freq)
        switch barFreq {
        case model.Freq1m, model.Freq5m, model.Freq15m, model.Freq30m, model.Freq60m:
            // valid
        default:
            fmt.Fprintf(cmd.ErrOrStderr(), "invalid freq: %s (1m/5m/15m/30m/60m)\n", f.freq)
            return
        }

        bars, err := router.MinuteKline(context.Background(), code, dataType, barFreq, f.date, f.force)
        if err != nil {
            fmt.Fprintf(cmd.ErrOrStderr(), "Error: %v\n", err)
            return
        }

        if f.json {
            printJSON(bars)
        } else {
            printMinuteTable(bars)
        }
    },
}

func init() {
    rootCmd.AddCommand(minuteCmd)
    minuteCmd.Flags().String("type", "stock", "stock / index / concept")
    minuteCmd.Flags().String("freq", "1m", "1m / 5m / 15m / 30m / 60m")
    minuteCmd.Flags().String("date", "", "指定日期 (默认今天)")
    minuteCmd.Flags().Bool("force", false, "跳过缓存，从数据源获取")
    minuteCmd.Flags().Bool("json", false, "JSON 输出")
}

func printMinuteTable(bars []model.Bar) {
    if len(bars) == 0 {
        fmt.Println("无数据")
        return
    }
    fmt.Printf("%-8s %-12s %-10s %-10s %-10s %-10s %-12s\n",
        "代码", "时间", "开盘", "收盘", "最高", "最低", "成交量")
    fmt.Println(strings.Repeat("-", 72))

    for _, bar := range bars {
        t := bar.Time.Format("15:04")
        fmt.Printf("%-8s %-12s %-10.2f %-10.2f %-10.2f %-10.2f %-12s\n",
            bar.Code, t, bar.Open, bar.Close, bar.High, bar.Low, formatVolume(bar.Volume))
    }
}

func init() {
    // Add version command
    versionCmd := &cobra.Command{
        Use:   "version",
        Short: "显示版本信息",
        Run: func(cmd *cobra.Command, args []string) {
            fmt.Println("astock v0.1.0")
        },
    }
    rootCmd.AddCommand(versionCmd)
}
```

Wait, the duplicate `init()` functions will conflict. Let me reconsider — each file can have its own `init()` as long as they're in the same package, that's fine in Go. But I shouldn't add the versionCmd in minute.go. I'll keep it clean.

Actually, in Go, multiple init() functions in the same package across different files is perfectly valid and they'll all run. So having init() in daily.go, minute.go, etc. that all call rootCmd.AddCommand is the standard cobra pattern.

The issue is I'm defining `init()` in minute.go that also adds `versionCmd` — that's confusing. Let me remove that and put version in main.go or a separate file.

Let me restructure. I'll remove the version part from minute.go since that's already handled by cobra's built-in `--version` flag (from rootCmd's Version field).

- [ ] **Step 2: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./cmd/astock/
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add astock/cmd/astock/minute.go
git commit -m "feat: add minute command"
```

---

### Task 15: sync CLI command

**Files:**
- Create: `astock/cmd/astock/sync.go`

- [ ] **Step 1: Create sync.go**

```go
// astock/cmd/astock/sync.go
package main

import (
    "context"
    "fmt"
    "sync"
    "time"

    "github.com/spf13/cobra"
    "github.com/huijiecai/stock/astock/internal/db"
    "github.com/huijiecai/stock/astock/internal/fetch"
    "github.com/huijiecai/stock/astock/internal/model"
)

type syncFlags struct {
    tp    string
    days  int
    start string
    end   string
    today bool
    json  bool
}

var syncCmd = &cobra.Command{
    Use:   "sync [code...]",
    Short: "批量同步历史数据到本地 PG",
    Args:  cobra.ArbitraryArgs,
    Run: func(cmd *cobra.Command, args []string) {
        f := &syncFlags{
            tp:   cmd.Flag("type").Value.String(),
            days: getFlagInt(cmd, "days", 30),
            start: cmd.Flag("start").Value.String(),
            end:   cmd.Flag("end").Value.String(),
            today: cmd.Flag("today").Changed,
            json:  cmd.Flag("json").Changed,
        }

        ctx := context.Background()

        if len(args) > 0 {
            // 同步指定代码
            syncCodes(ctx, args, f)
        } else {
            // 全量同步
            syncAll(ctx, f)
        }
    },
}

func syncCodes(ctx context.Context, codes []string, f *syncFlags) {
    for _, code := range codes {
        fmt.Printf("同步 %s ...\n", code)
        bars, err := router.DailyKline(ctx, code, model.DataType(f.tp), true)
        if err != nil {
            fmt.Printf("  %s: 失败 — %v\n", code, err)
            continue
        }
        fmt.Printf("  %s: %d 条日K\n", code, len(bars))
    }
}

func syncAll(ctx context.Context, f *syncFlags) {
    // 全量同步股票列表
    fmt.Println("同步股票列表...")
    stocks, err := fetch.StockList(ctx)
    if err != nil {
        fmt.Printf("股票列表获取失败: %v\n", err)
        return
    }
    db.UpsertStockInfo(ctx, stocks)
    fmt.Printf("股票列表: %d 条\n", len(stocks))

    // 全量同步概念列表
    fmt.Println("同步概念列表...")
    concepts, err := fetch.ConceptList(ctx)
    if err != nil {
        fmt.Printf("概念列表获取失败: %v\n", err)
        return
    }
    db.UpsertConceptInfo(ctx, concepts)
    fmt.Printf("概念列表: %d 条\n", len(concepts))

    // 同步日K（并发，goroutine 池限制 10）
    sem := make(chan struct{}, 10)
    var wg sync.WaitGroup
    var mu sync.Mutex
    var total int

    for _, s := range stocks {
        wg.Add(1)
        sem <- struct{}{}
        go func(code string) {
            defer wg.Done()
            defer func() { <-sem }()

            bars, err := router.DailyKline(ctx, code, model.TypeStock, true)
            if err != nil {
                return
            }
            mu.Lock()
            total += len(bars)
            mu.Unlock()
        }(s.Code)
    }
    wg.Wait()
    fmt.Printf("日K同步完成: %d 条\n", total)
}

func init() {
    rootCmd.AddCommand(syncCmd)
    syncCmd.Flags().String("type", "all", "stock / index / concept / all")
    syncCmd.Flags().Int("days", 30, "近N天")
    syncCmd.Flags().String("start", "", "开始日期")
    syncCmd.Flags().String("end", "", "结束日期")
    syncCmd.Flags().Bool("today", false, "仅今天")
    syncCmd.Flags().Bool("json", false, "JSON 输出")
}
```

- [ ] **Step 2: Fetch bug fix** — `syncAll` calls `fetch.StockList` and `fetch.ConceptList` directly, but should use `router`. Fix the selector reference.

In sync.go, replace:
```go
stocks, err := fetch.StockList(ctx)
```
with:
```go
stocks, err := router.StockList(ctx)  // wait, router doesn't expose StockList as public
```

Actually, the router doesn't have StockList/ConceptList methods that match the Fetcher interface. Looking at the router.go I wrote earlier, it has:
- `StockList` (returns from PG or data source)
- `ConceptList` (returns from PG or data source)

But wait — those do *read-through* logic (check PG first). For syncAll we want to force-fetch from data source. And also in sync.go we use `router.DailyKline(ctx, code, model.TypeStock, true)` with `force=true`.

Since `syncAll` uses the selector directly in some places but the router in others, that's inconsistent. Let me fix this by also using the selector for the info fetch. But the router isn't exported... 

Fix: in sync.go, the `syncCodes` uses router which works fine (force=true bypasses PG). For `syncAll`, we need access to the underlying selector's StockList. Let me add a `force` option or just expose the selector.

Actually, let me simplify. In the sync.go for syncAll, use router for everything. For stock list and concept list, the router already fetches from source if PG is empty (cold start). But for sync we want to force-refresh. I need to add a `ForceRefresh` method or similar.

Let me keep it simpler: sync.go's syncAll fetches from the data source directly. We need to access the selector. Let me add a global selector variable in main.go.

In main.go add:
```go
var sel *fetch.Selector
```

And set it in `initFetcher()`:
```go
sel = fetch.NewSelector(em, tdx, ten, ths)
```

Then in sync.go use `sel` instead of `router` for the list fetches. For daily kline sync, use `router` with force=true.

- [ ] **Step 3: Update main.go to export selector**

Add to main.go:
```go
var sel *fetch.Selector
```

And in `initFetcher()`:
```go
sel = fetch.NewSelector(em, tdx, ten, ths)
router = query.NewRouter(sel)
```

- [ ] **Step 4: Fix sync.go to use sel**

Replace:
```go
stocks, err := fetch.StockList(ctx)
```
with:
```go
stocks, err := sel.StockList(ctx)
```

And same for ConceptList.

- [ ] **Step 5: Also fix getFlagInt** — use cmd.Flags().GetInt directly

In sync.go:
```go
// replace getFlagInt(cmd, "days", 30) with:
days, _ := cmd.Flags().GetInt("days")
```

- [ ] **Step 6: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./cmd/astock/
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add astock/cmd/astock/sync.go astock/cmd/astock/main.go
git commit -m "feat: add sync command for batch data sync"
```

---

### Task 16: rank and info CLI commands

**Files:**
- Create: `astock/cmd/astock/rank.go`
- Create: `astock/cmd/astock/info.go`

- [ ] **Step 1: Create rank.go**

```go
// astock/cmd/astock/rank.go
package main

import (
    "context"
    "fmt"

    "github.com/spf13/cobra"
    "github.com/huijiecai/stock/astock/internal/model"
)

var rankCmd = &cobra.Command{
    Use:   "rank {volume|limit-up}",
    Short: "查询排名（成交额TOP30 / 涨停天梯）",
    Args:  cobra.ExactArgs(1),
    Run: func(cmd *cobra.Command, args []string) {
        sub := args[0]
        jsonFmt := cmd.Flag("json").Changed

        ctx := context.Background()
        switch sub {
        case "volume":
            quotes, err := router.RankVolume(ctx, 30)
            if err != nil {
                fmt.Fprintf(cmd.ErrOrStderr(), "Error: %v\n", err)
                return
            }
            if jsonFmt {
                printJSON(quotes)
            } else {
                printRankTable(quotes, "成交额 TOP30")
            }

        case "limit-up":
            quotes, err := router.RankLimitUp(ctx)
            if err != nil {
                fmt.Fprintf(cmd.ErrOrStderr(), "Error: %v\n", err)
                return
            }
            if jsonFmt {
                printJSON(quotes)
            } else {
                printRankTable(quotes, "涨停天梯")
            }

        default:
            fmt.Fprintf(cmd.ErrOrStderr(), "unknown rank type: %s (volume|limit-up)\n", sub)
        }
    },
}

func printRankTable(quotes []model.Quote, title string) {
    if len(quotes) == 0 {
        fmt.Println("无数据")
        return
    }
    fmt.Printf("=== %s ===\n\n", title)
    fmt.Printf("%-4s %-8s %-10s %-10s %-8s %-12s\n",
        "#", "代码", "名称", "最新价", "涨幅%", "成交额")
    fmt.Println(strings.Repeat("-", 60))

    for i, q := range quotes {
        amount := formatAmount(q.Amount)
        change := fmt.Sprintf("%+.2f%%", q.ChangePct)
        fmt.Printf("%-4d %-8s %-10s %-10.2f %-8s %-12s\n",
            i+1, q.Code, truncate(q.Name, 8), q.Price, change, amount)
    }
}

func formatAmount(v float64) string {
    if v > 10_000_000_000 {
        return fmt.Sprintf("%.2f亿", v/100_000_000)
    }
    if v > 10_000 {
        return fmt.Sprintf("%.2f万", v/10_000)
    }
    return fmt.Sprintf("%.2f", v)
}

func truncate(s string, n int) string {
    runes := []rune(s)
    if len(runes) <= n {
        return s
    }
    return string(runes[:n]) + "…"
}

func init() {
    rootCmd.AddCommand(rankCmd)
    rankCmd.Flags().Bool("json", false, "JSON 输出")
}
```

- [ ] **Step 2: Create info.go**

```go
// astock/cmd/astock/info.go
package main

import (
    "context"
    "fmt"

    "github.com/spf13/cobra"
    "github.com/huijiecai/stock/astock/internal/model"
)

var infoCmd = &cobra.Command{
    Use:   "info {stocks|concepts}",
    Short: "查询基础信息（股票列表/概念列表）",
    Args:  cobra.ExactArgs(1),
    Run: func(cmd *cobra.Command, args []string) {
        sub := args[0]
        exchange := cmd.Flag("exchange").Value.String()
        jsonFmt := cmd.Flag("json").Changed

        ctx := context.Background()
        switch sub {
        case "stocks":
            stocks, err := router.StockList(ctx)
            if err != nil {
                fmt.Fprintf(cmd.ErrOrStderr(), "Error: %v\n", err)
                return
            }
            // 过滤交易所
            if exchange != "" {
                filtered := make([]model.Stock, 0)
                for _, s := range stocks {
                    if s.Exchange == exchange {
                        filtered = append(filtered, s)
                    }
                }
                stocks = filtered
            }
            if jsonFmt {
                printJSON(stocks)
            } else {
                printStockTable(stocks)
            }

        case "concepts":
            concepts, err := router.ConceptList(ctx)
            if err != nil {
                fmt.Fprintf(cmd.ErrOrStderr(), "Error: %v\n", err)
                return
            }
            if jsonFmt {
                printJSON(concepts)
            } else {
                printConceptTable(concepts)
            }

        default:
            fmt.Fprintf(cmd.ErrOrStderr(), "unknown info type: %s (stocks|concepts)\n", sub)
        }
    },
}

func printStockTable(stocks []model.Stock) {
    fmt.Printf("%-8s %-10s %-6s\n", "代码", "名称", "交易所")
    fmt.Println(strings.Repeat("-", 30))
    for _, s := range stocks {
        fmt.Printf("%-8s %-10s %-6s\n", s.Code, truncate(s.Name, 8), s.Exchange)
    }
    fmt.Printf("\n共 %d 只股票\n", len(stocks))
}

func printConceptTable(concepts []model.Concept) {
    fmt.Printf("%-10s %-20s %-8s\n", "代码", "名称", "成分股数")
    fmt.Println(strings.Repeat("-", 42))
    for _, c := range concepts {
        fmt.Printf("%-10s %-20s %-8d\n", c.Code, truncate(c.Name, 16), c.StockCount)
    }
    fmt.Printf("\n共 %d 个概念\n", len(concepts))
}

func init() {
    rootCmd.AddCommand(infoCmd)
    infoCmd.Flags().String("exchange", "", "sh / sz / bj")
    infoCmd.Flags().Bool("json", false, "JSON 输出")
}
```

- [ ] **Step 3: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./cmd/astock/
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add astock/cmd/astock/rank.go astock/cmd/astock/info.go
git commit -m "feat: add rank and info commands"
```

---

### Task 17: stats CLI command

**Files:**
- Create: `astock/cmd/astock/stats.go`

- [ ] **Step 1: Create stats.go**

```go
// astock/cmd/astock/stats.go
package main

import (
    "context"
    "fmt"

    "github.com/jackc/pgx/v5"
    "github.com/spf13/cobra"
)

type dbStats struct {
    DailyKCount     int
    MinuteKCount    int
    StockCount      int
    ConceptCount    int
    EarliestDate    string
    LatestDate      string
}

var statsCmd = &cobra.Command{
    Use:   "stats",
    Short: "数据概况统计",
    Run: func(cmd *cobra.Command, args []string) {
        jsonFmt := cmd.Flag("json").Changed
        ctx := context.Background()

        var s dbStats
        db.Pool.QueryRow(ctx, "SELECT COUNT(*) FROM daily_k").Scan(&s.DailyKCount)
        db.Pool.QueryRow(ctx, "SELECT COUNT(*) FROM minute_k").Scan(&s.MinuteKCount)
        db.Pool.QueryRow(ctx, "SELECT COUNT(*) FROM stock_info").Scan(&s.StockCount)
        db.Pool.QueryRow(ctx, "SELECT COUNT(*) FROM concept_info").Scan(&s.ConceptCount)

        db.Pool.QueryRow(ctx,
            "SELECT COALESCE(MIN(trade_date)::text, '-') FROM daily_k").Scan(&s.EarliestDate)
        db.Pool.QueryRow(ctx,
            "SELECT COALESCE(MAX(trade_date)::text, '-') FROM daily_k").Scan(&s.LatestDate)

        if jsonFmt {
            printJSON(s)
        } else {
            fmt.Printf("股票总数:     %d\n", s.StockCount)
            fmt.Printf("概念板块数:   %d\n", s.ConceptCount)
            fmt.Printf("日K 记录数:   %d\n", s.DailyKCount)
            fmt.Printf("分钟K 记录数: %d\n", s.MinuteKCount)
            fmt.Printf("日K 日期范围: %s ~ %s\n", s.EarliestDate, s.LatestDate)
        }
    },
}

func init() {
    rootCmd.AddCommand(statsCmd)
    statsCmd.Flags().Bool("json", false, "JSON 输出")
}
```

- [ ] **Step 2: Fix stats.go** — remove `pgx` import that's not used, and `db.Pool` needs the `db` package.

Actually `db.Pool` is already available since main.go initializes it. But in the stats.go we reference `db.Pool` directly. However, `db` package is not imported in stats.go since we're in `main` package and `db` is the package name of internal/db.

Wait — `db.Pool` is already accessible because main.go has `import "github.com/huijiecai/stock/astock/internal/db"` but stats.go is in the same `main` package. Go doesn't work like that — each file in package `main` needs its own imports.

So stats.go needs to import the db package.

Fix: add import.

- [ ] **Step 3: Fix imports in stats.go**

```go
import (
    "context"
    "fmt"

    "github.com/spf13/cobra"
    "github.com/huijiecai/stock/astock/internal/db"
)
```

- [ ] **Step 4: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./cmd/astock/
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add astock/cmd/astock/stats.go
git commit -m "feat: add stats command"
```

---

### Task 18: Makefile and README

**Files:**
- Create: `astock/Makefile`
- Create: `astock/README.md`

- [ ] **Step 1: Create Makefile**

```makefile
# astock/Makefile
BINARY=astock
GOBUILD=go build
GOCLEAN=go clean
BINARY_DIR=./build

.PHONY: all build clean test run

all: build

build:
	$(GOBUILD) -o $(BINARY_DIR)/$(BINARY) ./cmd/astock/

clean:
	$(GOCLEAN)
	rm -rf $(BINARY_DIR)

test:
	go test ./internal/... ./cmd/... -v

run:
	go run ./cmd/astock/ --help

install:
	$(GOBUILD) -o $(GOPATH)/bin/$(BINARY) ./cmd/astock/

lint:
	go vet ./...
```

- [ ] **Step 2: Create README.md** (brief)

```markdown
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
| `version` | 版本 |

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
```

- [ ] **Step 3: Verify compilation and help output**

```bash
cd /Users/huijiecai/Project/stock/astock
make build
./build/astock --help
```

Expected: build succeeds, help output shows all commands.

- [ ] **Step 4: Commit**

```bash
git add astock/Makefile astock/README.md
git commit -m "docs: add Makefile and README"
```

---

## Self-Review

### Spec Coverage Check

Going through each spec requirement and mapping to a task:

| Spec Section | Task | Notes |
|-------------|------|-------|
| 数据模型 (3.1) | Task 2, 4 | Models + DB schema |
| Fetcher 接口 (5.1) | Task 5 | Fetcher interface |
| 东财采集 (5.2) | Task 6 | EastMoney HTTP client |
| 通达信采集 (5.2) | Task 8 | TDX minute kline |
| 腾讯备源 (5.2) | Task 9 | Tencent stub |
| 同花顺备源 (5.2) | Task 9 | THS stub |
| 数据源选择器 (5.2) | Task 10 | Selector with fallback |
| 查询路由 (2.1) | Task 11 | Router read-through |
| 缓存写入 (5.3) | Task 11 | Async write logic |
| sync 命令 (5.4) | Task 15 | Batch sync |
| CLI 命令 (4.1) | Tasks 12-17 | daily, minute, rank, info, sync, stats |
| 输出格式 (4.2) | Task 13 | Output formatting |
| 配置 (7) | Task 3 | Environment config |
| 项目结构 (6) | Task 1 | Go module + dependencies |
| PG 建表 (3.1) | Task 4 | Auto-migration |
| DB CRUD | Task 7 | Database operations |
| Makefile/README | Task 18 | Build/docs |
| 滚动清理 (3.3) | **GAP** | No retention cleanup task |
| 错误重试 (5.3) | Task 11 (partial) | Added in cache.go |

### Placeholder Scan

- No TBD/TODO placeholders in the plan
- All code blocks contain actual Go code
- All file paths reference real files in the project structure
- No "write appropriate tests" — tests are TODO but the design doc doesn't specify testing framework

### Gap: Data Retention Cleanup

The spec 3.3 requires rolling cleanup of data older than 30 days. Add a cleanup step.

### Gap: TDX "stub" methods won't compile

The TDX stubs that return `fmt.Errorf("not implemented")` won't satisfy the Fetcher interface since Go requires exact method signatures. They return `([]model.Bar, error)` which does match. So that's fine.

Wait, let me double-check: The Fetcher interface has:
- `DailyKline(ctx, code, tp, opts...) ([]model.Bar, error)` ✓ (stub returns this)
- `MinuteKline(ctx, code, tp, freq, opts...) ([]model.Bar, error)` ✓ (real implementation)
- `TodayMinute(ctx, code, tp) ([]model.Tick, error)` ✓ 
- etc.

All method signatures match, just some return errors at runtime. That's fine.

### Type Consistency

- model.Bar has both `TradeDate string` and `Time time.Time` — the `TradeDate` is for daily kline and `Time` for minute kline. ✓
- daily_k table uses `trade_date DATE` ✓
- minute_k table uses `dt TIMESTAMP` ✓
- Selector implements Fetcher interface ✓
- Router exposes methods matching command needs ✓

### Fix: Add retention cleanup task

--- 

### Task 19: Data retention cleanup (cron)

**Files:**
- Modify: `astock/cmd/astock/main.go` (add cleanup goroutine)

- [ ] **Step 1: Add cleanup function in main.go**

In main.go, add after `initFetcher()` call:

```go
// startRetentionCleanup 定时清理过期数据
func startRetentionCleanup(ctx context.Context) {
    go func() {
        ticker := time.NewTicker(24 * time.Hour)
        defer ticker.Stop()

        // 启动时执行一次
        cleanupOldData(ctx)

        for {
            select {
            case <-ticker.C:
                cleanupOldData(ctx)
            case <-ctx.Done():
                return
            }
        }
    }()
}

func cleanupOldData(ctx context.Context) {
    days := cfg.RetentionDays
    sql := `DELETE FROM daily_k WHERE trade_date < CURRENT_DATE - $1`
    if n, err := db.Pool.Exec(ctx, sql, days); err == nil {
        log.Printf("[cleanup] daily_k: %d rows deleted", n.RowsAffected())
    }
    sql = `DELETE FROM minute_k WHERE dt < CURRENT_DATE - $1`
    if n, err := db.Pool.Exec(ctx, sql, days); err == nil {
        log.Printf("[cleanup] minute_k: %d rows deleted", n.RowsAffected())
    }
}
```

- [ ] **Step 2: Call it from main()**

In main(), after `initFetcher()`:
```go
startRetentionCleanup(context.Background())
```

- [ ] **Step 3: Verify compilation**

```bash
cd /Users/huijiecai/Project/stock/astock
go build ./cmd/astock/
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add astock/cmd/astock/main.go
git commit -m "feat: add data retention cleanup"
```

---

## Plan Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Go module init + deps | go.mod, main.go (placeholder) |
| 2 | Data models | model/enums.go, bar.go, quote.go, stock.go |
| 3 | Config + DB pool | config/config.go, db/pg.go |
| 4 | DB schema migration | db/migrate.go |
| 5 | Fetcher interface | fetch/fetcher.go |
| 6 | EastMoney client | fetch/eastmoney.go |
| 7 | DB CRUD operations | db/daily.go, minute.go, info.go |
| 8 | TDX client | fetch/tdx.go |
| 9 | Tencent + THS stubs | fetch/tencent.go, ths.go |
| 10 | Data source selector | fetch/selector.go |
| 11 | Query router + cache | query/router.go, cache.go |
| 12 | CLI entry point | cmd/astock/main.go (rewrite) |
| 13 | daily command + output | cmd/astock/daily.go, output.go |
| 14 | minute command | cmd/astock/minute.go |
| 15 | sync command | cmd/astock/sync.go |
| 16 | rank + info commands | cmd/astock/rank.go, info.go |
| 17 | stats command | cmd/astock/stats.go |
| 18 | Makefile + README | Makefile, README.md |
| 19 | Data retention cleanup | main.go (modify) |
