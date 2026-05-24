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
	enc.Encode(v)
}

func printDailyTable(bars []model.Bar) {
	if len(bars) == 0 {
		fmt.Println("无数据")
		return
	}
	fmt.Printf("%-8s %-12s %-10s %-10s %-10s %-10s %-8s %-12s\n",
		"代码", "日期", "开盘", "收盘", "最高", "最低", "涨幅%", "成交量")
	fmt.Println(strings.Repeat("-", 80))

	for _, bar := range bars {
		change := fmt.Sprintf("%+.2f%%", bar.ChangePct)
		vol := formatVolume(bar.Volume)
		fmt.Printf("%-8s %-12s %-10.2f %-10.2f %-10.2f %-10.2f %-8s %-12s\n",
			bar.Code, bar.TradeDate, bar.Open, bar.Close,
			bar.High, bar.Low, change, vol)
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
