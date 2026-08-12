package sync

import (
	"testing"
	"time"

	"github.com/huijiecai/stock/astock/internal/model"
)

func TestMergeSecurityMetadataPreservesExistingFieldsAndFillsNewIPODate(t *testing.T) {
	oldDate := time.Date(2010, 1, 1, 0, 0, 0, 0, time.Local)
	newDate := time.Date(2026, 8, 5, 0, 0, 0, 0, time.Local)
	existing := map[securityKey]*model.Security{
		{Code: "000001", Market: "sz", Type: model.TypeStock}: {
			Code: "000001", Market: "sz", Type: model.TypeStock, Name: "平安银行", ListDate: oldDate,
			Industry: "银行", Sector: "金融", Province: "广东", Business: "银行业务",
		},
	}
	fetched := []*model.Security{
		{Code: "000001", Market: "sz", Type: model.TypeStock, Name: "平安银行"},
		{Code: "920001", Market: "bj", Type: model.TypeStock, Name: "北交示例"},
		{Code: "920002", Market: "bj", Type: model.TypeStock, Name: "缺失日期"},
		{Code: "000001", Market: "sz", Type: model.TypeStock, Name: "重复行"},
	}
	lookups := 0
	merged, result := mergeSecurityMetadata(fetched, existing, func(market, code string) (time.Time, error) {
		lookups++
		if code == "920001" {
			return newDate, nil
		}
		return time.Time{}, errMissingDate
	})
	if lookups != 2 {
		t.Fatalf("lookups=%d want 2", lookups)
	}
	if len(merged) != 2 {
		t.Fatalf("merged=%d want 2", len(merged))
	}
	if result.NewStocks != 2 || result.ListDatesFilled != 1 || len(result.PendingStocks) != 1 {
		t.Fatalf("unexpected result: %#v", result)
	}
	if merged[0].Industry != "银行" || merged[0].ListDate != oldDate {
		t.Fatalf("existing fields were not preserved: %#v", merged[0])
	}
	if merged[1].ListDate != newDate {
		t.Fatalf("new list date=%v want=%v", merged[1].ListDate, newDate)
	}
}

type missingDateError struct{}

func (missingDateError) Error() string { return "missing date" }

var errMissingDate error = missingDateError{}
