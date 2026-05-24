package db

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/huijiecai/stock/astock/internal/model"
)

func UpsertStockInfo(ctx context.Context, stocks []model.Stock) error {
	if len(stocks) == 0 {
		return nil
	}
	batch := &pgx.Batch{}
	for _, s := range stocks {
		sql := `INSERT INTO stock_info (code, name, exchange, sector)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, exchange=EXCLUDED.exchange, sector=EXCLUDED.sector, updated_at=CURRENT_TIMESTAMP`
		batch.Queue(sql, s.Code, s.Name, s.Exchange, s.Sector)
	}
	br := Pool.SendBatch(ctx, batch)
	defer br.Close()
	for i := 0; i < len(stocks); i++ {
		if _, err := br.Exec(); err != nil {
			return fmt.Errorf("upsert stock_info %s: %w", stocks[i].Code, err)
		}
	}
	return nil
}

func QueryStocks(ctx context.Context, exchange string) ([]model.Stock, error) {
	sql := "SELECT code, name, exchange, sector FROM stock_info"
	args := []any{}
	if exchange != "" {
		sql += " WHERE exchange=$1"
		args = append(args, exchange)
	}
	sql += " ORDER BY code"
	rows, err := Pool.Query(ctx, sql, args...)
	if err != nil {
		return nil, fmt.Errorf("query stocks: %w", err)
	}
	defer rows.Close()
	var stocks []model.Stock
	for rows.Next() {
		var s model.Stock
		if err := rows.Scan(&s.Code, &s.Name, &s.Exchange, &s.Sector); err != nil {
			return nil, fmt.Errorf("scan stock: %w", err)
		}
		stocks = append(stocks, s)
	}
	return stocks, nil
}

func UpsertConceptInfo(ctx context.Context, concepts []model.Concept) error {
	if len(concepts) == 0 {
		return nil
	}
	batch := &pgx.Batch{}
	for _, c := range concepts {
		sql := `INSERT INTO concept_info (code, name, stock_count)
                VALUES ($1, $2, $3)
                ON CONFLICT (code) DO UPDATE SET name=EXCLUDED.name, stock_count=EXCLUDED.stock_count, updated_at=CURRENT_TIMESTAMP`
		batch.Queue(sql, c.Code, c.Name, c.StockCount)
	}
	br := Pool.SendBatch(ctx, batch)
	defer br.Close()
	for i := 0; i < len(concepts); i++ {
		if _, err := br.Exec(); err != nil {
			return fmt.Errorf("upsert concept_info %s: %w", concepts[i].Code, err)
		}
	}
	return nil
}

func QueryConcepts(ctx context.Context) ([]model.Concept, error) {
	rows, err := Pool.Query(ctx, "SELECT code, name, stock_count FROM concept_info ORDER BY code")
	if err != nil {
		return nil, fmt.Errorf("query concepts: %w", err)
	}
	defer rows.Close()
	var concepts []model.Concept
	for rows.Next() {
		var c model.Concept
		if err := rows.Scan(&c.Code, &c.Name, &c.StockCount); err != nil {
			return nil, fmt.Errorf("scan concept: %w", err)
		}
		concepts = append(concepts, c)
	}
	return concepts, nil
}

func UpsertConceptConstituents(ctx context.Context, conceptCode string, stockCodes []string) error {
	if len(stockCodes) == 0 {
		return nil
	}
	batch := &pgx.Batch{}
	for _, sc := range stockCodes {
		sql := `INSERT INTO concept_constituents (concept_code, stock_code)
                VALUES ($1, $2) ON CONFLICT DO NOTHING`
		batch.Queue(sql, conceptCode, sc)
	}
	br := Pool.SendBatch(ctx, batch)
	defer br.Close()
	for i := 0; i < len(stockCodes); i++ {
		if _, err := br.Exec(); err != nil {
			return fmt.Errorf("upsert concept_constituents %s %s: %w", conceptCode, stockCodes[i], err)
		}
	}
	return nil
}

// DeleteStocksNotInSectors deletes stocks whose sector is not in the given list,
// along with all related kline data.
func DeleteStocksNotInSectors(ctx context.Context, sectors []string) (int, error) {
	// Also clean up orphaned kline data (stocks deleted from stock_info)
	var total int
	for _, tbl := range []string{"daily_k", "minute_k"} {
		tag, err := Pool.Exec(ctx, fmt.Sprintf(`DELETE FROM %s WHERE code NOT IN (SELECT code FROM stock_info)`, tbl))
		if err != nil {
			return total, fmt.Errorf("delete orphan %s: %w", tbl, err)
		}
		total += int(tag.RowsAffected())
	}

	if len(sectors) == 0 {
		return total, nil
	}

	// Build condition: sector NOT IN (target list)
	cond := "sector NOT IN ("
	for i, s := range sectors {
		if i > 0 {
			cond += ","
		}
		cond += fmt.Sprintf("'%s'", s)
	}
	cond += ")"

	for _, tbl := range []string{"daily_k", "minute_k"} {
		sql := fmt.Sprintf(`DELETE FROM %s WHERE code IN (SELECT code FROM stock_info WHERE %s)`, tbl, cond)
		tag, err := Pool.Exec(ctx, sql)
		if err != nil {
			return total, fmt.Errorf("delete %s: %w", tbl, err)
		}
		total += int(tag.RowsAffected())
	}

	_, err := Pool.Exec(ctx, fmt.Sprintf(`DELETE FROM concept_constituents WHERE stock_code IN (SELECT code FROM stock_info WHERE %s)`, cond))
	if err != nil {
		return total, fmt.Errorf("delete concept_constituents: %w", err)
	}

	tag, err := Pool.Exec(ctx, fmt.Sprintf(`DELETE FROM stock_info WHERE %s`, cond))
	if err != nil {
		return total, fmt.Errorf("delete stock_info: %w", err)
	}
	total += int(tag.RowsAffected())
	return total, nil
}

// QueryStocksBySector returns stocks matching the given sector.
func QueryStocksBySector(ctx context.Context, sector string) ([]model.Stock, error) {
	rows, err := Pool.Query(ctx, "SELECT code, name, exchange, sector FROM stock_info WHERE sector=$1 ORDER BY code", sector)
	if err != nil {
		return nil, fmt.Errorf("query stocks by sector: %w", err)
	}
	defer rows.Close()
	var stocks []model.Stock
	for rows.Next() {
		var s model.Stock
		if err := rows.Scan(&s.Code, &s.Name, &s.Exchange, &s.Sector); err != nil {
			return nil, fmt.Errorf("scan stock: %w", err)
		}
		stocks = append(stocks, s)
	}
	return stocks, nil
}
