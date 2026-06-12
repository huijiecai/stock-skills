package main

import (
	"fmt"
	"os"

	"github.com/joho/godotenv"
	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/config"
)

// cfg 全局配置，在 main() 中初始化，子命令通过此包变量访问。
var cfg *config.Config

var rootCmd = &cobra.Command{
	Use:     "astock",
	Short:   "A股量化数据 CLI（ClickHouse + TDX）",
	Long:    `astock —— 基于 ClickHouse 的本地行情仓库 + TDX 直连工具。`,
	Version: "0.2.0-dev",
}

func init() {
	rootCmd.PersistentFlags().Bool("json", false, "输出 JSON 格式（供 AI/脚本消费）")
}

// isJSON 检查全局 --json flag 是否开启。
func isJSON(cmd *cobra.Command) bool {
	v, _ := cmd.Root().PersistentFlags().GetBool("json")
	return v
}

func main() {
	// 加载 .env（不存在不报错，回退环境变量默认值）
	_ = godotenv.Load()
	cfg = config.Load()

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
