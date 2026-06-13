package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/dwh"
)

// buildLimitLadderSubCmd 连板天梯，作为 query limit 的子命令。
//
// 指令路径：query limit ladder [date]（命名宪法 v1：禁止连字符复合命令名）。
// 派生自 queryLimitList（同一份数据），按连板数 ConsecDays 分组并降序展示。
func buildLimitLadderSubCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "ladder [date]",
		Short: "连板天梯：按连板数分组展示当日仍封涨停股",
		Long: `连板天梯——派生自 query limit，按连板数分组展示当日所有仍封涨停股。

date 可选，格式 YYYYMMDD；省略则取 kline_daily 中最新交易日。

示例：
  astock query limit ladder 20260612              # ≥2 板天梯（默认）
  astock query limit ladder 20260612 --min-board 3 # 仅 3 板及以上
  astock query limit ladder --exclude-st           # 排除 ST
  astock query limit ladder --json                 # JSON 扁平输出`,
		Args: cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			minBoard, _ := cmd.Flags().GetInt("min-board")
			if minBoard < 1 {
				return fmt.Errorf("--min-board 必须 >= 1")
			}
			excludeST, _ := cmd.Flags().GetBool("exclude-st")

			ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			// 解析日期（沿用 query limit 同款逻辑）
			var date string
			if len(args) == 1 {
				if _, err := time.Parse("20060102", args[0]); err != nil {
					return fmt.Errorf("date 格式应为 YYYYMMDD，如 20260612")
				}
				date = args[0]
			} else {
				row := ch.Conn().QueryRow(ctx,
					fmt.Sprintf("SELECT max(trade_date) FROM %s.kline_daily WHERE type='stock'", ch.DB()))
				var d time.Time
				if err := row.Scan(&d); err != nil {
					return fmt.Errorf("查询最新交易日失败: %w", err)
				}
				date = d.Format("20060102")
			}

			// 1. 复用 queryLimitList 拿当日涨停清单（已含 ConsecDays + Concepts）
			all, err := queryLimitList(ctx, ch, date, "up", excludeST)
			if err != nil {
				return err
			}
			// 2. 过滤 ≥ minBoard
			filtered := make([]*LimitStock, 0, len(all))
			for _, s := range all {
				if s.ConsecDays >= minBoard {
					filtered = append(filtered, s)
				}
			}
			// 3. 按 ConsecDays DESC, Amount DESC 排序
			sort.Slice(filtered, func(i, j int) bool {
				if filtered[i].ConsecDays != filtered[j].ConsecDays {
					return filtered[i].ConsecDays > filtered[j].ConsecDays
				}
				return filtered[i].Amount > filtered[j].Amount
			})

			if len(filtered) == 0 {
				fmt.Printf("日期 %s 无 ≥%d 板涨停股\n", formatDate(date), minBoard)
				return nil
			}

			if isJSON(cmd) {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(filtered)
			}
			printLimitLadder(filtered, formatDate(date), minBoard)
			return nil
		},
	}
	cmd.Flags().Int("min-board", 2, "最低连板数（默认 2，即 2 板及以上）")
	cmd.Flags().Bool("exclude-st", false, "排除 ST/*ST 股")
	return cmd
}

// printLimitLadder 按连板数分组打印天梯表格。
//
// 同一组内按成交额 DESC 排序（已在调用前完成），列定义与 query limit 保持一致：
// 代码 / 名称 / 板别 / 涨幅% / 收盘价 / 涨停价 / 成交额 / 连板 / 概念标签。
func printLimitLadder(list []*LimitStock, dateLabel string, minBoard int) {
	fmt.Printf("=== %s 连板天梯（≥%d 板） ===\n\n", dateLabel, minBoard)

	// 按 ConsecDays 分组（list 已 DESC 排好）
	type group struct {
		consec int
		stocks []*LimitStock
	}
	var groups []group
	cur := group{consec: list[0].ConsecDays}
	for _, s := range list {
		if s.ConsecDays != cur.consec {
			groups = append(groups, cur)
			cur = group{consec: s.ConsecDays}
		}
		cur.stocks = append(cur.stocks, s)
	}
	groups = append(groups, cur)

	for _, g := range groups {
		fmt.Printf("━━ %d 板（%d 只） ━━\n", g.consec, len(g.stocks))
		t := newTable(
			"代码", 6,
			"名称", 12,
			"板别", 6,
			"涨幅%", 8,
			"收盘价", 8,
			"涨停价", 8,
			"成交额", 10,
			"连板", 4,
			"概念标签", 30,
		)
		for _, s := range g.stocks {
			concepts := strings.Join(s.Concepts, "/")
			t.Row(
				s.Code,
				s.Name,
				boardLabel(s.Board),
				fmt.Sprintf("%+.2f%%", s.ChangePct),
				fmt.Sprintf("%.2f", s.Close),
				fmt.Sprintf("%.2f", s.LimitPrice),
				formatAmount(s.Amount),
				fmt.Sprintf("%d", s.ConsecDays),
				concepts,
			)
		}
		t.Print()
		fmt.Println()
	}
	fmt.Printf("共 %d 只 ≥%d 板\n", len(list), minBoard)
}
