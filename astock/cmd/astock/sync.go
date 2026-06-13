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

	// --- sync info ---
	infoCmd := &cobra.Command{
		Use:   "info",
		Short: "同步 F10 公司信息（行业/地域/经营范围）→ securities 扩展字段",
		RunE: func(cmd *cobra.Command, args []string) error {
			codeStr, _ := cmd.Flags().GetString("code")
			all, _ := cmd.Flags().GetBool("all")
			if codeStr == "" && !all {
				return fmt.Errorf("需指定 --code 或 --all")
			}
			ctx, cancel := context.WithTimeout(context.Background(), 60*time.Minute)
			defer cancel()
			ch, tc, close, err := openBoth(ctx)
			if err != nil {
				return err
			}
			defer close()

			if all {
				fmt.Println("→ sync info (all)...")
				n, err := ssync.Info(ctx, ch, tc, "", true, func(i, total int, code string) {
					if i%100 == 0 {
						fmt.Printf("  [%d/%d] %s...\n", i, total, code)
					}
				})
				if err != nil {
					return err
				}
				fmt.Printf("✓ 更新 securities %d 只\n", n)
				return nil
			}

			codes := parseCodes(codeStr)
			for _, code := range codes {
				fmt.Printf("→ sync info %s...\n", code)
				n, err := ssync.Info(ctx, ch, tc, code, false, nil)
				if err != nil {
					fmt.Printf("✗ %s: %v\n", code, err)
					continue
				}
				fmt.Printf("✓ %s 更新 %d 条\n", code, n)
			}
			return nil
		},
	}
	infoCmd.Flags().String("code", "", "6 位代码，多只用逗号分隔")
	infoCmd.Flags().Bool("all", false, "遍历全部已入库 stock")
	syncCmd.AddCommand(infoCmd)

	// --- sync daily ---
	dailyCmd := &cobra.Command{
		Use:   "daily",
		Short: "同步日 K 线 → kline_daily",
		RunE: func(cmd *cobra.Command, args []string) error {
			codeStr, _ := cmd.Flags().GetString("code")
			all, _ := cmd.Flags().GetBool("all")
			count, _ := cmd.Flags().GetUint16("count")
			typeStr, _ := cmd.Flags().GetString("type")
			dataType := parseType(typeStr)
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
				fmt.Printf("→ sync daily (all type=%s count=%d)...\n", dataType, count)
				n, err := ssync.Daily(ctx, ch, tc, "", dataType, true, count, syncProgress)
				if err != nil {
					return err
				}
				fmt.Printf("✓ 写入 kline_daily %d 行\n", n)
				return nil
			}

			codes := parseCodes(codeStr)
			for _, code := range codes {
				fmt.Printf("→ sync daily %s (type=%s count=%d)...\n", code, dataType, count)
				n, err := ssync.Daily(ctx, ch, tc, code, dataType, false, count, nil)
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
	dailyCmd.Flags().String("type", "stock", "标的类型: stock(默认)/index/etf/block；--all 下 stock 默认扫 stock+index，block 扫全市场板块")
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
				n, err := ssync.XDXR(ctx, ch, tc, "", true, syncProgress)
				if err != nil {
					return err
				}
				fmt.Printf("✓ 写入 xdxr %d 行\n", n)
				return nil
			}

			codes := parseCodes(codeStr)
			for _, code := range codes {
				fmt.Printf("→ sync xdxr %s...\n", code)
				n, err := ssync.XDXR(ctx, ch, tc, code, false, nil)
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
			typeStr, _ := cmd.Flags().GetString("type")
			dataType := parseType(typeStr)
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
				fmt.Printf("→ sync minute %s (type=%s freq=%s count=%d)...\n", code, dataType, freq, count)
				n, err := ssync.Minute(ctx, ch, tc, code, dataType, model.Freq(freq), count)
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
	minuteCmd.Flags().String("type", "stock", "标的类型: stock(默认)/index/etf")
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
				n, err := ssync.Finance(ctx, ch, tc, "", true, syncProgress)
				if err != nil {
					return err
				}
				fmt.Printf("✓ 写入 finance %d 行\n", n)
				return nil
			}

			codes := parseCodes(codeStr)
			for _, code := range codes {
				fmt.Printf("→ sync finance %s...\n", code)
				n, err := ssync.Finance(ctx, ch, tc, code, false, nil)
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
		Short: "批量同步：按 --type 分发（stock=全套；index/etf=仅 daily/minute），支持 --all 全市场",
		RunE: func(cmd *cobra.Command, args []string) error {
			codeStr, _ := cmd.Flags().GetString("code")
			allFlag, _ := cmd.Flags().GetBool("all")
			days, _ := cmd.Flags().GetUint16("days")
			skipInfo, _ := cmd.Flags().GetBool("skip-info")
			skipFin, _ := cmd.Flags().GetBool("skip-finance")
			skipMin, _ := cmd.Flags().GetBool("skip-minute")
			skipXDXR, _ := cmd.Flags().GetBool("skip-xdxr")
			typeStr, _ := cmd.Flags().GetString("type")
			dataType := parseType(typeStr)
			if codeStr == "" && !allFlag {
				return fmt.Errorf("需指定 --code（逗号分隔多只）或 --all")
			}
			// --all 全市场可能耗时数小时，放宽到 6h；--code 模式 60min 仍够。
			timeout := 60 * time.Minute
			if allFlag {
				timeout = 6 * time.Hour
			}
			ctx, cancel := context.WithTimeout(context.Background(), timeout)
			defer cancel()
			ch, tc, close, err := openBoth(ctx)
			if err != nil {
				return err
			}
			defer close()
	
			// stock 走全套；info/xdxr/finance 仅适用 stock。
			isStock := dataType == model.TypeStock
	
			// 按天数换算各频率的 count
			dailyCount := days
			min1Count := days * 240 // 1m: 每天 240 根
			min5Count := days * 48  // 5m: 每天 48 根
	
			// 代码列表：--all 时从 securities 拉全量；否则解析 --code
			var codes []string
			if allFlag {
				codes, err = loadCodesFromCH(ctx, ch, dataType)
				if err != nil {
					return fmt.Errorf("加载 securities 代码列表失败: %w", err)
				}
				if len(codes) == 0 {
					return fmt.Errorf("securities 表中无 type=%s 数据，请先 sync meta", dataType)
				}
				fmt.Printf("→ 从 securities 加载 %d 只 %s\n", len(codes), dataType)
			} else {
				codes = parseCodes(codeStr)
			}
	
			for i, code := range codes {
				fmt.Printf("\n━━ [%d/%d] %s (type=%s) ━━\n", i+1, len(codes), code, dataType)
	
				// info (F10 公司信息)——仅 stock
				if isStock && !skipInfo {
					fmt.Printf("  → info...\n")
					n, err := ssync.Info(ctx, ch, tc, code, false, nil)
					if err != nil {
						fmt.Printf("  ✗ info: %v\n", err)
					} else {
						fmt.Printf("  ✓ info %d 条\n", n)
					}
				}
	
				// daily
				fmt.Printf("  → daily (%d天)...\n", days)
				n, err := ssync.Daily(ctx, ch, tc, code, dataType, false, dailyCount, nil)
				if err != nil {
					fmt.Printf("  ✗ daily: %v\n", err)
				} else {
					fmt.Printf("  ✓ daily %d 行\n", n)
				}
	
				// minute: 1m + 5m
				if !skipMin {
					freqCounts := []struct {
						freq  string
						count uint16
					}{
						{"1m", min1Count},
						{"5m", min5Count},
					}
					for _, fc := range freqCounts {
						fmt.Printf("  → minute %s (%d天=%d根)...\n", fc.freq, days, fc.count)
						n, err = ssync.Minute(ctx, ch, tc, code, dataType, model.Freq(fc.freq), fc.count)
						if err != nil {
							fmt.Printf("  ✗ minute(%s): %v\n", fc.freq, err)
						} else {
							fmt.Printf("  ✓ minute(%s) %d 行\n", fc.freq, n)
						}
					}
				}
	
				// xdxr——仅 stock
				if isStock && !skipXDXR {
					fmt.Printf("  → xdxr...\n")
					n, err = ssync.XDXR(ctx, ch, tc, code, false, nil)
					if err != nil {
						fmt.Printf("  ✗ xdxr: %v\n", err)
					} else {
						fmt.Printf("  ✓ xdxr %d 行\n", n)
					}
				}
	
				// finance——仅 stock
				if isStock && !skipFin {
					fmt.Printf("  → finance...\n")
					n, err = ssync.Finance(ctx, ch, tc, code, false, nil)
					if err != nil {
						fmt.Printf("  ✗ finance: %v\n", err)
					} else {
						fmt.Printf("  ✓ finance %d 行\n", n)
					}
				}
			}
			fmt.Printf("\n━━ 全部完成（%d 只, type=%s, %d天）━━\n", len(codes), dataType, days)
			return nil
		},
	}
	allCmd.Flags().String("code", "", "6 位代码，多只用逗号分隔（与 --all 二选一）")
	allCmd.Flags().Bool("all", false, "遍历 securities 表中全部当前 --type 标的")
	allCmd.Flags().Uint16("days", 30, "同步最近 N 个交易日")
	allCmd.Flags().Bool("skip-info", false, "跳过 F10 公司信息同步（仅 stock 生效）")
	allCmd.Flags().Bool("skip-finance", false, "跳过财务数据同步（仅 stock 生效）")
	allCmd.Flags().Bool("skip-minute", false, "跳过分钟K线同步（1m+5m）")
	allCmd.Flags().Bool("skip-xdxr", false, "跳过除权除息同步（仅 stock 生效）")
	allCmd.Flags().String("type", "stock", "标的类型: stock(默认全套)/index/etf(仅 daily/minute)")
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

// syncProgress 供 sync daily/xdxr/finance/info 的 --all 路径使用的进度回调。
// 每 100 只股打一行进度，避免全市场扫描 30+ 分钟期间静默看如卡死。
func syncProgress(i, total int, code string) {
	if i%100 == 0 {
		fmt.Printf("  [%d/%d] %s...\n", i, total, code)
	}
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

// loadCodesFromCH 从 securities 表按 type 拉取全部已入库代码。
// sync all --all 用于全市场扫描；前置依赖 sync meta 已执行。
func loadCodesFromCH(ctx context.Context, ch *dwh.Client, dataType model.DataType) ([]string, error) {
	sql := fmt.Sprintf("SELECT code FROM %s.securities FINAL WHERE type = ? ORDER BY code", ch.DB())
	rows, err := ch.Conn().Query(ctx, sql, string(dataType))
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var codes []string
	for rows.Next() {
		var code string
		if err := rows.Scan(&code); err != nil {
			return nil, err
		}
		codes = append(codes, code)
	}
	return codes, nil
}
