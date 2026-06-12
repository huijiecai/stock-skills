package sync

import (
	"context"
	"fmt"
	"time"

	"github.com/huijiecai/stock/astock/internal/dwh"
	"github.com/huijiecai/stock/astock/internal/model"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

// Info 同步 F10 公司信息（行业/地域/经营范围）到 securities 表的扩展字段。
// code 为空时遍历全市场 stock；非空时只处理指定代码（逗号分隔由上层解析）。
func Info(ctx context.Context, ch *dwh.Client, tc *tdx.Client, code string, all bool, progress func(i, total int, code string)) (int, error) {
	start := time.Now()
	var codes []stockInfo

	if all || code == "" {
		var err error
		codes, err = listStockCodes(ctx, ch)
		if err != nil {
			return 0, err
		}
		// 只处理 stock 类型
		var filtered []stockInfo
		for _, c := range codes {
			if c.Type == model.TypeStock {
				filtered = append(filtered, c)
			}
		}
		codes = filtered
	} else {
		codes = []stockInfo{{Code: code, Type: model.TypeStock}}
	}

	var total int
	for i, sc := range codes {
		if progress != nil {
			progress(i, len(codes), sc.Code)
		}

		market := tdx.MarketOf(sc.Code)
		if market == "" {
			continue
		}

		info, err := tc.GetCompanyInfo(market, sc.Code)
		if err != nil {
			fmt.Printf("  ⚠ info %s: %v\n", sc.Code, err)
			continue
		}
		if info.Industry == "" && info.Province == "" {
			continue
		}

		// UPDATE securities 的扩展字段（CH 不支持 UPDATE，用 INSERT 覆盖 ReplacingMergeTree）
		// 先读出现有行，再补充字段写回
		if err := updateSecurityInfo(ctx, ch, sc.Code, info); err != nil {
			fmt.Printf("  ⚠ update %s: %v\n", sc.Code, err)
			continue
		}
		total++
	}

	_ = WriteLog(ctx, ch, &LogEntry{Task: "sync_info", Target: code, StartAt: start, Rows: uint64(total), Status: "ok"})
	return total, nil
}

// updateSecurityInfo 把 F10 信息写回 securities 表。
// 因为 CH 不支持 UPDATE，我们插入一条带更新字段的新版本行（ReplacingMergeTree 靠 updated_at 去重取最新）。
func updateSecurityInfo(ctx context.Context, ch *dwh.Client, code string, info *tdx.CompanyInfo) error {
	// 先查出现有行的必要字段（限定 type='stock' 避免同代码 index 冲突）
	q := fmt.Sprintf(`SELECT market, type, name, list_date FROM %s.securities FINAL WHERE code = '%s' AND type = 'stock' LIMIT 1`, ch.DB(), code)
	row := ch.Conn().QueryRow(ctx, q)

	var market, typ, name string
	var listDate time.Time
	if err := row.Scan(&market, &typ, &name, &listDate); err != nil {
		return fmt.Errorf("read existing: %w", err)
	}

	// 构造 industry 字段值
	industry := info.Industry // e.g. "食品饮料-酿酒"
	sector := info.Sector     // e.g. "食品饮料"
	province := info.Province
	business := info.Business

	batch, err := ch.Conn().PrepareBatch(ctx,
		fmt.Sprintf(`INSERT INTO %s.securities (code, market, type, name, list_date, industry, sector, province, business, updated_at)`, ch.DB()))
	if err != nil {
		return fmt.Errorf("prepare: %w", err)
	}
	if err := batch.Append(code, market, typ, name, listDate, industry, sector, province, business, time.Now()); err != nil {
		return fmt.Errorf("append: %w", err)
	}
	return batch.Send()
}

// 确保 model.TypeStock 可用
var _ = model.TypeStock
