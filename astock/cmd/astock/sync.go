package main

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/dwh"
	"github.com/huijiecai/stock/astock/internal/model"
	ssync "github.com/huijiecai/stock/astock/internal/sync"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

func init() {
	rootCmd.AddCommand(newSyncCmd())
}

func newSyncCmd() *cobra.Command {
	syncCmd := &cobra.Command{
		Use:   "sync",
		Short: "从 TDX 拉数据写入 ClickHouse",
	}

	// --- sync meta ---
	syncCmd.AddCommand(&cobra.Command{
		Use:   "meta",
		Short: "同步全市场标的列表（stock/index/etf）→ securities",
		RunE: func(cmd *cobra.Command, args []string) error {
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
			defer cancel()
			ch, tc, close, err := openBoth(ctx)
			if err != nil {
				return err
			}
			defer close()

			fmt.Println("→ 拉取全市场标的列表...")
			n, err := ssync.Meta(ctx, ch, tc)
			if err != nil {
				return err
			}
			fmt.Printf("✓ 写入 securities %d 行\n", n)
			return nil
		},
	})

	// --- sync daily ---
	dailyCmd := &cobra.Command{
		Use:   "daily",
		Short: "同步日 K 线 → kline_daily",
		RunE: func(cmd *cobra.Command, args []string) error {
			codeStr, _ := cmd.Flags().GetString("code")
			all, _ := cmd.Flags().GetBool("all")
			count, _ := cmd.Flags().GetUint16("count")
			if codeStr == "" && !all {
				return fmt.Errorf("需指定 --code 或 --all")
			}
			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
			defer cancel()
			ch, tc, close, err := openBoth(ctx)
			if err != nil {
				return err
			}
			defer close()

			if all {
				fmt.Printf("→ sync daily (all count=%d)...\n", count)
				n, err := ssync.Daily(ctx, ch, tc, "", true, count)
				if err != nil {
					return err
				}
				fmt.Printf("✓ 写入 kline_daily %d 行\n", n)
				return nil
			}

			codes := parseCodes(codeStr)
			for _, code := range codes {
				fmt.Printf("→ sync daily %s (count=%d)...\n", code, count)
				n, err := ssync.Daily(ctx, ch, tc, code, false, count)
				if err != nil {
					fmt.Printf("✗ %s: %v\n", code, err)
					continue
				}
				fmt.Printf("✓ %s kline_daily %d 行\n", code, n)
			}
			return nil
		},
	}
	dailyCmd.Flags().String("code", "", "6 位代码，多只用逗号分隔")
	dailyCmd.Flags().Bool("all", false, "遍历全部已入库标的")
	dailyCmd.Flags().Uint16("count", 800, "每只拉最近 N 根")
	syncCmd.AddCommand(dailyCmd)

	// --- sync xdxr ---
	xdxrCmd := &cobra.Command{
		Use:   "xdxr",
		Short: "同步除权除息 → xdxr",
		RunE: func(cmd *cobra.Command, args []string) error {
			codeStr, _ := cmd.Flags().GetString("code")
			all, _ := cmd.Flags().GetBool("all")
			if codeStr == "" && !all {
				return fmt.Errorf("需指定 --code 或 --all")
			}
			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
			defer cancel()
			ch, tc, close, err := openBoth(ctx)
			if err != nil {
				return err
			}
			defer close()

			if all {
				fmt.Println("→ sync xdxr (all)...")
				n, err := ssync.XDXR(ctx, ch, tc, "", true)
				if err != nil {
					return err
				}
				fmt.Printf("✓ 写入 xdxr %d 行\n", n)
				return nil
			}

			codes := parseCodes(codeStr)
			for _, code := range codes {
				fmt.Printf("→ sync xdxr %s...\n", code)
				n, err := ssync.XDXR(ctx, ch, tc, code, false)
				if err != nil {
					fmt.Printf("✗ %s: %v\n", code, err)
					continue
				}
				fmt.Printf("✓ %s xdxr %d 行\n", code, n)
			}
			return nil
		},
	}
	xdxrCmd.Flags().String("code", "", "6 位代码，多只用逗号分隔")
	xdxrCmd.Flags().Bool("all", false, "遍历全部已入库 stock")
	syncCmd.AddCommand(xdxrCmd)

	// --- sync minute ---
	minuteCmd := &cobra.Command{
		Use:   "minute",
		Short: "同步分钟 K 线 → kline_minute",
		RunE: func(cmd *cobra.Command, args []string) error {
			codeStr, _ := cmd.Flags().GetString("code")
			freq, _ := cmd.Flags().GetString("freq")
			count, _ := cmd.Flags().GetUint16("count")
			if codeStr == "" {
				return fmt.Errorf("需指定 --code")
			}
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
			defer cancel()
			ch, tc, close, err := openBoth(ctx)
			if err != nil {
				return err
			}
			defer close()

			codes := parseCodes(codeStr)
			for _, code := range codes {
				fmt.Printf("→ sync minute %s (freq=%s count=%d)...\n", code, freq, count)
				n, err := ssync.Minute(ctx, ch, tc, code, model.Freq(freq), count)
				if err != nil {
					fmt.Printf("✗ %s: %v\n", code, err)
					continue
				}
				fmt.Printf("✓ %s kline_minute %d 行\n", code, n)
			}
			return nil
		},
	}
	minuteCmd.Flags().String("code", "", "6 位代码，多只用逗号分隔")
	minuteCmd.Flags().String("freq", "5m", "频率: 1m/5m/15m/30m/60m")
	minuteCmd.Flags().Uint16("count", 800, "拉取根数")
	syncCmd.AddCommand(minuteCmd)

	// --- sync block ---
	syncCmd.AddCommand(&cobra.Command{
		Use:   "block",
		Short: "同步板块 + 成分股 → blocks / block_constituents",
		RunE: func(cmd *cobra.Command, args []string) error {
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
			defer cancel()
			ch, tc, close, err := openBoth(ctx)
			if err != nil {
				return err
			}
			defer close()

			fmt.Println("→ sync block...")
			n, err := ssync.Block(ctx, ch, tc)
			if err != nil {
				return err
			}
			fmt.Printf("✓ 写入 blocks + block_constituents %d 行\n", n)
			return nil
		},
	})

	// --- sync finance ---
	finCmd := &cobra.Command{
		Use:   "finance",
		Short: "同步财务数据 → finance",
		RunE: func(cmd *cobra.Command, args []string) error {
			codeStr, _ := cmd.Flags().GetString("code")
			all, _ := cmd.Flags().GetBool("all")
			if codeStr == "" && !all {
				return fmt.Errorf("需指定 --code 或 --all")
			}
			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
			defer cancel()
			ch, tc, close, err := openBoth(ctx)
			if err != nil {
				return err
			}
			defer close()

			if all {
				fmt.Println("→ sync finance (all)...")
				n, err := ssync.Finance(ctx, ch, tc, "", true)
				if err != nil {
					return err
				}
				fmt.Printf("✓ 写入 finance %d 行\n", n)
				return nil
			}

			codes := parseCodes(codeStr)
			for _, code := range codes {
				fmt.Printf("→ sync finance %s...\n", code)
				n, err := ssync.Finance(ctx, ch, tc, code, false)
				if err != nil {
					fmt.Printf("✗ %s: %v\n", code, err)
					continue
				}
				fmt.Printf("✓ %s finance %d 行\n", code, n)
			}
			return nil
		},
	}
	finCmd.Flags().String("code", "", "6 位代码，多只用逗号分隔")
	finCmd.Flags().Bool("all", false, "遍历全部")
	syncCmd.AddCommand(finCmd)

	// --- sync all ---
	allCmd := &cobra.Command{
		Use:   "all",
		Short: "批量同步：对每个 code 执行 daily + minute(1m,5m) + xdxr",
		RunE: func(cmd *cobra.Command, args []string) error {
			codeStr, _ := cmd.Flags().GetString("code")
			days, _ := cmd.Flags().GetUint16("days")
			if codeStr == "" {
				return fmt.Errorf("需指定 --code（逗号分隔多只）")
			}
			ctx, cancel := context.WithTimeout(context.Background(), 60*time.Minute)
			defer cancel()
			ch, tc, close, err := openBoth(ctx)
			if err != nil {
				return err
			}
			defer close()

			// 按天数换算各频率的 count
			dailyCount := days
			min1Count := days * 240 // 1m: 每天 240 根
			min5Count := days * 48  // 5m: 每天 48 根

			codes := parseCodes(codeStr)
			for i, code := range codes {
				fmt.Printf("\n━━ [%d/%d] %s ━━\n", i+1, len(codes), code)

				// daily
				fmt.Printf("  → daily (%d天)...\n", days)
				n, err := ssync.Daily(ctx, ch, tc, code, false, dailyCount)
				if err != nil {
					fmt.Printf("  ✗ daily: %v\n", err)
				} else {
					fmt.Printf("  ✓ daily %d 行\n", n)
				}

				// minute: 1m + 5m
				freqCounts := []struct {
					freq  string
					count uint16
				}{
					{"1m", min1Count},
					{"5m", min5Count},
				}
				for _, fc := range freqCounts {
					fmt.Printf("  → minute %s (%d天=%d根)...\n", fc.freq, days, fc.count)
					n, err = ssync.Minute(ctx, ch, tc, code, model.Freq(fc.freq), fc.count)
					if err != nil {
						fmt.Printf("  ✗ minute(%s): %v\n", fc.freq, err)
					} else {
						fmt.Printf("  ✓ minute(%s) %d 行\n", fc.freq, n)
					}
				}

				// xdxr
				fmt.Printf("  → xdxr...\n")
				n, err = ssync.XDXR(ctx, ch, tc, code, false)
				if err != nil {
					fmt.Printf("  ✗ xdxr: %v\n", err)
				} else {
					fmt.Printf("  ✓ xdxr %d 行\n", n)
				}
			}
			fmt.Printf("\n━━ 全部完成（%d 只, %d天）━━\n", len(codes), days)
			return nil
		},
	}
	allCmd.Flags().String("code", "", "6 位代码，多只用逗号分隔（必填）")
	allCmd.Flags().Uint16("days", 30, "同步最近 N 个交易日")
	syncCmd.AddCommand(allCmd)

	return syncCmd
}

// openBoth 打开 CH 连接 + TDX 连接，返回统一 close。
func openBoth(ctx context.Context) (*dwh.Client, *tdx.Client, func(), error) {
	ch, err := dwh.New(ctx, cfg)
	if err != nil {
		return nil, nil, nil, fmt.Errorf("connect CH: %w", err)
	}
	tc := tdx.New()
	close := func() {
		tc.Close()
		ch.Close()
	}
	return ch, tc, close, nil
}

// parseCodes 解析逗号分隔的代码列表，去除空白。
func parseCodes(s string) []string {
	parts := strings.Split(s, ",")
	var out []string
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}
