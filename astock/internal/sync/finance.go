package sync

import (
	"context"
	"fmt"
	"time"

	"github.com/huijiecai/stock/astock/internal/dwh"
	"github.com/huijiecai/stock/astock/internal/model"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

// Finance 同步财务数据到 finance 表。
// all=true → 遍历全部 stock；否则只做 code 一只。
func Finance(ctx context.Context, ch *dwh.Client, tc *tdx.Client, code string, all bool, progress func(i, total int, code string)) (int, error) {
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
