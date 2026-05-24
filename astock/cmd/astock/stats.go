// astock/cmd/astock/stats.go
package main

import (
	"context"
	"fmt"

	"github.com/spf13/cobra"
	"github.com/huijiecai/stock/astock/internal/db"
)

type dbStats struct {
	DailyKCount  int
	MinuteKCount int
	StockCount   int
	ConceptCount int
	EarliestDate string
	LatestDate   string
}

var statsCmd = &cobra.Command{
	Use:   "stats",
	Short: "数据概况统计",
	Run: func(cmd *cobra.Command, args []string) {
		jsonFmt, _ := cmd.Flags().GetBool("json")
		ctx := context.Background()

		var s dbStats
		db.Pool.QueryRow(ctx, "SELECT COUNT(*) FROM daily_k").Scan(&s.DailyKCount)
		db.Pool.QueryRow(ctx, "SELECT COUNT(*) FROM minute_k").Scan(&s.MinuteKCount)
		db.Pool.QueryRow(ctx, "SELECT COUNT(*) FROM stock_info").Scan(&s.StockCount)
		db.Pool.QueryRow(ctx, "SELECT COUNT(*) FROM concept_info").Scan(&s.ConceptCount)

		db.Pool.QueryRow(ctx,
			"SELECT COALESCE(MIN(trade_date)::text, '-') FROM daily_k").Scan(&s.EarliestDate)
		db.Pool.QueryRow(ctx,
			"SELECT COALESCE(MAX(trade_date)::text, '-') FROM daily_k").Scan(&s.LatestDate)

		if jsonFmt {
			printJSON(s)
		} else {
			fmt.Printf("股票总数:     %d\n", s.StockCount)
			fmt.Printf("概念板块数:   %d\n", s.ConceptCount)
			fmt.Printf("日K 记录数:   %d\n", s.DailyKCount)
			fmt.Printf("分钟K 记录数: %d\n", s.MinuteKCount)
			fmt.Printf("日K 日期范围: %s ~ %s\n", s.EarliestDate, s.LatestDate)
		}
	},
}

func init() {
	rootCmd.AddCommand(statsCmd)
	statsCmd.Flags().Bool("json", false, "JSON 输出")
}
