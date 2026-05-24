package db

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/huijiecai/stock/astock/internal/model"
)

func UpsertDailyK(ctx context.Context, bars []model.Bar) error {
	if len(bars) == 0 {
		return nil
	}
	batch := &pgx.Batch{}
	for _, bar := range bars {
		sql := `INSERT INTO daily_k (code, trade_date, type, open, high, low, close, pre_close, change_pct, volume, amount, turnover)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                ON CONFLICT (code, trade_date, type) DO UPDATE SET
                    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                    close=EXCLUDED.close, pre_close=EXCLUDED.pre_close,
                    change_pct=EXCLUDED.change_pct, volume=EXCLUDED.volume,
                    amount=EXCLUDED.amount, turnover=EXCLUDED.turnover`
		batch.Queue(sql, bar.Code, bar.TradeDate, string(bar.Type),
			bar.Open, bar.High, bar.Low, bar.Close,
			bar.PreClose, bar.ChangePct, bar.Volume, bar.Amount, bar.Turnover)
	}
	br := Pool.SendBatch(ctx, batch)
	defer br.Close()
	for i := 0; i < len(bars); i++ {
		if _, err := br.Exec(); err != nil {
			return fmt.Errorf("upsert daily_k %s %s: %w", bars[i].Code, bars[i].TradeDate, err)
		}
	}
	return nil
}

func QueryDailyK(ctx context.Context, code string, tp model.DataType, start, end string, limit int) ([]model.Bar, error) {
	if limit <= 0 {
		limit = 30
	}
	sql := `SELECT code, trade_date::text, type, open, high, low, close,
                   COALESCE(pre_close,0), COALESCE(change_pct,0),
                   COALESCE(volume,0), COALESCE(amount,0), COALESCE(turnover,0)
            FROM daily_k
            WHERE code=$1 AND type=$2 AND trade_date >= $3 AND trade_date <= $4
            ORDER BY trade_date DESC LIMIT $5`
	if start == "" {
		start = "2000-01-01"
	}
	if end == "" {
		end = time.Now().Format("2006-01-02")
	}
	rows, err := Pool.Query(ctx, sql, code, string(tp), start, end, limit)
	if err != nil {
		return nil, fmt.Errorf("query daily_k: %w", err)
	}
	defer rows.Close()
	var bars []model.Bar
	for rows.Next() {
		var bar model.Bar
		if err := rows.Scan(&bar.Code, &bar.TradeDate, &bar.Type,
			&bar.Open, &bar.High, &bar.Low, &bar.Close,
			&bar.PreClose, &bar.ChangePct, &bar.Volume, &bar.Amount, &bar.Turnover); err != nil {
			return nil, fmt.Errorf("scan daily_k: %w", err)
		}
		bars = append(bars, bar)
	}
	return bars, nil
}

func HasDailyK(ctx context.Context, code string, tp model.DataType, date string) (bool, error) {
	var cnt int
	err := Pool.QueryRow(ctx,
		"SELECT COUNT(*) FROM daily_k WHERE code=$1 AND type=$2 AND trade_date=$3",
		code, string(tp), date).Scan(&cnt)
	return cnt > 0, err
}
