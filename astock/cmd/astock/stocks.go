// astock/cmd/astock/stocks.go
package main

import (
	"context"
	"fmt"
	"strings"

	"github.com/spf13/cobra"
	"github.com/huijiecai/stock/astock/internal/db"
	"github.com/huijiecai/stock/astock/internal/fetch"
	"github.com/huijiecai/stock/astock/internal/model"
)

var stocksCmd = &cobra.Command{
	Use:   "stocks {import|list|clean}",
	Short: "行业股票管理（按行业分类导入/查询/清理）",
}

var stocksImportCmd = &cobra.Command{
	Use:   "import",
	Short: "导入目标行业股票（先尝试API，失败则用内置精选列表）",
	Run: func(cmd *cobra.Command, args []string) {
		ctx := context.Background()

		classified := make([]model.Stock, 0)
		sectorStats := make(map[string]int)

		// 1. 获取股票列表（先尝试API，失败则用内置精选列表）
		fmt.Println("正在获取A股列表...")
		apiStocks, apiErr := sel.StockList(ctx)
		if apiErr == nil && len(apiStocks) > 0 {
			fmt.Printf("从数据源获取到 %d 只股票\n", len(apiStocks))
			sectorIndex := fetch.BuildSectorIndex()
			for _, s := range apiStocks {
				sector, ok := sectorIndex[s.Code]
				if !ok {
					sector = fetch.ClassifyStock(s.Code, s.Name)
				}
				if sector == "" {
					continue
				}
				s.Sector = sector
				sectorStats[sector]++
				classified = append(classified, s)
			}
		} else {
			if apiErr != nil {
				fmt.Printf("数据源获取失败: %v\n", apiErr)
			}
			fmt.Println("使用内置精选股票列表（覆盖10大行业产业链上下游）")
			curated := fetch.CuratedStockList()
			for _, ci := range curated {
				sectorStats[ci.Sector]++
				classified = append(classified, model.Stock{
					Code:     ci.Code,
					Name:     ci.Name,
					Exchange: ci.Exchange,
					Sector:   ci.Sector,
				})
			}
		}

		// 2. 显示分类统计
		fmt.Println("\n行业分类统计:")
		fmt.Println(strings.Repeat("-", 40))
		for _, sec := range fetch.TargetSectors {
			if count := sectorStats[sec]; count > 0 {
				fmt.Printf("  %-12s %d 只\n", sec, count)
			}
		}
		fmt.Println(strings.Repeat("-", 40))
		fmt.Printf("  目标行业合计: %d 只\n", len(classified))

		// 3. 写入数据库
		fmt.Println("\n正在写入数据库...")
		if err := db.UpsertStockInfo(ctx, classified); err != nil {
			fmt.Fprintf(cmd.ErrOrStderr(), "写入失败: %v\n", err)
			return
		}
		fmt.Printf("已写入 %d 只股票\n", len(classified))

		// 4. 清理非目标行业的数据
		fmt.Println("\n正在清理非目标行业的历史K线数据...")
		deleted, err := db.DeleteStocksNotInSectors(ctx, fetch.TargetSectors)
		if err != nil {
			fmt.Fprintf(cmd.ErrOrStderr(), "清理失败: %v\n", err)
			return
		}
		fmt.Printf("已清理 %d 条记录\n", deleted)

		fmt.Println("\n导入完成!")
	},
}

var stocksListCmd = &cobra.Command{
	Use:   "list [sector]",
	Short: "按行业列出股票（留空列出所有行业统计）",
	Args:  cobra.MaximumNArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		ctx := context.Background()

		if len(args) > 0 {
			sector := args[0]
			stocks, err := db.QueryStocksBySector(ctx, sector)
			if err != nil {
				fmt.Fprintf(cmd.ErrOrStderr(), "查询失败: %v\n", err)
				return
			}
			if len(stocks) == 0 {
				fmt.Printf("行业[%s]无股票\n", sector)
				return
			}
			fmt.Printf("=== %s (%d只) ===\n\n", sector, len(stocks))
			fmt.Printf("%-8s %-10s %-6s\n", "代码", "名称", "交易所")
			fmt.Println(strings.Repeat("-", 30))
			for _, s := range stocks {
				fmt.Printf("%-8s %-10s %-6s\n", s.Code, truncate(s.Name, 8), s.Exchange)
			}
		} else {
			// 显示所有行业统计
			stocks, err := db.QueryStocks(ctx, "")
			if err != nil {
				fmt.Fprintf(cmd.ErrOrStderr(), "查询失败: %v\n", err)
				return
			}
			stats := make(map[string]int)
			for _, s := range stocks {
				sec := s.Sector
				if sec == "" {
					sec = "未分类"
				}
				stats[sec]++
			}
			fmt.Println("各行业股票数量:")
			fmt.Println(strings.Repeat("-", 30))
			for _, sec := range fetch.TargetSectors {
				if count := stats[sec]; count > 0 {
					fmt.Printf("  %-12s %d 只\n", sec, count)
				}
			}
			if count := stats["未分类"]; count > 0 {
				fmt.Printf("  %-12s %d 只\n", "未分类", count)
			}
			fmt.Println(strings.Repeat("-", 30))
			fmt.Printf("  合计: %d 只\n", len(stocks))
		}
	},
}

var stocksCleanCmd = &cobra.Command{
	Use:   "clean",
	Short: "清理非目标行业的所有股票及K线数据",
	Run: func(cmd *cobra.Command, args []string) {
		ctx := context.Background()
		fmt.Println("正在清理非目标行业数据...")
		deleted, err := db.DeleteStocksNotInSectors(ctx, fetch.TargetSectors)
		if err != nil {
			fmt.Fprintf(cmd.ErrOrStderr(), "清理失败: %v\n", err)
			return
		}
		fmt.Printf("已清理 %d 条记录\n", deleted)
	},
}

func init() {
	rootCmd.AddCommand(stocksCmd)
	stocksCmd.AddCommand(stocksImportCmd)
	stocksCmd.AddCommand(stocksListCmd)
	stocksCmd.AddCommand(stocksCleanCmd)
}
