package sync

import (
	"context"
	"fmt"
	"time"

	"github.com/huijiecai/stock/astock/internal/dwh"
	"github.com/huijiecai/stock/astock/internal/model"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

// Daily 同步日 K 线到 kline_daily 表。
// dataType 决定 TDX 路由（stock vs index），仅在单 code 模式下使用；
// all 模式下按 securities 表实际 type 字段分发，dataType 参数被忽略。
func Daily(ctx context.Context, ch *dwh.Client, tc *tdx.Client, code string, dataType model.DataType, all bool, count uint16) (int, error) {
	start := time.Now()
	var total int

	if code != "" {
		if dataType == "" {
			dataType = model.TypeStock
		}
		n, err := syncDailyOne(ctx, ch, tc, code, dataType, count)
		if err != nil {
			return 0, err
		}
		total = n
	} else if all {
		codes, err := listStockCodes(ctx, ch)
		if err != nil {
			return 0, err
		}
		for _, sc := range codes {
			n, err := syncDailyOne(ctx, ch, tc, sc.Code, sc.Type, count)
			if err != nil {
				fmt.Printf("  ⚠ %s failed: %v\n", sc.Code, err)
				continue
			}
			total += n
		}
	}

	_ = WriteLog(ctx, ch, &LogEntry{Task: "sync_daily", Target: code, StartAt: start, Rows: uint64(total), Status: "ok"})
	return total, nil
}

func syncDailyOne(ctx context.Context, ch *dwh.Client, tc *tdx.Client, code string, dataType model.DataType, count uint16) (int, error) {
	var bars []*model.Bar
	var err error
	if count == 0 {
		bars, err = tc.GetKlineDayAll(code, dataType)
	} else {
		bars, err = tc.GetKlineDay(code, dataType, count)
	}
	if err != nil {
		return 0, err
	}
	if len(bars) == 0 {
		return 0, nil
	}

	batch, err := ch.Conn().PrepareBatch(ctx,
		fmt.Sprintf(`INSERT INTO %s.kline_daily (code, type, trade_date, open, high, low, close, pre_close, volume, amount, turnover)`, ch.DB()))
	if err != nil {
		return 0, fmt.Errorf("prepare batch: %w", err)
	}
	for _, b := range bars {
		td, _ := time.Parse("2006-01-02", b.TradeDate)
		if err := batch.Append(b.Code, string(b.Type), td, b.Open, b.High, b.Low, b.Close, b.PreClose, uint64(b.Volume), b.Amount, float32(b.Turnover)); err != nil {
			return 0, fmt.Errorf("append: %w", err)
		}
	}
	if err := batch.Send(); err != nil {
		return 0, fmt.Errorf("send batch: %w", err)
	}
	return len(bars), nil
}

// XDXR 同步除权除息到 xdxr 表。
func XDXR(ctx context.Context, ch *dwh.Client, tc *tdx.Client, code string, all bool) (int, error) {
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

// stockInfo 用于遍历 securities 表。
type stockInfo struct {
	Code string
	Type model.DataType
}

// listStockCodes 从 CH securities 表读取全部 stock+index 代码列表。
func listStockCodes(ctx context.Context, ch *dwh.Client) ([]stockInfo, error) {
	rows, err := ch.Conn().Query(ctx,
		fmt.Sprintf(`SELECT code, type FROM %s.securities FINAL WHERE type IN ('stock','index') ORDER BY code`, ch.DB()))
	if err != nil {
		return nil, fmt.Errorf("query securities: %w", err)
	}
	defer rows.Close()

	var out []stockInfo
	for rows.Next() {
		var code, typ string
		if err := rows.Scan(&code, &typ); err != nil {
			return nil, err
		}
		out = append(out, stockInfo{Code: code, Type: model.DataType(typ)})
	}
	return out, nil
}

// dataTypeForCode 已删除：默认 stock 由 CLI 层 --type 参数显式控制，避免
// 000001（平安银行 vs 上证综指）等代码段歧义被自动推断到错误通道。
