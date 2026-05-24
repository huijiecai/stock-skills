// astock/cmd/astock/info.go
package main

import (
	"context"
	"fmt"
	"strings"

	"github.com/spf13/cobra"
	"github.com/huijiecai/stock/astock/internal/model"
)

var infoCmd = &cobra.Command{
	Use:   "info {stocks|concepts}",
	Short: "查询基础信息（股票列表/概念列表）",
	Args:  cobra.ExactArgs(1),
	Run: func(cmd *cobra.Command, args []string) {
		sub := args[0]
		exchange, _ := cmd.Flags().GetString("exchange")
		jsonFmt, _ := cmd.Flags().GetBool("json")

		ctx := context.Background()
		switch sub {
		case "stocks":
			stocks, err := router.StockList(ctx)
			if err != nil {
				fmt.Fprintf(cmd.ErrOrStderr(), "Error: %v\n", err)
				return
			}
			if exchange != "" {
				filtered := make([]model.Stock, 0)
				for _, s := range stocks {
					if s.Exchange == exchange {
						filtered = append(filtered, s)
					}
				}
				stocks = filtered
			}
			if jsonFmt {
				printJSON(stocks)
			} else {
				printStockTable(stocks)
			}

		case "concepts":
			concepts, err := router.ConceptList(ctx)
			if err != nil {
				fmt.Fprintf(cmd.ErrOrStderr(), "Error: %v\n", err)
				return
			}
			if jsonFmt {
				printJSON(concepts)
			} else {
				printConceptTable(concepts)
			}

		default:
			fmt.Fprintf(cmd.ErrOrStderr(), "unknown info type: %s (stocks|concepts)\n", sub)
		}
	},
}

func printStockTable(stocks []model.Stock) {
	fmt.Printf("%-8s %s %s\n", "代码", padRight("名称", 10), padRight("交易所", 6))
	fmt.Println(strings.Repeat("-", 30))
	for _, s := range stocks {
		fmt.Printf("%-8s %s %s\n", s.Code, padRight(truncate(s.Name, 8), 10), padRight(s.Exchange, 6))
	}
	fmt.Printf("\n共 %d 只股票\n", len(stocks))
}

func printConceptTable(concepts []model.Concept) {
	fmt.Printf("%-10s %s %s\n", "代码", padRight("名称", 20), padRight("成分股数", 8))
	fmt.Println(strings.Repeat("-", 42))
	for _, c := range concepts {
		fmt.Printf("%-10s %s %d\n", c.Code, padRight(truncate(c.Name, 16), 20), c.StockCount)
	}
	fmt.Printf("\n共 %d 个概念\n", len(concepts))
}

func init() {
	rootCmd.AddCommand(infoCmd)
	infoCmd.Flags().String("exchange", "", "sh / sz / bj")
	infoCmd.Flags().Bool("json", false, "JSON 输出")
}
