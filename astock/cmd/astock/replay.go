package main

import (
	"fmt"
	"time"

	"github.com/spf13/cobra"
)

// 市场指数代码 → 名称（replay index / prepare 共用）。
var marketIndexCodes = []struct {
	code, name string
}{
	{"000001", "上证指数"},
	{"399001", "深证成指"},
	{"000688", "科创50"},
	{"399006", "创业板指"},
	{"399300", "沪深300"},
	{"399016", "深证700"},
	{"399905", "中证500"},
}

func init() {
	rootCmd.AddCommand(newReplayCmd())
}

// newReplayCmd 构建 replay 子命令树——历史回放，和 live 镜像。
//
// live 直拉 TDX 实时协议；replay 从 ClickHouse 重建指定日期的行情。
// replay prepare <date>  统一同步一天所需的全部数据；
// replay check  <date>    检查数据完整性。
func newReplayCmd() *cobra.Command {
	replayCmd := &cobra.Command{
		Use:   "replay",
		Short: "历史回放——从 ClickHouse 重建指定日期的行情",
	}

	replayCmd.AddCommand(buildReplayPrepareCmd())
	replayCmd.AddCommand(buildReplayCheckCmd())
	replayCmd.AddCommand(buildReplayIndexCmd())
	addReplayBlockCmd(replayCmd)
	replayCmd.AddCommand(buildReplayQuoteCmd())
	addReplayLimitCmd(replayCmd)
	replayCmd.AddCommand(buildReplayMarketCmd())

	return replayCmd
}

// parseReplayDate 校验并格式化日期参数（YYYYMMDD）。
func parseReplayDate(s string) (string, error) {
	if _, err := time.Parse("20060102", s); err != nil {
		return "", fmt.Errorf("date 格式应为 YYYYMMDD，如 20260730")
	}
	return s, nil
}

// parseReplayTime 校验时间参数（HH:MM），返回 "HH:MM:SS" 形式（供 SQL）。
// 空字符串表示不指定时间（返回最近一根 bar / 收盘值）。
func parseReplayTime(s string) (string, error) {
	if s == "" {
		return "", nil
	}
	t, err := time.Parse("15:04", s)
	if err != nil {
		return "", fmt.Errorf("time 格式应为 HH:MM，如 10:30")
	}
	return t.Format("15:04:05"), nil
}

// replayDateTime 构造完整的 DateTime 字符串 "YYYY-MM-DD HH:MM:SS"。
func replayDateTime(date, hhmmss string) string {
	return formatDate(date) + " " + hhmmss
}
