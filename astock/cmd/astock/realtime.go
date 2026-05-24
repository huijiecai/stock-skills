// astock/cmd/astock/realtime.go
package main

import (
	"context"
	"fmt"
	"strings"

	"github.com/spf13/cobra"
	"github.com/huijiecai/stock/astock/internal/model"
)

var realtimeCmd = &cobra.Command{
	Use:   "realtime <code> [code...]",
	Short: "查询实时行情",
	Long: `查询实时行情（当前最新价、涨幅、成交额等）。
支持个股、指数和概念板块，后端根据收盘时间自动判断数据源和缓存策略。
如果已收盘则读取缓存，盘中交易直接从数据源获取。

示例:
  astock realtime 002463
  astock realtime 002463 600183 300750
  astock realtime 000001 --type index
  astock realtime BK0001 --type concept`,
	Args: cobra.MinimumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		tp, _ := cmd.Flags().GetString("type")
		jsonFmt, _ := cmd.Flags().GetBool("json")

		ctx := context.Background()

		quotes, err := router.RealTimeQuote(ctx, args...)
		if err != nil {
			fmt.Fprintf(cmd.ErrOrStderr(), "Error: %v\n", err)
			return
		}

		_ = tp // type filter already handled by data source

		if jsonFmt {
			printJSON(quotes)
			return
		}

		printRealtimeTable(quotes)
	},
}

func printRealtimeTable(quotes []model.Quote) {
	if len(quotes) == 0 {
		fmt.Println("无数据")
		return
	}
	fmt.Printf("%-8s %s %s %s %s %s %s\n",
		"代码", padRight("名称", 10), padRight("最新价", 10),
		padRight("涨幅%", 8), padRight("今开", 10), padRight("昨收", 10),
		padRight("成交额", 12))
	fmt.Println(strings.Repeat("-", 68))

	for _, q := range quotes {
		change := fmt.Sprintf("%+.2f%%", q.ChangePct)
		amount := formatVolume(int64(q.Amount))
		fmt.Printf("%-8s %s %s %s %s %s %s\n",
			q.Code, padRight(truncate(q.Name, 8), 10),
			padRight(fmt.Sprintf("%.2f", q.Price), 10),
			padRight(change, 8),
			padRight(fmt.Sprintf("%.2f", q.Open), 10),
			padRight(fmt.Sprintf("%.2f", q.PreClose), 10),
			padRight(amount, 12))
	}
}

func init() {
	rootCmd.AddCommand(realtimeCmd)
	realtimeCmd.Flags().String("type", "stock", "stock / index / concept")
	realtimeCmd.Flags().Bool("json", false, "JSON 输出")
}
