package sync

import (
	"context"
	"fmt"
	"time"

	"github.com/huijiecai/stock/astock/internal/dwh"
	"github.com/huijiecai/stock/astock/internal/model"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

// Minute 同步分钟 K 线到 kline_minute 表。
// 每次从 TDX 拉最近 count 根（≤800），覆盖写入（ReplacingMergeTree 去重）。
// dataType 决定 TDX 路由（stock vs index），由 CLI --type 显式传入。
func Minute(ctx context.Context, ch *dwh.Client, tc *tdx.Client, code string, dataType model.DataType, freq model.Freq, count uint16) (int, error) {
	start := time.Now()
	if dataType == "" {
		dataType = model.TypeStock
	}

	bars, err := tc.GetKlineMinute(code, dataType, freq, count)
	if err != nil {
		return 0, err
	}
	if len(bars) == 0 {
		return 0, nil
	}

	batch, err := ch.Conn().PrepareBatch(ctx,
		fmt.Sprintf(`INSERT INTO %s.kline_minute (code, type, freq, dt, open, high, low, close, volume, amount)`, ch.DB()))
	if err != nil {
		return 0, fmt.Errorf("prepare batch: %w", err)
	}
	for _, b := range bars {
		if err := batch.Append(b.Code, string(b.Type), string(b.Freq), b.Time, b.Open, b.High, b.Low, b.Close, uint64(b.Volume), b.Amount); err != nil {
			return 0, fmt.Errorf("append: %w", err)
		}
	}
	if err := batch.Send(); err != nil {
		return 0, fmt.Errorf("send batch: %w", err)
	}

	_ = WriteLog(ctx, ch, &LogEntry{Task: "sync_kline_minute", Target: code, StartAt: start, Rows: uint64(len(bars)), Status: "ok"})
	return len(bars), nil
}
