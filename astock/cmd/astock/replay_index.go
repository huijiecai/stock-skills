package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/dwh"
)

// ReplayIndexRow 是 replay index 的单行输出。
type ReplayIndexRow struct {
	Code      string  `json:"code"`
	Name      string  `json:"name"`
	Price     float64 `json:"price"`
	PreClose  float64 `json:"pre_close"`
	ChangePct float64 `json:"change_pct"`
	Amount    float64 `json:"amount"`
}

// buildReplayIndexCmd 构建 `astock replay index <date> [time]` 命令。
//
// 从指数分钟线重建指定时间点的指数报价。
// 无 time 时返回当日最后一根 bar（收盘）。
// 镜像 astock live index。
func buildReplayIndexCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "index <date> [time]",
		Short: "历史指数报价（从分钟线重建）",
		Long: `从指数分钟线重建指定时间点的指数报价。

无 time 参数返回当日最后一根 bar（收盘）。
有 time 参数（如 10:30）返回到该时间为止最后一根 bar 的 close。

示例：
  astock replay index 20260730             # 收盘
  astock replay index 20260730 10:30       # 10:30 时点
  astock replay index 20260730 --json`,
		Args: cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			date, err := parseReplayDate(args[0])
			if err != nil {
				return err
			}
			timeStr := ""
			if len(args) >= 2 {
				timeStr = args[1]
			}
			hhmmss, err := parseReplayTime(timeStr)
			if err != nil {
				return err
			}

			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			var list []*ReplayIndexRow
			for _, idx := range marketIndexCodes {
				row, err := queryReplayIndex(ctx, ch, idx.code, idx.name, date, hhmmss)
				if err != nil {
					fmt.Fprintf(os.Stderr, "  ✗ %s: %v\n", idx.code, err)
					continue
				}
				if row != nil {
					list = append(list, row)
				}
			}

			if len(list) == 0 {
				fmt.Fprintf(os.Stderr, "日期 %s 无指数分钟线数据（请先 replay prepare）\n", formatDate(date))
				return nil
			}

			if isJSON(cmd) {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(list)
			}

			t := newTable("代码", 8, "名称", 10, "现价", 10, "昨收", 10, "涨跌%", 8, "成交额", 12)
			for _, r := range list {
				t.Row(r.Code, r.Name,
					fmt.Sprintf("%.2f", r.Price),
					fmt.Sprintf("%.2f", r.PreClose),
					fmt.Sprintf("%+.2f%%", r.ChangePct),
					formatAmount(r.Amount))
			}
			t.Print()
			return nil
		},
	}
	return cmd
}

// queryReplayIndex 从 kline_minute + kline_daily 重建指定时间点的指数报价。
func queryReplayIndex(ctx context.Context, ch *dwh.Client, code, name, date, hhmmss string) (*ReplayIndexRow, error) {
	dateFormatted := formatDate(date)

	// 1. 取 pre_close 从 daily
	var preClose float64
	err := ch.Conn().QueryRow(ctx, fmt.Sprintf(
		"SELECT pre_close FROM %s.kline_daily FINAL WHERE code='%s' AND type='index' AND trade_date=toDate('%s')",
		ch.DB(), code, dateFormatted)).Scan(&preClose)
	if err != nil {
		return nil, fmt.Errorf("index daily pre_close: %w", err)
	}

	// 2. 取到指定时间为止的最后一根 bar + 累计成交额
	var minuteSQL string
	if hhmmss == "" {
		// 无 time：取当日最后一根 bar
		minuteSQL = fmt.Sprintf(`
SELECT close, amount FROM %s.kline_minute FINAL
WHERE code='%s' AND type='index' AND freq='1m'
  AND toDate(dt)=toDate('%s')
ORDER BY dt DESC LIMIT 1`, ch.DB(), code, dateFormatted)
	} else {
		// 有 time：取到该时间为止最后一根 bar + 累计成交额
		minuteSQL = fmt.Sprintf(`
SELECT argMax(close, dt), sum(amount) FROM %s.kline_minute FINAL
WHERE code='%s' AND type='index' AND freq='1m'
  AND toDate(dt)=toDate('%s') AND dt <= toDateTime('%s')`,
			ch.DB(), code, dateFormatted, replayDateTime(date, hhmmss))
	}

	var price, amount float64
	if hhmmss == "" {
		err = ch.Conn().QueryRow(ctx, minuteSQL).Scan(&price, &amount)
	} else {
		err = ch.Conn().QueryRow(ctx, minuteSQL).Scan(&price, &amount)
	}
	if err != nil {
		return nil, fmt.Errorf("index minute: %w", err)
	}
	if price == 0 {
		return nil, nil // 无分钟线数据
	}

	changePct := 0.0
	if preClose > 0 {
		changePct = (price - preClose) / preClose * 100
	}

	return &ReplayIndexRow{
		Code:      code,
		Name:      name,
		Price:     price,
		PreClose:  preClose,
		ChangePct: changePct,
		Amount:    amount,
	}, nil
}
