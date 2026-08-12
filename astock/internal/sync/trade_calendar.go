package sync

import (
	"context"
	"fmt"

	"github.com/huijiecai/stock/astock/internal/dwh"
)

// RefreshTradeCalendarFromDaily rebuilds the open-day calendar from stored
// index daily bars. An index bar is only present on an actual market session,
// so this avoids introducing a second external calendar source.
//
// The operation is idempotent: only dates not already marked open are inserted.
func RefreshTradeCalendarFromDaily(ctx context.Context, ch *dwh.Client) (inserted, total int, err error) {
	var sourceDates uint64
	if err := ch.Conn().QueryRow(ctx, fmt.Sprintf(`
SELECT countDistinct(trade_date)
FROM %s.kline_daily FINAL
WHERE type = 'index'`, ch.DB())).Scan(&sourceDates); err != nil {
		return 0, 0, fmt.Errorf("count index trading dates: %w", err)
	}
	if sourceDates == 0 {
		return 0, 0, nil
	}

	var before uint64
	if err := ch.Conn().QueryRow(ctx, fmt.Sprintf(
		"SELECT countDistinct(trade_date) FROM %s.trade_cal FINAL WHERE is_open = 1", ch.DB()),
	).Scan(&before); err != nil {
		return 0, 0, fmt.Errorf("count existing trading dates: %w", err)
	}

	err = ch.Conn().Exec(ctx, fmt.Sprintf(`
INSERT INTO %s.trade_cal (trade_date, is_open)
SELECT DISTINCT trade_date, toUInt8(1)
FROM %s.kline_daily FINAL
WHERE type = 'index'
  AND trade_date NOT IN (
    SELECT trade_date FROM %s.trade_cal FINAL WHERE is_open = 1
  )`, ch.DB(), ch.DB(), ch.DB()))
	if err != nil {
		return 0, 0, fmt.Errorf("insert trade calendar: %w", err)
	}

	var after uint64
	if err := ch.Conn().QueryRow(ctx, fmt.Sprintf(
		"SELECT countDistinct(trade_date) FROM %s.trade_cal FINAL WHERE is_open = 1", ch.DB()),
	).Scan(&after); err != nil {
		return 0, 0, fmt.Errorf("count refreshed trading dates: %w", err)
	}
	return int(after - before), int(after), nil
}
