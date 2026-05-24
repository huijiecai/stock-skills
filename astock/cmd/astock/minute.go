// astock/cmd/astock/minute.go
package main

import (
	"context"
	"fmt"
	"strings"

	"github.com/spf13/cobra"
	"github.com/huijiecai/stock/astock/internal/model"
)

var minuteCmd = &cobra.Command{
	Use:   "minute <code>",
	Short: "查询分钟K线",
	Args:  cobra.ExactArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		code := args[0]
		tp, _ := cmd.Flags().GetString("type")
		freq, _ := cmd.Flags().GetString("freq")
		date, _ := cmd.Flags().GetString("date")
		force, _ := cmd.Flags().GetBool("force")
		jsonFmt, _ := cmd.Flags().GetBool("json")

		dataType := model.DataType(tp)
		if !isValidType(dataType) {
			fmt.Fprintf(cmd.ErrOrStderr(), "invalid type: %s\n", tp)
			return
		}

		barFreq := model.Freq(freq)
		switch barFreq {
		case model.Freq1m, model.Freq5m, model.Freq15m, model.Freq30m, model.Freq60m:
			// valid
		default:
			fmt.Fprintf(cmd.ErrOrStderr(), "invalid freq: %s (1m/5m/15m/30m/60m)\n", freq)
			return
		}

		bars, err := router.MinuteKline(context.Background(), code, dataType, barFreq, date, force)
		if err != nil {
			fmt.Fprintf(cmd.ErrOrStderr(), "Error: %v\n", err)
			return
		}

		if jsonFmt {
			printJSON(bars)
		} else {
			printMinuteTable(bars)
		}
	},
}

func printMinuteTable(bars []model.Bar) {
	if len(bars) == 0 {
		fmt.Println("无数据")
		return
	}
	fmt.Printf("%-8s %s %s %s %s %s %s\n",
		"代码", padRight("时间", 12), padRight("开盘", 10), padRight("收盘", 10),
		padRight("最高", 10), padRight("最低", 10), padRight("成交量", 12))
	fmt.Println(strings.Repeat("-", 72))

	for _, bar := range bars {
		t := bar.Time.Format("15:04")
		fmt.Printf("%-8s %s %s %s %s %s %s\n",
			bar.Code, padRight(t, 12),
			padRight(fmt.Sprintf("%.2f", bar.Open), 10),
			padRight(fmt.Sprintf("%.2f", bar.Close), 10),
			padRight(fmt.Sprintf("%.2f", bar.High), 10),
			padRight(fmt.Sprintf("%.2f", bar.Low), 10),
			padRight(formatVolume(bar.Volume), 12))
	}
}

func init() {
	rootCmd.AddCommand(minuteCmd)
	minuteCmd.Flags().String("type", "stock", "stock / index / concept")
	minuteCmd.Flags().String("freq", "1m", "1m / 5m / 15m / 30m / 60m")
	minuteCmd.Flags().String("date", "", "指定日期 (默认今天)")
	minuteCmd.Flags().Bool("force", false, "跳过缓存，从数据源获取")
	minuteCmd.Flags().Bool("json", false, "JSON 输出")
}
