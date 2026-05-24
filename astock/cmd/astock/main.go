package main

import (
	"context"
	"fmt"
	"log"
	"os"
	"time"

	"github.com/joho/godotenv"
	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/config"
	"github.com/huijiecai/stock/astock/internal/db"
	"github.com/huijiecai/stock/astock/internal/fetch"
	"github.com/huijiecai/stock/astock/internal/query"
)

var (
	cfg    *config.Config
	router *query.Router
	sel    *fetch.Selector
)

var rootCmd = &cobra.Command{
	Use:   "astock",
	Short: "A股量化数据 CLI 工具",
	Long: `astock -- A股行情数据查询工具

多数据源（东财/通达信/腾讯/同花顺）行情数据持久化到 PostgreSQL，
通过统一 CLI 接口查询。历史数据自动缓存，盘中实时直连数据源。`,
	Version: "0.1.0",
	Run: func(cmd *cobra.Command, args []string) {
		cmd.Help()
	},
}

func initConfig() {
	godotenv.Load()
	cfg = config.Load()
}

func initDB() {
	ctx := context.Background()
	if err := db.Connect(ctx, cfg); err != nil {
		log.Fatalf("DB connect: %v", err)
	}
	if err := db.Migrate(ctx); err != nil {
		log.Fatalf("DB migrate: %v", err)
	}
}

func initFetcher() {
	em := fetch.NewEastMoney()
	bd := fetch.NewBaidu()
	ten := fetch.NewTencent()
	ths := fetch.NewTHS()
	sina := fetch.NewSina()

	sel = fetch.NewSelector(em, bd, nil, ten, ths, sina)
	router = query.NewRouter(sel)
}

func startRetentionCleanup(ctx context.Context) {
	go func() {
		ticker := time.NewTicker(24 * time.Hour)
		defer ticker.Stop()
		cleanupOldData(ctx)
		for {
			select {
			case <-ticker.C:
				cleanupOldData(ctx)
			case <-ctx.Done():
				return
			}
		}
	}()
}

func cleanupOldData(ctx context.Context) {
	days := cfg.RetentionDays
	sql := `DELETE FROM daily_k WHERE trade_date < CURRENT_DATE - $1`
	if n, err := db.Pool.Exec(ctx, sql, days); err == nil {
		log.Printf("[cleanup] daily_k: %d rows deleted", n.RowsAffected())
	}
	sql = `DELETE FROM minute_k WHERE dt < CURRENT_DATE - $1`
	if n, err := db.Pool.Exec(ctx, sql, days); err == nil {
		log.Printf("[cleanup] minute_k: %d rows deleted", n.RowsAffected())
	}
}

func main() {
	initConfig()
	initDB()
	defer db.Close()
	initFetcher()
	startRetentionCleanup(context.Background())

	if err := rootCmd.Execute(); err != nil {
		fmt.Println(err)
		os.Exit(1)
	}
}
