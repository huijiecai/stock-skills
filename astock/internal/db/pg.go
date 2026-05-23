package db

import (
    "context"
    "fmt"
    "time"

    "github.com/jackc/pgx/v5/pgxpool"
    "github.com/huijiecai/stock/astock/internal/config"
)

var Pool *pgxpool.Pool

func Connect(ctx context.Context, cfg *config.Config) error {
    dsn := fmt.Sprintf("postgres://%s:%s@%s:%d/%s?sslmode=disable",
        cfg.DBUser, cfg.DBPassword, cfg.DBHost, cfg.DBPort, cfg.DBName)

    poolCfg, err := pgxpool.ParseConfig(dsn)
    if err != nil {
        return fmt.Errorf("parse dsn: %w", err)
    }
    poolCfg.MaxConns = 10
    poolCfg.MinConns = 2

    pool, err := pgxpool.NewWithConfig(ctx, poolCfg)
    if err != nil {
        return fmt.Errorf("create pool: %w", err)
    }

    pingCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
    defer cancel()
    if err := pool.Ping(pingCtx); err != nil {
        pool.Close()
        return fmt.Errorf("ping: %w", err)
    }

    Pool = pool
    return nil
}

func Close() {
    if Pool != nil {
        Pool.Close()
    }
}
