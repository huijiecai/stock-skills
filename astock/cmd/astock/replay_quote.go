package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/dwh"
	"github.com/huijiecai/stock/astock/internal/model"
	ssync "github.com/huijiecai/stock/astock/internal/sync"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

// ReplayQuoteRow 是 replay quote 的单行输出。
type ReplayQuoteRow struct {
	Code      string  `json:"code"`
	Name      string  `json:"name"`
	Price     float64 `json:"price"`
	PreClose  float64 `json:"pre_close"`
	ChangePct float64 `json:"change_pct"`
	Amount    float64 `json:"amount"`
}

// buildReplayQuoteCmd 构建 `astock replay quote <codes> <date> [time]` 命令。
//
// 从个股分钟线重建指定时间点的报价。
// 如果本地没有该股票的分钟线，自动从 TDX 同步（窗口内）。
// 无 time 时返回当日收盘价。
// 镜像 astock live quote。
func buildReplayQuoteCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "quote <codes> <date> [time]",
		Short: "历史个股报价（从分钟线重建）",
		Long: `从个股分钟线重建指定时间点的报价。

无 time 参数返回当日收盘价。
有 time 参数（如 10:30）返回到该时间为止最后一根 bar 的 close。
本地无分钟线时自动从 TDX 同步（仅窗口内 ~3 个交易日）。

示例：
  astock replay quote 000021 20260730              # 收盘
  astock replay quote 000021 20260730 10:30        # 10:30
  astock replay quote 000021,000002 20260730 10:30 --json`,
		Args: cobra.MinimumNArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			codes := parseCodes(args[0])
			date, err := parseReplayDate(args[1])
			if err != nil {
				return err
			}
			timeStr := ""
			if len(args) >= 3 {
				timeStr = args[2]
			}
			hhmmss, err := parseReplayTime(timeStr)
			if err != nil {
				return err
			}

			ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			var list []*ReplayQuoteRow
			for _, code := range codes {
				row, err := queryReplayQuote(ctx, ch, code, date, hhmmss)
				if err != nil {
					fmt.Fprintf(os.Stderr, "  ✗ %s: %v\n", code, err)
					continue
				}
				if row != nil {
					list = append(list, row)
				}
			}

			if len(list) == 0 {
				fmt.Fprintf(os.Stderr, "无可用数据（请先 replay prepare 或检查代码/日期）\n")
				return nil
			}

			if isJSON(cmd) {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(list)
			}

			for _, r := range list {
				fmt.Printf("---- %s %s ----\n", r.Code, r.Name)
				fmt.Printf("现价: %.2f  昨收: %.2f  涨跌: %+.2f%%  成交额: %s\n\n",
					r.Price, r.PreClose, r.ChangePct, formatAmount(r.Amount))
			}
			return nil
		},
	}
	return cmd
}

// queryReplayQuote 从 kline_minute + kline_daily 重建指定时间点的个股报价。
// 本地无分钟线时自动从 TDX 同步（窗口内）。
func queryReplayQuote(ctx context.Context, ch *dwh.Client, code, date, hhmmss string) (*ReplayQuoteRow, error) {
	dateFormatted := formatDate(date)

	// 1. 取 pre_close + name 从 daily + securities
	var name string
	var preClose float64
	err := ch.Conn().QueryRow(ctx, fmt.Sprintf(`
SELECT s.name, k.pre_close
FROM %s.kline_daily AS k FINAL
INNER JOIN %s.securities AS s FINAL ON k.code = s.code AND s.type = 'stock'
WHERE k.code = '%s' AND k.type = 'stock' AND k.trade_date = toDate('%s')`,
		ch.DB(), ch.DB(), code, dateFormatted)).Scan(&name, &preClose)
	if err != nil {
		return nil, fmt.Errorf("daily: %w", err)
	}

	// 2. 取分钟线
	var minuteSQL string
	if hhmmss == "" {
		minuteSQL = fmt.Sprintf(`
SELECT close, amount FROM %s.kline_minute FINAL
WHERE code='%s' AND type='stock' AND freq='1m'
  AND toDate(dt)=toDate('%s')
ORDER BY dt DESC LIMIT 1`, ch.DB(), code, dateFormatted)
	} else {
		minuteSQL = fmt.Sprintf(`
SELECT argMax(close, dt), sum(amount) FROM %s.kline_minute FINAL
WHERE code='%s' AND type='stock' AND freq='1m'
  AND toDate(dt)=toDate('%s') AND dt <= toDateTime('%s')`,
			ch.DB(), code, dateFormatted, replayDateTime(date, hhmmss))
	}

	var price, amount float64
	err = ch.Conn().QueryRow(ctx, minuteSQL).Scan(&price, &amount)

	// 3. 无分钟线数据 → 自动同步
	if err != nil || price == 0 {
		// 检查是否在 TDX 窗口内
		if ok, reason := canAutoSync("minute", "1m", date, ""); ok {
			fmt.Fprintf(os.Stderr, "⚠ 本地无 %s 分钟线，自动 sync...\n", code)
			tc := tdx.New()
			defer tc.Close()
			_, sErr := ssync.Minute(ctx, ch, tc, code, model.TypeStock, model.Freq1m, 800)
			if sErr != nil {
				return nil, fmt.Errorf("auto sync: %w", sErr)
			}
			// 重查
			err = ch.Conn().QueryRow(ctx, minuteSQL).Scan(&price, &amount)
			if err != nil || price == 0 {
				return nil, nil // sync 后仍无数据
			}
		} else {
			fmt.Fprintf(os.Stderr, "⚠ %s 无分钟线数据（%s）\n", code, reason)
			return nil, nil
		}
	}

	changePct := 0.0
	if preClose > 0 {
		changePct = (price - preClose) / preClose * 100
	}

	return &ReplayQuoteRow{
		Code:      code,
		Name:      name,
		Price:     price,
		PreClose:  preClose,
		ChangePct: changePct,
		Amount:    amount,
	}, nil
}
