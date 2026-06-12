package main

import (
	"context"
	"fmt"
	"time"

	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/dwh"
)

func init() {
	rootCmd.AddCommand(newInitCmd())
}

func newInitCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "init",
		Short: "在 ClickHouse 中创建 astock 数据库及全部表",
		Long: `连接 CH，创建 astock 数据库并执行全部 9 张表的 DDL。
此命令幂等，重复执行只会确保结构存在，不会覆盖数据。`,
		RunE: func(cmd *cobra.Command, args []string) error {
			ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
			defer cancel()

			fmt.Printf("→ 连接 ClickHouse %s ...\n", cfg.CHAddr())
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return fmt.Errorf("connect: %w", err)
			}
			defer ch.Close()

			ver, err := ch.Version(ctx)
			if err != nil {
				return err
			}
			fmt.Printf("✓ 连上 CH，版本: %s\n", ver)

			fmt.Println("→ 执行 DDL（创建数据库 + 9 张表）...")
			if err := ch.InitSchema(ctx); err != nil {
				return fmt.Errorf("init schema: %w", err)
			}

			n, err := ch.CountTables(ctx)
			if err != nil {
				return err
			}
			fmt.Printf("✓ 数据库 %s 中已有 %d 张表（期望 9）\n", cfg.CHDatabase, n)

			if n < len(dwh.Tables) {
				fmt.Printf("⚠ 实际表数量少于预期，请检查日志\n")
			}
			fmt.Println("✓ astock init 完成")
			return nil
		},
	}
}
