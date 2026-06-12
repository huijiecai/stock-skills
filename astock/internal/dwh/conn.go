package dwh

import (
	"context"
	"fmt"
	"time"

	"github.com/ClickHouse/clickhouse-go/v2"
	"github.com/ClickHouse/clickhouse-go/v2/lib/driver"

	"github.com/huijiecai/stock/astock/internal/config"
)

// Client 是 ClickHouse 数据仓库的薄封装。
// 包装 driver.Conn 提供项目级别的工具方法（建表、批量写入、统计等）。
type Client struct {
	conn driver.Conn
	db   string
}

// New 用配置打开一个 CH 连接（原生协议）。
func New(ctx context.Context, cfg *config.Config) (*Client, error) {
	conn, err := clickhouse.Open(&clickhouse.Options{
		Addr: []string{cfg.CHAddr()},
		Auth: clickhouse.Auth{
			Database: "default", // 先连 default，建库后再切
			Username: cfg.CHUser,
			Password: cfg.CHPassword,
		},
		Settings: clickhouse.Settings{
			"max_execution_time": 600,
		},
		DialTimeout: 5 * time.Second,
		ReadTimeout: 60 * time.Second,
	})
	if err != nil {
		return nil, fmt.Errorf("open clickhouse: %w", err)
	}
	if err := conn.Ping(ctx); err != nil {
		return nil, fmt.Errorf("ping clickhouse: %w", err)
	}
	return &Client{conn: conn, db: cfg.CHDatabase}, nil
}

// Conn 暴露底层连接，供其他子包做 SELECT/INSERT。
func (c *Client) Conn() driver.Conn { return c.conn }

// DB 返回数据库名。
func (c *Client) DB() string { return c.db }

// Close 关闭连接。
func (c *Client) Close() error { return c.conn.Close() }

// Exec 直接执行一段 DDL/DML，无返回行。
func (c *Client) Exec(ctx context.Context, query string, args ...any) error {
	return c.conn.Exec(ctx, query, args...)
}

// Version 返回 CH 服务端版本，用于健康检查。
func (c *Client) Version(ctx context.Context) (string, error) {
	var v string
	row := c.conn.QueryRow(ctx, "SELECT version()")
	if err := row.Scan(&v); err != nil {
		return "", err
	}
	return v, nil
}
