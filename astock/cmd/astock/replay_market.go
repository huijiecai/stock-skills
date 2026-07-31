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

// buildReplayMarketCmd 构建 `astock replay market <date> [time]` 命令。
//
// 无 time：同 query market（日线终值快照）。
// 有 time：从分钟线重建到该时间点的市场快照。
// 镜像 astock live market。
func buildReplayMarketCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "market <date> [time]",
		Short: "市场全景快照（支持分钟级）",
		Long: `市场全景快照——支持分钟级。

无 time 参数返回日线终值快照（同 query market）。
有 time 参数从分钟线重建到该时间点的涨跌家数/涨停数。

注意：分钟级模式下，涨停数和涨跌停判定基于到该时间为止的分钟数据，
仅覆盖已同步分钟线的股票（通常为涨停股 + 持仓股），不是全市场。

示例：
  astock replay market 20260730             # 收盘快照
  astock replay market 20260730 10:30         # 10:30 快照
  astock replay market 20260730 --json`,
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
			excludeST, _ := cmd.Flags().GetBool("exclude-st")

			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			if hhmmss == "" {
				// 无 time：复用日线终值
				snap, err := queryMarketSnapshot(ctx, ch, date, excludeST)
				if err != nil {
					return err
				}
				if snap.TotalStocks == 0 {
					fmt.Fprintf(os.Stderr, "日期 %s 无 daily 数据（可能非交易日或未同步）\n", date)
					return nil
				}
				if isJSON(cmd) {
					enc := json.NewEncoder(os.Stdout)
					enc.SetIndent("", "  ")
					return enc.Encode(snap)
				}
				printMarketTable(snap)
				return nil
			}

			// 有 time：分钟级市场快照
			snap, err := queryReplayMarketSnapshot(ctx, ch, date, hhmmss, excludeST)
			if err != nil {
				return err
			}
			if snap.TotalStocks == 0 {
				fmt.Fprintf(os.Stderr, "日期 %s 无分钟数据（请先 replay prepare）\n", formatDate(date))
				return nil
			}

			if isJSON(cmd) {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(snap)
			}
			printReplayMarketTable(snap, timeStr)
			return nil
		},
	}
	cmd.Flags().Bool("exclude-st", false, "排除 ST/*ST 股")
	return cmd
}

// ReplayMarketSnapshot 分钟级市场快照。
type ReplayMarketSnapshot struct {
	Date           string  `json:"date"`
	Time           string  `json:"time"`
	TotalStocks    uint64  `json:"total_stocks"`
	UpCount        uint64  `json:"up_count"`
	DownCount      uint64  `json:"down_count"`
	FlatCount      uint64  `json:"flat_count"`
	LimitUpCount   uint64  `json:"limit_up_count"`
	TotalAmount    float64 `json:"total_amount"`
	IndexPrice     float64 `json:"index_price"`
	IndexChangePct float64 `json:"index_change_pct"`
}

// queryReplayMarketSnapshot 从分钟线重建到指定时间点的市场快照。
// 仅统计已同步分钟线的股票（不是全市场，是分钟线覆盖范围）。
func queryReplayMarketSnapshot(ctx context.Context, ch *dwh.Client, date, hhmmss string, excludeST bool) (*ReplayMarketSnapshot, error) {
	dateFormatted := formatDate(date)
	stFilter := ""
	if excludeST {
		stFilter = "AND s.name NOT LIKE '%ST%' AND s.name NOT LIKE 'S%ST%'"
	}

	sql := fmt.Sprintf(`
WITH joined AS (
  SELECT
    km.code AS code,
    argMax(km.close, km.dt) AS replay_close,
    kd.pre_close AS pre_close,
    argMax(km.high, km.dt) AS replay_high,
    sum(km.amount) AS amount,
    s.name AS name,
    multiIf(
      s.name LIKE '%%ST%%' OR s.name LIKE 'S%%ST%%', 0.05,
      km.code LIKE '688%%' OR km.code LIKE '689%%', 0.20,
      km.code LIKE '300%%' OR km.code LIKE '301%%', 0.20,
      km.code LIKE '43%%' OR km.code LIKE '83%%' OR km.code LIKE '87%%' OR km.code LIKE '88%%' OR km.code LIKE '920%%', 0.30,
      0.10
    ) AS pct_limit
  FROM %s.kline_minute AS km FINAL
  INNER JOIN %s.kline_daily AS kd ON km.code = kd.code AND kd.type='stock' AND kd.trade_date = toDate('%s')
  INNER JOIN %s.securities AS s ON km.code = s.code AND s.type = 'stock'
  WHERE km.type='stock' AND km.freq='1m'
    AND toDate(km.dt) = toDate('%s')
    AND km.dt <= toDateTime('%s') %s
  GROUP BY km.code, kd.pre_close, s.name
)
SELECT
  count() AS total,
  countIf(replay_close > pre_close) AS up,
  countIf(replay_close < pre_close) AS down,
  countIf(replay_close = pre_close) AS flat,
  countIf(replay_close = floor(pre_close * (1 + pct_limit) * 100 + 0.5) / 100
          AND replay_close = replay_high AND pre_close > 0) AS lu,
  sum(amount) AS amt_all
FROM joined`,
		ch.DB(), ch.DB(), dateFormatted, ch.DB(), dateFormatted,
		replayDateTime(date, hhmmss), stFilter)

	var snap ReplayMarketSnapshot
	snap.Date = dateFormatted
	snap.Time = hhmmss[:5] // "HH:MM"
	row := ch.Conn().QueryRow(ctx, sql)
	if err := row.Scan(
		&snap.TotalStocks, &snap.UpCount, &snap.DownCount, &snap.FlatCount,
		&snap.LimitUpCount, &snap.TotalAmount,
	); err != nil {
		return nil, fmt.Errorf("query replay market: %w", err)
	}

	// 取上证指数作为参考
	idxRow, err := queryReplayIndex(ctx, ch, "000001", "上证指数", date, hhmmss)
	if err == nil && idxRow != nil {
		snap.IndexPrice = idxRow.Price
		snap.IndexChangePct = idxRow.ChangePct
	}

	return &snap, nil
}

func printReplayMarketTable(s *ReplayMarketSnapshot, timeLabel string) {
	fmt.Fprintf(os.Stderr, "=== %s %s 市场快照 ===\n", s.Date, timeLabel)
	fmt.Fprintf(os.Stderr, "  覆盖: %d 只（仅已同步分钟线的股票）\n", s.TotalStocks)
	fmt.Fprintf(os.Stderr, "  涨: %d  跌: %d  平: %d  涨停: %d\n",
		s.UpCount, s.DownCount, s.FlatCount, s.LimitUpCount)
	fmt.Fprintf(os.Stderr, "  累计成交额: %s\n", formatAmount(s.TotalAmount))
	if s.IndexPrice > 0 {
		fmt.Fprintf(os.Stderr, "  上证: %.2f (%+.2f%%)\n", s.IndexPrice, s.IndexChangePct)
	}
}
