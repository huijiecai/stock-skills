package tdx

import (
	"fmt"
	"time"

	"github.com/huijiecai/stock/astock/internal/model"
)

// GetSecurityListDate reads the IPO date carried by TDX's finance snapshot.
// It is intentionally used only for newly discovered stocks; calling it for
// the full market would turn a metadata refresh into thousands of requests.
func (c *Client) GetSecurityListDate(market, code string) (time.Time, error) {
	info, err := c.GetFinanceInfo(market, code)
	if err == nil && info != nil {
		date := parseTdxDate(info.IPODate)
		if !date.IsZero() {
			return date, nil
		}
	}

	// 极新股的财务快照有时尚未填 IPODate；最近 800 根日 K 足以覆盖
	// 新股上市初期，并且首根交易日就是可用的上市日期兜底。
	bars, klineErr := c.GetKlineDay(code, model.TypeStock, 800)
	if klineErr == nil {
		var first time.Time
		for _, bar := range bars {
			if bar.Time.IsZero() || (!first.IsZero() && !bar.Time.Before(first)) {
				continue
			}
			first = bar.Time
		}
		if !first.IsZero() {
			return first, nil
		}
	}
	return time.Time{}, fmt.Errorf("TDX 未返回有效上市日期（finance=%v, kline=%v）", err, klineErr)
}
