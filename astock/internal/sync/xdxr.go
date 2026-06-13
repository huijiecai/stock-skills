package sync

import (
	"context"
	"fmt"
	"time"

	"github.com/huijiecai/stock/astock/internal/dwh"
	"github.com/huijiecai/stock/astock/internal/model"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

// XDXR 同步除权除息到 xdxr 表。
// progress 可选：--all 路径下每只股处理前回调，供 CLI 层打进度。
func XDXR(ctx context.Context, ch *dwh.Client, tc *tdx.Client, code string, all bool, progress func(i, total int, code string)) (int, error) {
	start := time.Now()
	var total int

	codes := []stockInfo{{Code: code, Type: model.TypeStock}}
	if all {
		var err error
		codes, err = listStockCodes(ctx, ch)
		if err != nil {
			return 0, err
		}
	}

	for i, sc := range codes {
		if progress != nil {
			progress(i, len(codes), sc.Code)
		}
		if sc.Type != model.TypeStock {
			continue
		}
		items, err := tc.GetXDXR(sc.Code)
		if err != nil {
			fmt.Printf("  ⚠ xdxr %s failed: %v\n", sc.Code, err)
			continue
		}
		if len(items) == 0 {
			continue
		}

		batch, err := ch.Conn().PrepareBatch(ctx,
			fmt.Sprintf(`INSERT INTO %s.xdxr (code, ex_date, type, bonus, transfer, dividend, rights_price, rights_ratio, updated_at)`, ch.DB()))
		if err != nil {
			return total, fmt.Errorf("prepare batch: %w", err)
		}
		for _, x := range items {
			if err := batch.Append(x.Code, x.ExDate, x.Type, x.Bonus, x.Transfer, x.Dividend, x.RightsPrice, x.RightsRatio, time.Now()); err != nil {
				return total, fmt.Errorf("append: %w", err)
			}
		}
		if err := batch.Send(); err != nil {
			return total, fmt.Errorf("send batch: %w", err)
		}
		total += len(items)
	}

	_ = WriteLog(ctx, ch, &LogEntry{Task: "sync_xdxr", Target: code, StartAt: start, Rows: uint64(total), Status: "ok"})
	return total, nil
}
