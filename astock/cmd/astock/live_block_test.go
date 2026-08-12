package main

import "testing"

func TestAggregateLiveBlockBreadth(t *testing.T) {
	blocks := map[string][]string{
		"880001": {"000001", "300001", "600001", "600002", "600003"},
	}
	names := map[string]string{
		"000001": "平安银行",
		"300001": "特锐德",
		"600001": "邯郸钢铁",
		"600002": "齐鲁石化",
		"600003": "ST东北高",
	}
	quotes := map[string]liveBlockStockQuote{
		"000001": {price: 11.00, preClose: 10.00, high: 11.00, low: 10.00, changePct: 10.00},
		"300001": {price: 8.00, preClose: 10.00, high: 10.00, low: 8.00, changePct: -20.00},
		"600001": {price: 10.20, preClose: 10.00, high: 10.30, low: 9.90, changePct: 2.00},
		"600002": {price: 10.00, preClose: 10.00, high: 10.10, low: 9.90, changePct: 0},
		// 600003 deliberately has no quote and must count as an uncovered member.
	}

	got := aggregateLiveBlockBreadth([]string{"880001"}, blocks, names, quotes)["880001"]
	if got.MemberCount != 5 || got.ValidCount != 4 {
		t.Fatalf("coverage = %d/%d, want 4/5", got.ValidCount, got.MemberCount)
	}
	if got.UpCount != 2 || got.DownCount != 1 || got.FlatCount != 1 {
		t.Fatalf("up/down/flat = %d/%d/%d, want 2/1/1", got.UpCount, got.DownCount, got.FlatCount)
	}
	if got.LimitUpCount != 1 || got.LimitDownCount != 1 {
		t.Fatalf("limit up/down = %d/%d, want 1/1", got.LimitUpCount, got.LimitDownCount)
	}
	if got.MedianChangePct != 1 {
		t.Fatalf("median = %.2f, want 1.00", got.MedianChangePct)
	}
}

func TestAggregateLiveBlockBreadthUsesSTLimit(t *testing.T) {
	blocks := map[string][]string{"880002": {"600003"}}
	names := map[string]string{"600003": "*ST东北高"}
	quotes := map[string]liveBlockStockQuote{
		"600003": {price: 9.50, preClose: 10.00, high: 10.00, low: 9.50, changePct: -5.00},
	}

	got := aggregateLiveBlockBreadth([]string{"880002"}, blocks, names, quotes)["880002"]
	if got.LimitDownCount != 1 {
		t.Fatalf("ST limit down count = %d, want 1", got.LimitDownCount)
	}
}

func TestMedianFloat64DoesNotMutateInput(t *testing.T) {
	values := []float64{3, 1, 2, 4}
	if got := medianFloat64(values); got != 2.5 {
		t.Fatalf("median = %.2f, want 2.50", got)
	}
	if values[0] != 3 || values[1] != 1 {
		t.Fatalf("input mutated: %#v", values)
	}
}
