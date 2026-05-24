// astock/cmd/astock/daily.go
package main

import (
	"context"
	"fmt"

	"github.com/spf13/cobra"
	"github.com/huijiecai/stock/astock/internal/fetch"
	"github.com/huijiecai/stock/astock/internal/model"
)

type dailyFlags struct {
	tp    string
	start string
	end   string
	limit int
	force bool
	json  bool
}

var dailyCmd = &cobra.Command{
	Use:   "daily <code>",
	Short: "查询日K线",
	Args:  cobra.ExactArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		code := args[0]
		tp, _ := cmd.Flags().GetString("type")
		start, _ := cmd.Flags().GetString("start")
		end, _ := cmd.Flags().GetString("end")
		limit, _ := cmd.Flags().GetInt("limit")
		force, _ := cmd.Flags().GetBool("force")
		jsonFmt, _ := cmd.Flags().GetBool("json")

		dataType := model.DataType(tp)
		if !isValidType(dataType) {
			fmt.Fprintf(cmd.ErrOrStderr(), "invalid type: %s (stock/index/concept)\n", tp)
			return
		}

		var opts []fetch.Option
		if start != "" {
			opts = append(opts, fetch.WithStart(start))
		}
		if end != "" {
			opts = append(opts, fetch.WithEnd(end))
		}
		if limit > 0 {
			opts = append(opts, fetch.WithLimit(limit))
		}

		bars, err := router.DailyKline(context.Background(), code, dataType, force, opts...)
		if err != nil {
			fmt.Fprintf(cmd.ErrOrStderr(), "Error: %v\n", err)
			return
		}

		if jsonFmt {
			printJSON(bars)
		} else {
			printDailyTable(bars)
		}
	},
}

func init() {
	rootCmd.AddCommand(dailyCmd)
	dailyCmd.Flags().String("type", "stock", "stock / index / concept")
	dailyCmd.Flags().String("start", "", "开始日期 (2006-01-02)")
	dailyCmd.Flags().String("end", "", "结束日期")
	dailyCmd.Flags().Int("limit", 30, "条数")
	dailyCmd.Flags().Bool("force", false, "跳过缓存，从数据源获取")
	dailyCmd.Flags().Bool("json", false, "JSON 输出")
}
