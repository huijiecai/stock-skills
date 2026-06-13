package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/dwh"
)

func init() {
	rootCmd.AddCommand(newStatsCmd())
	// newStatusCmd 不再作为顶层命令注册、改由 sync.go 在 sync 子命令树中 AddCommand
}

func newStatsCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "stats [table]",
		Short: "仓库概览统计；可选 [table] 参数查单表行数（原 query count 合并入此）",
		Args:  cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			// stats <table>：单表行数（原 query count 语义）
			if len(args) == 1 {
				var n uint64
				q := fmt.Sprintf(`SELECT count() FROM %s.%s`, ch.DB(), args[0])
				if err := ch.Conn().QueryRow(ctx, q).Scan(&n); err != nil {
					return err
				}
				if isJSON(cmd) {
					enc := json.NewEncoder(os.Stdout)
					enc.SetIndent("", "  ")
					return enc.Encode(map[string]uint64{args[0]: n})
				}
				fmt.Printf("%s: %d 行\n", args[0], n)
				return nil
			}

			tables := []string{
				"securities", "blocks", "block_constituents",
				"trade_cal", "xdxr", "finance",
				"kline_daily", "kline_minute", "sync_log",
			}

			// 统计各表行数
			tableCounts := make(map[string]uint64, len(tables))
			for _, t := range tables {
				var n uint64
				q := fmt.Sprintf(`SELECT count() FROM %s.%s`, ch.DB(), t)
				row := ch.Conn().QueryRow(ctx, q)
				if err := row.Scan(&n); err == nil {
					tableCounts[t] = n
				}
			}

			// 最近同步记录
			type logEntry struct {
				Task    string `json:"task"`
				Target  string `json:"target"`
				Rows    uint64 `json:"rows"`
				Status  string `json:"status"`
				StartAt string `json:"start_at"`
			}
			var logs []logEntry
			rows, err := ch.Conn().Query(ctx,
				fmt.Sprintf(`SELECT task, target, rows, status, start_at FROM %s.sync_log ORDER BY start_at DESC LIMIT 5`, ch.DB()))
			if err == nil {
				defer rows.Close()
				for rows.Next() {
					var e logEntry
					var startAt time.Time
					if err := rows.Scan(&e.Task, &e.Target, &e.Rows, &e.Status, &startAt); err == nil {
						e.StartAt = startAt.Format("2006-01-02 15:04:05")
						logs = append(logs, e)
					}
				}
			}

			// JSON 输出
			if isJSON(cmd) {
				out := struct {
					Tables  map[string]uint64 `json:"tables"`
					SyncLog []logEntry        `json:"sync_log"`
				}{Tables: tableCounts, SyncLog: logs}
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(out)
			}

			// 表格输出
			fmt.Println("━━━━━━ astock 仓库概览 ━━━━━━")
			for _, t := range tables {
				fmt.Printf("  %-22s  %d 行\n", t, tableCounts[t])
			}
			fmt.Println("\n━━━━━━ 最近 5 条 sync_log ━━━━━━")
			for _, e := range logs {
				fmt.Printf("  %s  %-12s  %-10s  %d行  %s\n", e.StartAt[5:16], e.Task, e.Target, e.Rows, e.Status)
			}
			return nil
		},
	}
}

func newStatusCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "status",
		Short: "最近同步任务状态",
		RunE: func(cmd *cobra.Command, args []string) error {
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			type logEntry struct {
				Task    string `json:"task"`
				Target  string `json:"target"`
				Rows    uint64 `json:"rows"`
				Status  string `json:"status"`
				StartAt string `json:"start_at"`
			}

			rows, err := ch.Conn().Query(ctx,
				fmt.Sprintf(`SELECT task, target, rows, status, start_at FROM %s.sync_log ORDER BY start_at DESC LIMIT 20`, ch.DB()))
			if err != nil {
				return err
			}
			defer rows.Close()

			var logs []logEntry
			for rows.Next() {
				var e logEntry
				var startAt time.Time
				if err := rows.Scan(&e.Task, &e.Target, &e.Rows, &e.Status, &startAt); err != nil {
					return err
				}
				e.StartAt = startAt.Format("2006-01-02 15:04:05")
				logs = append(logs, e)
			}
			if len(logs) == 0 {
				fmt.Println("无同步记录")
				return nil
			}

			if isJSON(cmd) {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(logs)
			}

			t := newTable("时间", 16, "任务", 12, "目标", 10, "行数", 8, "状态", 6)
			for _, e := range logs {
				t.Row(e.StartAt[5:16], e.Task, e.Target, fmt.Sprintf("%d", e.Rows), e.Status)
			}
			t.Print()
			return nil
		},
	}
}
