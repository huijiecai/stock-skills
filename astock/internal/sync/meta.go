package sync

import (
	"context"
	"fmt"
	"time"

	"github.com/huijiecai/stock/astock/internal/dwh"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

// Meta 同步全市场标的列表（stock + index）到 securities 表。
// 因为 ReplacingMergeTree 按 (type, market, code) 去重，可以每次全量覆盖写。
func Meta(ctx context.Context, ch *dwh.Client, tc *tdx.Client) (int, error) {
	start := time.Now()

	secs, err := tc.ListSecurities()
	if err != nil {
		return 0, err
	}
	if len(secs) == 0 {
		return 0, fmt.Errorf("no securities fetched")
	}

	// 批量写入（clickhouse-go batch 方式）
	batch, err := ch.Conn().PrepareBatch(ctx,
		fmt.Sprintf(`INSERT INTO %s.securities (code, market, type, name, list_date, delist_date, updated_at)`, ch.DB()))
	if err != nil {
		return 0, fmt.Errorf("prepare batch: %w", err)
	}
	for _, s := range secs {
		if err := batch.Append(s.Code, s.Market, string(s.Type), s.Name, s.ListDate, nil, time.Now()); err != nil {
			return 0, fmt.Errorf("append: %w", err)
		}
	}
	if err := batch.Send(); err != nil {
		return 0, fmt.Errorf("send batch: %w", err)
	}

	n := len(secs)
	_ = WriteLog(ctx, ch, &LogEntry{Task: "sync_meta", Target: "securities", StartAt: start, Rows: uint64(n), Status: "ok"})
	return n, nil
}
