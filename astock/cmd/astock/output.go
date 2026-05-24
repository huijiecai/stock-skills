// astock/cmd/astock/output.go
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strconv"
	"strings"

	"github.com/huijiecai/stock/astock/internal/model"
)

func isValidType(tp model.DataType) bool {
	return tp == model.TypeStock || tp == model.TypeIndex || tp == model.TypeConcept
}

func printJSON(v any) {
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	if err := enc.Encode(v); err != nil {
		fmt.Fprintf(os.Stderr, "JSON encode error: %v\n", err)
	}
}

func printDailyTable(bars []model.Bar) {
	if len(bars) == 0 {
		fmt.Println("无数据")
		return
	}
	fmt.Printf("%-8s %s %s %s %s %s %s %s\n",
		"代码", padRight("日期", 12), padRight("开盘", 10), padRight("收盘", 10),
		padRight("最高", 10), padRight("最低", 10), padRight("涨幅%", 8), padRight("成交量", 12))
	fmt.Println(strings.Repeat("-", 80))

	for _, bar := range bars {
		change := fmt.Sprintf("%+.2f%%", bar.ChangePct)
		vol := formatVolume(bar.Volume)
		fmt.Printf("%-8s %s %s %s %s %s %s %s\n",
			bar.Code, padRight(bar.TradeDate, 12),
			padRight(fmt.Sprintf("%.2f", bar.Open), 10),
			padRight(fmt.Sprintf("%.2f", bar.Close), 10),
			padRight(fmt.Sprintf("%.2f", bar.High), 10),
			padRight(fmt.Sprintf("%.2f", bar.Low), 10),
			padRight(change, 8), padRight(vol, 12))
	}
}

func formatVolume(v int64) string {
	if v > 100_000_000 {
		return fmt.Sprintf("%.2f亿", float64(v)/100_000_000)
	}
	if v > 10_000 {
		return fmt.Sprintf("%.2f万", float64(v)/10_000)
	}
	return strconv.FormatInt(v, 10)
}
