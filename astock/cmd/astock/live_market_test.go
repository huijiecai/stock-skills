package main

import (
	"testing"
	"time"
)

func TestValidateLiveMarketOptions(t *testing.T) {
	if err := validateLiveMarketOptions("all", "amount", "desc", "all", 0, 50); err != nil {
		t.Fatalf("valid options rejected: %v", err)
	}
	for _, tc := range []struct {
		market, sortBy, order, state string
		offset, limit                int
	}{
		{"hk", "amount", "desc", "all", 0, 50},
		{"all", "turnover", "desc", "all", 0, 50},
		{"all", "amount", "sideways", "all", 0, 50},
		{"all", "amount", "desc", "strong", 0, 50},
		{"all", "amount", "desc", "all", -1, 50},
		{"all", "amount", "desc", "all", 0, 501},
	} {
		if err := validateLiveMarketOptions(tc.market, tc.sortBy, tc.order, tc.state, tc.offset, tc.limit); err == nil {
			t.Fatalf("invalid options accepted: %#v", tc)
		}
	}
}

func TestLivePriceLimitState(t *testing.T) {
	asOf := time.Date(2026, 8, 5, 15, 0, 0, 0, time.Local)
	old := time.Date(2020, 1, 1, 0, 0, 0, 0, time.Local)

	tests := []struct {
		name, code, market, securityName string
		price, preClose                  float64
		want                             string
	}{
		{"main up", "000636", "SZ", "风华高科", 52.18, 47.44, "limit_up"},
		{"star up", "688001", "SH", "华兴源创", 24.00, 20.00, "limit_up"},
		{"st up", "600001", "SH", "*ST示例", 5.25, 5.00, "limit_up"},
		{"beijing down", "920001", "BJ", "北交示例", 7.00, 10.00, "limit_down"},
		{"normal", "000636", "SZ", "风华高科", 51.96, 47.44, "normal"},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			state, _ := livePriceLimitState(LiveMarketRow{
				Code: tc.code, Market: tc.market, Price: tc.price, PreClose: tc.preClose,
			}, liveMarketMeta{Name: tc.securityName, ListDate: old}, nil, asOf)
			if state != tc.want {
				t.Fatalf("state=%s want=%s", state, tc.want)
			}
		})
	}
}

func TestNewListingHasNoPriceLimit(t *testing.T) {
	tradeDates := []time.Time{
		time.Date(2026, 7, 30, 0, 0, 0, 0, time.Local),
		time.Date(2026, 7, 31, 0, 0, 0, 0, time.Local),
		time.Date(2026, 8, 3, 0, 0, 0, 0, time.Local),
		time.Date(2026, 8, 4, 0, 0, 0, 0, time.Local),
		time.Date(2026, 8, 5, 0, 0, 0, 0, time.Local),
		time.Date(2026, 8, 6, 0, 0, 0, 0, time.Local),
	}
	listDate := tradeDates[0]
	if hasDailyPriceLimit("SZ", listDate, tradeDates, tradeDates[4].Add(15*time.Hour)) {
		t.Fatal("first five trading days should have no daily price limit")
	}
	if !hasDailyPriceLimit("SZ", listDate, tradeDates, tradeDates[5].Add(15*time.Hour)) {
		t.Fatal("sixth trading day should have a daily price limit")
	}
	if hasDailyPriceLimit("BJ", listDate, tradeDates, tradeDates[0].Add(15*time.Hour)) {
		t.Fatal("Beijing listing day should have no daily price limit")
	}
	if !hasDailyPriceLimit("BJ", listDate, tradeDates, tradeDates[1].Add(15*time.Hour)) {
		t.Fatal("Beijing stock should have a daily price limit after listing day")
	}
}

func TestSortLiveMarketRows(t *testing.T) {
	rows := []LiveMarketRow{
		{Code: "000003", Amount: 20},
		{Code: "000002", Amount: 20},
		{Code: "000001", Amount: 10},
	}
	sortLiveMarketRows(rows, "amount", "desc")
	want := []string{"000002", "000003", "000001"}
	for i := range want {
		if rows[i].Code != want[i] {
			t.Fatalf("row %d=%s want=%s", i, rows[i].Code, want[i])
		}
	}
}
