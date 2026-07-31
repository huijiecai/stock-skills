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

// ReplayCheckResult 是 replay check 的 JSON 输出结构。
type ReplayCheckResult struct {
	Date        string   `json:"date"`
	Ready       bool     `json:"ready"`
	Prepared    bool     `json:"prepared"` // sync_log 中有 replay_prepare 记录
	Checks      []string `json:"checks"`   // 通过的检查项
	Missing     []string `json:"missing"`  // 缺失项
	IndexCount  int      `json:"index_count"`
	BlockCount  int      `json:"block_count"`
	StockCount  int      `json:"stock_count"`
	ActiveCount int      `json:"active_count"` // 活跃股数（涨停/跌停/炸板/大成交额）
}

// buildReplayCheckCmd 构建 `astock replay check <date>` 命令。
//
// 检查指定日期的 replay 数据是否完整：
//  1. sync_log 中是否有 replay_prepare 记录
//  2. 指数 daily + 1m 是否有数据
//  3. 板块 daily + 1m 是否有数据
//  4. 股票 daily 是否有数据
//  5. 涨停股 1m 是否有数据
func buildReplayCheckCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "check <date>",
		Short: "检查指定日期的 replay 数据完整性",
		Long: `检查指定日期的 replay 数据是否完整。

示例：
  astock replay check 20260730
  astock replay check 20260730 --json`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			date, err := parseReplayDate(args[0])
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

			result := ReplayCheckResult{Date: formatDate(date)}

			// 1. 检查 sync_log
			var prepareRows uint64
			ch.Conn().QueryRow(ctx, fmt.Sprintf(
				"SELECT count() FROM %s.sync_log WHERE task='replay_prepare' AND target='%s' AND status='ok'",
				ch.DB(), date)).Scan(&prepareRows)
			result.Prepared = prepareRows > 0

			// 2. 指数 daily
			var idxDailyCount uint64
			ch.Conn().QueryRow(ctx, fmt.Sprintf(
				"SELECT count() FROM %s.kline_daily WHERE type='index' AND trade_date=toDate('%s')",
				ch.DB(), formatDate(date))).Scan(&idxDailyCount)

			// 3. 指数 1m
			var idxMinuteCount uint64
			ch.Conn().QueryRow(ctx, fmt.Sprintf(
				"SELECT count(DISTINCT code) FROM %s.kline_minute WHERE type='index' AND freq='1m' AND toDate(dt)=toDate('%s')",
				ch.DB(), formatDate(date))).Scan(&idxMinuteCount)
			result.IndexCount = int(idxMinuteCount)

			// 4. 板块 daily
			var blkDailyCount uint64
			ch.Conn().QueryRow(ctx, fmt.Sprintf(
				"SELECT count() FROM %s.kline_daily WHERE type='block' AND trade_date=toDate('%s')",
				ch.DB(), formatDate(date))).Scan(&blkDailyCount)

			// 5. 板块 1m
			var blkMinuteCount uint64
			ch.Conn().QueryRow(ctx, fmt.Sprintf(
				"SELECT count(DISTINCT code) FROM %s.kline_minute WHERE type='block' AND freq='1m' AND toDate(dt)=toDate('%s')",
				ch.DB(), formatDate(date))).Scan(&blkMinuteCount)
			result.BlockCount = int(blkMinuteCount)

			// 6. 股票 daily
			var stockCount uint64
			ch.Conn().QueryRow(ctx, fmt.Sprintf(
				"SELECT count() FROM %s.kline_daily WHERE type='stock' AND trade_date=toDate('%s')",
				ch.DB(), formatDate(date))).Scan(&stockCount)
			result.StockCount = int(stockCount)

			// 7. 活跃股数（涨停/跌停/炸板/大成交额，最近3天）
			activeCodes, _ := identifyReplayMinuteStocks(ctx, ch, date)
			result.ActiveCount = len(activeCodes)

			// 8. 活跃股 1m
			var stockMinuteCount uint64
			if len(activeCodes) > 0 {
				ch.Conn().QueryRow(ctx, fmt.Sprintf(
					"SELECT count(DISTINCT code) FROM %s.kline_minute WHERE type='stock' AND freq='1m' AND toDate(dt)=toDate('%s')",
					ch.DB(), formatDate(date))).Scan(&stockMinuteCount)
			}

			// 汇总检查
			if idxDailyCount > 0 {
				result.Checks = append(result.Checks, "index_daily")
			} else {
				result.Missing = append(result.Missing, "index_daily")
			}
			if idxMinuteCount > 0 {
				result.Checks = append(result.Checks, "index_minute")
			} else {
				result.Missing = append(result.Missing, "index_minute")
			}
			if blkDailyCount > 0 {
				result.Checks = append(result.Checks, "block_daily")
			} else {
				result.Missing = append(result.Missing, "block_daily")
			}
			if blkMinuteCount > 0 {
				result.Checks = append(result.Checks, "block_minute")
			} else {
				result.Missing = append(result.Missing, "block_minute")
			}
			if stockCount > 1000 {
				result.Checks = append(result.Checks, "stock_daily")
			} else {
				result.Missing = append(result.Missing, "stock_daily")
			}
			if result.ActiveCount > 0 && int(stockMinuteCount) >= result.ActiveCount {
				result.Checks = append(result.Checks, "active_minute")
			} else if result.ActiveCount > 0 {
				result.Missing = append(result.Missing, "active_minute")
			}
			result.Ready = len(result.Missing) == 0

			if isJSON(cmd) {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(result)
			}

			status := "✅ 就绪"
			if !result.Ready {
				status = "❌ 数据不完整"
			}
			fmt.Fprintf(os.Stderr, "replay check %s: %s\n", formatDate(date), status)
			fmt.Fprintf(os.Stderr, "  prepare: %v\n", result.Prepared)
			fmt.Fprintf(os.Stderr, "  指数 1m: %d 只\n", result.IndexCount)
			fmt.Fprintf(os.Stderr, "  板块 1m: %d 只\n", result.BlockCount)
			fmt.Fprintf(os.Stderr, "  股票 daily: %d 行\n", result.StockCount)
			fmt.Fprintf(os.Stderr, "  活跃股: %d 只（涨停/跌停/炸板/大成交额）\n", result.ActiveCount)
			if len(result.Missing) > 0 {
				fmt.Fprintf(os.Stderr, "  缺失: %v\n", result.Missing)
				fmt.Fprintf(os.Stderr, "  → 请先执行: astock replay prepare %s\n", date)
			}
			return nil
		},
	}
	return cmd
}
