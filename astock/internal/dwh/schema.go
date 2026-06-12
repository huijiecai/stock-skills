package dwh

import (
	"context"
	"fmt"
)

// Tables 列出所有由 InitSchema 管理的表（顺序无关）。
var Tables = []string{
	"securities",
	"blocks",
	"block_constituents",
	"trade_cal",
	"xdxr",
	"finance",
	"kline_daily",
	"kline_minute",
	"sync_log",
}

// schemaDDL 返回项目所有 DDL，按"先建库再建表"顺序执行。
// 设计依据：docs/superpowers/specs/2026-06-13-astock-ch-design.md 第四节。
func (c *Client) schemaDDL() []string {
	db := c.db
	return []string{
		// 0. 数据库本身
		fmt.Sprintf(`CREATE DATABASE IF NOT EXISTS %s`, db),

		// 1. securities — 标的身份证表 + F10 公司信息
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %s.securities (
    code        String,
    market      LowCardinality(String),
    type        LowCardinality(String),
    name        String,
    list_date   Date,
    delist_date Nullable(Date),
    industry    LowCardinality(String) DEFAULT '',
    sector      LowCardinality(String) DEFAULT '',
    province    LowCardinality(String) DEFAULT '',
    business    String DEFAULT '',
    updated_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (type, market, code)`, db),

		// 2. blocks — 板块/概念表
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %s.blocks (
    code        String,
    name        String,
    type        LowCardinality(String),
    stock_count UInt32,
    updated_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (type, code)`, db),

		// 3. block_constituents — 板块成分股关系
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %s.block_constituents (
    block_code String,
    stock_code String,
    updated_at DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (block_code, stock_code)`, db),

		// 4. trade_cal — 交易日历
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %s.trade_cal (
    trade_date Date,
    is_open    UInt8
) ENGINE = ReplacingMergeTree
ORDER BY trade_date`, db),

		// 5. xdxr — 除权除息（复权基础）
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %s.xdxr (
    code         String,
    ex_date      Date,
    type         LowCardinality(String),
    bonus        Float32 DEFAULT 0,
    transfer     Float32 DEFAULT 0,
    dividend     Float32 DEFAULT 0,
    rights_price Float32 DEFAULT 0,
    rights_ratio Float32 DEFAULT 0,
    updated_at   DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (code, ex_date, type)`, db),

		// 6. finance — 财务数据
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %s.finance (
    code            String,
    report_date     Date,
    revenue         Float64 DEFAULT 0,
    net_profit      Float64 DEFAULT 0,
    eps             Float32 DEFAULT 0,
    bps             Float32 DEFAULT 0,
    roe             Float32 DEFAULT 0,
    total_share     UInt64 DEFAULT 0,
    float_share     UInt64 DEFAULT 0,
    total_assets    Float64 DEFAULT 0,
    total_liability Float64 DEFAULT 0,
    updated_at      DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY (code, report_date)`, db),

		// 7. kline_daily — 日 K 线核心大表
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %s.kline_daily (
    code       String,
    type       LowCardinality(String),
    trade_date Date,
    open       Float64,
    high       Float64,
    low        Float64,
    close      Float64,
    pre_close  Float64,
    volume     UInt64,
    amount     Float64,
    turnover   Float32,
    change_pct Float32 MATERIALIZED if(pre_close > 0, (close - pre_close) / pre_close * 100, 0)
) ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(trade_date)
ORDER BY (type, code, trade_date)`, db),

		// 8. kline_minute — 分钟 K 线（含历史分时）
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %s.kline_minute (
    code   String,
    type   LowCardinality(String),
    freq   LowCardinality(String),
    dt     DateTime,
    open   Float64,
    high   Float64,
    low    Float64,
    close  Float64,
    volume UInt64,
    amount Float64
) ENGINE = ReplacingMergeTree
PARTITION BY toYYYYMM(dt)
ORDER BY (type, code, freq, dt)`, db),

		// 9. sync_log — 同步任务日志（普通 MergeTree，不去重）
		fmt.Sprintf(`CREATE TABLE IF NOT EXISTS %s.sync_log (
    task     String,
    target   String,
    start_at DateTime,
    end_at   Nullable(DateTime),
    rows     UInt64,
    status   LowCardinality(String),
    err_msg  String DEFAULT ''
) ENGINE = MergeTree
ORDER BY (task, start_at)`, db),
	}
}

// InitSchema 创建数据库及全部 9 张表。幂等。
func (c *Client) InitSchema(ctx context.Context) error {
	for i, ddl := range c.schemaDDL() {
		if err := c.conn.Exec(ctx, ddl); err != nil {
			return fmt.Errorf("ddl step %d: %w", i, err)
		}
	}
	return nil
}

// CountTables 返回 astock 数据库中已建表数量（用于验收）。
func (c *Client) CountTables(ctx context.Context) (int, error) {
	var n uint64
	row := c.conn.QueryRow(ctx,
		"SELECT count() FROM system.tables WHERE database = ?", c.db)
	if err := row.Scan(&n); err != nil {
		return 0, err
	}
	return int(n), nil
}
