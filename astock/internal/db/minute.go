package db

import (
	"context"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/huijiecai/stock/astock/internal/model"
)

func UpsertMinuteK(ctx context.Context, bars []model.Bar) error {
	if len(bars) == 0 {
		return nil
	}
	batch := &pgx.Batch{}
	for _, bar := range bars {
		sql := `INSERT INTO minute_k (code, dt, freq, type, open, high, low, close, volume, amount, avg_price)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (code, dt, freq, type) DO UPDATE SET
                    open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                    close=EXCLUDED.close, volume=EXCLUDED.volume,
                    amount=EXCLUDED.amount, avg_price=EXCLUDED.avg_price`
		batch.Queue(sql, bar.Code, bar.Time, string(bar.Freq), string(bar.Type),
			bar.Open, bar.High, bar.Low, bar.Close,
			bar.Volume, bar.Amount, bar.AvgPrice)
	}
	br := Pool.SendBatch(ctx, batch)
	defer br.Close()
	for i := 0; i < len(bars); i++ {
		if _, err := br.Exec(); err != nil {
			return fmt.Errorf("upsert minute_k %s %v: %w", bars[i].Code, bars[i].Time, err)
		}
	}
	return nil
}

func QueryMinuteK(ctx context.Context, code string, tp model.DataType, freq model.Freq, date string) ([]model.Bar, error) {
	if date == "" {
		date = time.Now().Format("2006-01-02")
	}
	startDT := date + " 00:00:00"
	endDT := date + " 23:59:59"
	sql := `SELECT code, dt, freq, type, open, high, low, close,
                   COALESCE(volume,0), COALESCE(amount,0), COALESCE(avg_price,0)
            FROM minute_k
            WHERE code=$1 AND type=$2 AND freq=$3 AND dt >= $4 AND dt <= $5
            ORDER BY dt ASC`
	rows, err := Pool.Query(ctx, sql, code, string(tp), string(freq), startDT, endDT)
	if err != nil {
		return nil, fmt.Errorf("query minute_k: %w", err)
	}
	defer rows.Close()
	var bars []model.Bar
	for rows.Next() {
		var bar model.Bar
		if err := rows.Scan(&bar.Code, &bar.Time, &bar.Freq, &bar.Type,
			&bar.Open, &bar.High, &bar.Low, &bar.Close,
			&bar.Volume, &bar.Amount, &bar.AvgPrice); err != nil {
			return nil, fmt.Errorf("scan minute_k: %w", err)
		}
		bars = append(bars, bar)
	}
	return bars, nil
}

func HasMinuteK(ctx context.Context, code string, tp model.DataType, freq model.Freq, date string) (bool, error) {
	var cnt int
	err := Pool.QueryRow(ctx,
		"SELECT COUNT(*) FROM minute_k WHERE code=$1 AND type=$2 AND freq=$3 AND dt::date=$4",
		code, string(tp), string(freq), date).Scan(&cnt)
	return cnt > 0, err
}
