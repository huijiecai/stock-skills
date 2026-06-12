package main

import (
	"context"
	"fmt"
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
			code, _ := cmd.Flags().GetString("code")
			all, _ := cmd.Flags().GetBool("all")
			count, _ := cmd.Flags().GetUint16("count")
			if code == "" && !all {
				return fmt.Errorf("需指定 --code 或 --all")
			}
			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
			defer cancel()
			ch, tc, close, err := openBoth(ctx)
			if err != nil {
				return err
			}
			defer close()

			fmt.Printf("→ sync daily (code=%s all=%v count=%d)...\n", code, all, count)
			n, err := ssync.Daily(ctx, ch, tc, code, all, count)
			if err != nil {
				return err
			}
			fmt.Printf("✓ 写入 kline_daily %d 行\n", n)
			return nil
		},
	}
	dailyCmd.Flags().String("code", "", "6 位代码（单只）")
	dailyCmd.Flags().Bool("all", false, "遍历全部已入库标的")
	dailyCmd.Flags().Uint16("count", 800, "每只拉最近 N 根（0 = 全量）")
	syncCmd.AddCommand(dailyCmd)

	// --- sync xdxr ---
	xdxrCmd := &cobra.Command{
		Use:   "xdxr",
		Short: "同步除权除息 → xdxr",
		RunE: func(cmd *cobra.Command, args []string) error {
			code, _ := cmd.Flags().GetString("code")
			all, _ := cmd.Flags().GetBool("all")
			if code == "" && !all {
				return fmt.Errorf("需指定 --code 或 --all")
			}
			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
			defer cancel()
			ch, tc, close, err := openBoth(ctx)
			if err != nil {
				return err
			}
			defer close()

			fmt.Printf("→ sync xdxr (code=%s all=%v)...\n", code, all)
			n, err := ssync.XDXR(ctx, ch, tc, code, all)
			if err != nil {
				return err
			}
			fmt.Printf("✓ 写入 xdxr %d 行\n", n)
			return nil
		},
	}
	xdxrCmd.Flags().String("code", "", "6 位代码（单只）")
	xdxrCmd.Flags().Bool("all", false, "遍历全部已入库 stock")
	syncCmd.AddCommand(xdxrCmd)

	// --- sync minute ---
	minuteCmd := &cobra.Command{
		Use:   "minute",
		Short: "同步分钟 K 线 → kline_minute",
		RunE: func(cmd *cobra.Command, args []string) error {
			code, _ := cmd.Flags().GetString("code")
			freq, _ := cmd.Flags().GetString("freq")
			count, _ := cmd.Flags().GetUint16("count")
			if code == "" {
				return fmt.Errorf("需指定 --code")
			}
			ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
			defer cancel()
			ch, tc, close, err := openBoth(ctx)
			if err != nil {
				return err
			}
			defer close()

			fmt.Printf("→ sync minute %s (freq=%s count=%d)...\n", code, freq, count)
			n, err := ssync.Minute(ctx, ch, tc, code, model.Freq(freq), count)
			if err != nil {
				return err
			}
			fmt.Printf("✓ 写入 kline_minute %d 行\n", n)
			return nil
		},
	}
	minuteCmd.Flags().String("code", "", "6 位代码")
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
			code, _ := cmd.Flags().GetString("code")
			all, _ := cmd.Flags().GetBool("all")
			if code == "" && !all {
				return fmt.Errorf("需指定 --code 或 --all")
			}
			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Minute)
			defer cancel()
			ch, tc, close, err := openBoth(ctx)
			if err != nil {
				return err
			}
			defer close()

			fmt.Printf("→ sync finance (code=%s all=%v)...\n", code, all)
			n, err := ssync.Finance(ctx, ch, tc, code, all)
			if err != nil {
				return err
			}
			fmt.Printf("✓ 写入 finance %d 行\n", n)
			return nil
		},
	}
	finCmd.Flags().String("code", "", "6 位代码（单只）")
	finCmd.Flags().Bool("all", false, "遍历全部")
	syncCmd.AddCommand(finCmd)

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
