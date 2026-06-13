package sync

import (
	"context"
	"fmt"
	"time"

	"github.com/huijiecai/stock/astock/internal/dwh"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

// Block 同步全市场板块 + 成分股关系。
func Block(ctx context.Context, ch *dwh.Client, tc *tdx.Client) (int, error) {
	start := time.Now()

	blocks, cons, err := tc.ListBlocks()
	if err != nil {
		return 0, err
	}

	// 写 blocks 表
	batch, err := ch.Conn().PrepareBatch(ctx,
		fmt.Sprintf(`INSERT INTO %s.blocks (code, name, type, stock_count, updated_at)`, ch.DB()))
	if err != nil {
		return 0, fmt.Errorf("prepare batch blocks: %w", err)
	}
	for _, b := range blocks {
		if err := batch.Append(b.Code, b.Name, b.Type, b.StockCount, time.Now()); err != nil {
			return 0, fmt.Errorf("append: %w", err)
		}
	}
	if err := batch.Send(); err != nil {
		return 0, fmt.Errorf("send batch blocks: %w", err)
	}

	// 写 block_constituents 表
	batch2, err := ch.Conn().PrepareBatch(ctx,
		fmt.Sprintf(`INSERT INTO %s.block_constituents (block_code, stock_code, updated_at)`, ch.DB()))
	if err != nil {
		return 0, fmt.Errorf("prepare batch constituents: %w", err)
	}
	for _, c := range cons {
		if err := batch2.Append(c.BlockCode, c.StockCode, time.Now()); err != nil {
			return 0, fmt.Errorf("append: %w", err)
		}
	}
	if err := batch2.Send(); err != nil {
		return 0, fmt.Errorf("send batch constituents: %w", err)
	}

	total := len(blocks) + len(cons)
	_ = WriteLog(ctx, ch, &LogEntry{Task: "sync_block", Target: "all", StartAt: start, Rows: uint64(total), Status: "ok"})
	return total, nil
}
