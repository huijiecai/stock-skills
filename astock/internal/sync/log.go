// Package sync 负责把 TDX 数据写入 ClickHouse。
// 每个子命令（meta/daily/minute/xdxr/block/finance）对应一个 func(ctx, dwh.Client, tdx.Client) error。
package sync

import (
	"context"
	"fmt"
	"time"

	"github.com/huijiecai/stock/astock/internal/dwh"
)

// LogEntry 是一条 sync_log 记录。
type LogEntry struct {
	Task    string
	Target  string
	StartAt time.Time
	Rows    uint64
	Status  string // "ok" / "error"
	ErrMsg  string
}

// WriteLog 写入一条 sync_log。
func WriteLog(ctx context.Context, ch *dwh.Client, e *LogEntry) error {
	q := fmt.Sprintf(`INSERT INTO %s.sync_log (task, target, start_at, end_at, rows, status, err_msg) VALUES (?, ?, ?, ?, ?, ?, ?)`, ch.DB())
	return ch.Exec(ctx, q, e.Task, e.Target, e.StartAt, time.Now(), e.Rows, e.Status, e.ErrMsg)
}
