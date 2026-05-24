// astock/cmd/astock/rank.go
package main

import (
	"context"
	"fmt"
	"strings"

	"github.com/spf13/cobra"
	"github.com/huijiecai/stock/astock/internal/model"
)

var rankCmd = &cobra.Command{
	Use:   "rank {volume|limit-up}",
	Short: "查询排名（成交额TOP30 / 涨停天梯）",
	Args:  cobra.ExactArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		sub := args[0]
		jsonFmt, _ := cmd.Flags().GetBool("json")

		ctx := context.Background()
		switch sub {
		case "volume":
			quotes, err := router.RankVolume(ctx, 30)
			if err != nil {
				fmt.Fprintf(cmd.ErrOrStderr(), "Error: %v\n", err)
				return
			}
			if jsonFmt {
				printJSON(quotes)
			} else {
				printRankTable(quotes, "成交额 TOP30")
			}

		case "limit-up":
			quotes, err := router.RankLimitUp(ctx)
			if err != nil {
				fmt.Fprintf(cmd.ErrOrStderr(), "Error: %v\n", err)
				return
			}
			if jsonFmt {
				printJSON(quotes)
			} else {
				printRankTable(quotes, "涨停天梯")
			}

		default:
			fmt.Fprintf(cmd.ErrOrStderr(), "unknown rank type: %s (volume|limit-up)\n", sub)
		}
	},
}

func printRankTable(quotes []model.Quote, title string) {
	if len(quotes) == 0 {
		fmt.Println("无数据")
		return
	}
	fmt.Printf("=== %s ===\n\n", title)
	fmt.Printf("%-4s %-8s %-10s %-10s %-8s %-12s\n",
		"#", "代码", "名称", "最新价", "涨幅%", "成交额")
	fmt.Println(strings.Repeat("-", 60))

	for i, q := range quotes {
		amount := formatAmount(q.Amount)
		change := fmt.Sprintf("%+.2f%%", q.ChangePct)
		fmt.Printf("%-4d %-8s %-10s %-10.2f %-8s %-12s\n",
			i+1, q.Code, truncate(q.Name, 8), q.Price, change, amount)
	}
}

func formatAmount(v float64) string {
	if v > 10_000_000_000 {
		return fmt.Sprintf("%.2f亿", v/100_000_000)
	}
	if v > 10_000 {
		return fmt.Sprintf("%.2f万", v/10_000)
	}
	return fmt.Sprintf("%.2f", v)
}

func truncate(s string, n int) string {
	runes := []rune(s)
	if len(runes) <= n {
		return s
	}
	return string(runes[:n]) + "…"
}

func init() {
	rootCmd.AddCommand(rankCmd)
	rankCmd.Flags().Bool("json", false, "JSON 输出")
}
