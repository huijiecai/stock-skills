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
func Minute(ctx context.Context, ch *dwh.Client, tc *tdx.Client, code string, freq model.Freq, count uint16) (int, error) {
	start := time.Now()
	dataType := dataTypeForCode(code)

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

	_ = WriteLog(ctx, ch, &LogEntry{Task: "sync_minute", Target: code, StartAt: start, Rows: uint64(len(bars)), Status: "ok"})
	return len(bars), nil
}

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

// Finance 同步财务数据到 finance 表。
// all=true → 遍历全部 stock；否则只做 code 一只。
func Finance(ctx context.Context, ch *dwh.Client, tc *tdx.Client, code string, all bool) (int, error) {
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

	for _, sc := range codes {
		if sc.Type != model.TypeStock {
			continue
		}
		market := tdx.MarketOf(sc.Code)
		if market == "" {
			continue
		}
		f, err := tc.GetFinance(market, sc.Code)
		if err != nil {
			fmt.Printf("  ⚠ finance %s failed: %v\n", sc.Code, err)
			continue
		}
		if f == nil || f.ReportDate.IsZero() {
			continue
		}

		batch, err := ch.Conn().PrepareBatch(ctx,
			fmt.Sprintf(`INSERT INTO %s.finance (code, report_date, revenue, net_profit, eps, bps, roe, total_share, float_share, total_assets, total_liability, updated_at)`, ch.DB()))
		if err != nil {
			return total, fmt.Errorf("prepare batch: %w", err)
		}
		if err := batch.Append(f.Code, f.ReportDate, f.Revenue, f.NetProfit, f.EPS, f.BPS, f.ROE, f.TotalShare, f.FloatShare, f.TotalAssets, f.TotalLiability, time.Now()); err != nil {
			return total, fmt.Errorf("append: %w", err)
		}
		if err := batch.Send(); err != nil {
			return total, fmt.Errorf("send batch: %w", err)
		}
		total++
	}

	_ = WriteLog(ctx, ch, &LogEntry{Task: "sync_finance", Target: code, StartAt: start, Rows: uint64(total), Status: "ok"})
	return total, nil
}
