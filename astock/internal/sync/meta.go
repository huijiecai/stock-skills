package sync

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/huijiecai/stock/astock/internal/dwh"
	"github.com/huijiecai/stock/astock/internal/model"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

type MetaResult struct {
	Written         int
	NewStocks       int
	ListDatesFilled int
	PendingStocks   []string
}

// Meta 同步全市场标的列表（stock + index）到 securities 表。
// 因为 ReplacingMergeTree 按 (type, market, code) 去重，可以每次全量覆盖写。
func Meta(ctx context.Context, ch *dwh.Client, tc *tdx.Client) (MetaResult, error) {
	start := time.Now()
	existing, err := loadExistingSecurities(ctx, ch)
	if err != nil {
		return MetaResult{}, err
	}

	secs, err := tc.ListSecurities()
	if err != nil {
		return MetaResult{}, err
	}
	if len(secs) == 0 {
		return MetaResult{}, fmt.Errorf("no securities fetched")
	}
	secs, result := mergeSecurityMetadata(secs, existing, tc.GetSecurityListDate)

	// 批量写入（clickhouse-go batch 方式）
	batch, err := ch.Conn().PrepareBatch(ctx,
		fmt.Sprintf(`INSERT INTO %s.securities
(code, market, type, name, list_date, delist_date, industry, sector, province, business, updated_at)`, ch.DB()))
	if err != nil {
		return MetaResult{}, fmt.Errorf("prepare batch: %w", err)
	}
	for _, s := range secs {
		var delistDate *time.Time
		if !s.DelistDate.IsZero() {
			delistDate = &s.DelistDate
		}
		if err := batch.Append(s.Code, s.Market, string(s.Type), s.Name, s.ListDate, delistDate,
			s.Industry, s.Sector, s.Province, s.Business, time.Now()); err != nil {
			return MetaResult{}, fmt.Errorf("append: %w", err)
		}
	}
	if err := batch.Send(); err != nil {
		return MetaResult{}, fmt.Errorf("send batch: %w", err)
	}

	result.Written = len(secs)
	_ = WriteLog(ctx, ch, &LogEntry{Task: "sync_meta", Target: "securities", StartAt: start, Rows: uint64(result.Written), Status: "ok"})
	return result, nil
}

type securityKey struct {
	Code, Market string
	Type         model.DataType
}

func loadExistingSecurities(ctx context.Context, ch *dwh.Client) (map[securityKey]*model.Security, error) {
	rows, err := ch.Conn().Query(ctx, fmt.Sprintf(`
SELECT code, market, type, name, list_date, delist_date, industry, sector, province, business
FROM %s.securities FINAL`, ch.DB()))
	if err != nil {
		return nil, fmt.Errorf("query existing securities: %w", err)
	}
	defer rows.Close()

	existing := make(map[securityKey]*model.Security, 7000)
	for rows.Next() {
		var security model.Security
		var typ string
		var delistDate *time.Time
		if err := rows.Scan(&security.Code, &security.Market, &typ, &security.Name,
			&security.ListDate, &delistDate, &security.Industry, &security.Sector,
			&security.Province, &security.Business); err != nil {
			return nil, err
		}
		security.Type = model.DataType(typ)
		if delistDate != nil {
			security.DelistDate = *delistDate
		}
		existing[securityKey{Code: security.Code, Market: security.Market, Type: security.Type}] = &security
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}
	return existing, nil
}

func mergeSecurityMetadata(
	fetched []*model.Security,
	existing map[securityKey]*model.Security,
	getListDate func(market, code string) (time.Time, error),
) ([]*model.Security, MetaResult) {
	merged := make([]*model.Security, 0, len(fetched))
	seen := make(map[securityKey]bool, len(fetched))
	result := MetaResult{}
	for _, security := range fetched {
		key := securityKey{Code: security.Code, Market: security.Market, Type: security.Type}
		if seen[key] {
			continue
		}
		seen[key] = true

		old, exists := existing[key]
		if exists {
			if security.Name == "" {
				security.Name = old.Name
			}
			security.ListDate = old.ListDate
			security.DelistDate = old.DelistDate
			security.Industry = old.Industry
			security.Sector = old.Sector
			security.Province = old.Province
			security.Business = old.Business
		} else if security.Type == model.TypeStock {
			result.NewStocks++
			listDate, err := getListDate(security.Market, security.Code)
			if err != nil {
				result.PendingStocks = append(result.PendingStocks, security.Market+security.Code)
				continue
			}
			security.ListDate = listDate
			result.ListDatesFilled++
		}
		merged = append(merged, security)
	}
	return merged, result
}

func (r MetaResult) PendingSummary() string {
	return strings.Join(r.PendingStocks, ", ")
}
