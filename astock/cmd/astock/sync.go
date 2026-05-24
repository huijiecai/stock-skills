// astock/cmd/astock/sync.go
package main

import (
	"context"
	"fmt"
	"sync"

	"github.com/spf13/cobra"
	"github.com/huijiecai/stock/astock/internal/fetch"
	"github.com/huijiecai/stock/astock/internal/model"
)

type syncFlags struct {
	tp    string
	days  int
	start string
	end   string
	today bool
	json  bool
}

var syncCmd = &cobra.Command{
	Use:   "sync [code...]",
	Short: "批量同步历史数据到本地 PG",
	Args:  cobra.ArbitraryArgs,
	Run: func(cmd *cobra.Command, args []string) {
		tp, _ := cmd.Flags().GetString("type")
		days, _ := cmd.Flags().GetInt("days")
		start, _ := cmd.Flags().GetString("start")
		end, _ := cmd.Flags().GetString("end")
		today, _ := cmd.Flags().GetBool("today")
		jsonFmt, _ := cmd.Flags().GetBool("json")

		f := &syncFlags{tp: tp, days: days, start: start, end: end, today: today, json: jsonFmt}
		ctx := context.Background()

		if len(args) > 0 {
			syncCodes(ctx, args, f)
		} else {
			syncAll(ctx, f)
		}
	},
}

func syncCodes(ctx context.Context, codes []string, f *syncFlags) {
	var opts []fetch.Option
	if f.start != "" {
		opts = append(opts, fetch.WithStart(f.start))
	}
	if f.end != "" {
		opts = append(opts, fetch.WithEnd(f.end))
	}
	if f.days > 0 {
		opts = append(opts, fetch.WithLimit(f.days))
	}
	for _, code := range codes {
		fmt.Printf("同步 %s ...\n", code)
		bars, err := router.DailyKline(ctx, code, model.DataType(f.tp), true, opts...)
		if err != nil {
			fmt.Printf("  %s: 失败 — %v\n", code, err)
			continue
		}
		fmt.Printf("  %s: %d 条日K\n", code, len(bars))
	}
}

func syncAll(ctx context.Context, f *syncFlags) {
	// 全量同步股票列表
	fmt.Println("同步股票列表...")
	stocks, err := sel.StockList(ctx)
	if err != nil {
		fmt.Printf("股票列表获取失败: %v\n", err)
		return
	}
	fmt.Printf("股票列表: %d 条\n", len(stocks))

	// 全量同步概念列表
	fmt.Println("同步概念列表...")
	concepts, err := sel.ConceptList(ctx)
	if err != nil {
		fmt.Printf("概念列表获取失败: %v\n", err)
		return
	}
	fmt.Printf("概念列表: %d 条\n", len(concepts))

	// 同步日K（并发，goroutine 池限制 10）
	sem := make(chan struct{}, 10)
	var wg sync.WaitGroup
	var mu sync.Mutex
	var total int

	for _, s := range stocks {
		wg.Add(1)
		sem <- struct{}{}
		go func(code string) {
			defer wg.Done()
			defer func() { <-sem }()

			bars, err := router.DailyKline(ctx, code, model.TypeStock, true)
			if err != nil {
				fmt.Printf("  %s 同步失败: %v\n", code, err)
				return
			}
			mu.Lock()
			total += len(bars)
			mu.Unlock()
		}(s.Code)
	}
	wg.Wait()
	fmt.Printf("日K同步完成: %d 条\n", total)
}

func init() {
	rootCmd.AddCommand(syncCmd)
	syncCmd.Flags().String("type", "all", "stock / index / concept / all")
	syncCmd.Flags().Int("days", 30, "近N天")
	syncCmd.Flags().String("start", "", "开始日期")
	syncCmd.Flags().String("end", "", "结束日期")
	syncCmd.Flags().Bool("today", false, "仅今天")
	syncCmd.Flags().Bool("json", false, "JSON 输出")
}
