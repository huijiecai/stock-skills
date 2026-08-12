package main

import (
	"testing"
	"time"

	"github.com/huijiecai/stock/astock/internal/model"
)

func TestLiveBreadthSourcesFollowRequestedMarkets(t *testing.T) {
	sources, err := liveBreadthSourcesForIndices([]string{"sh000001", "000016", "399001", "399006"})
	if err != nil {
		t.Fatal(err)
	}
	if len(sources) != 2 {
		t.Fatalf("sources = %d, want 2", len(sources))
	}
	if sources[0].scope != "sh" || sources[0].code != "sh000001" {
		t.Fatalf("unexpected sh source: %#v", sources[0])
	}
	if sources[1].scope != "sz" || sources[1].code != "399001" {
		t.Fatalf("unexpected sz source: %#v", sources[1])
	}
}

func TestLatestBreadthAsOfUsesMarketTime(t *testing.T) {
	got := latestBreadthAsOf([]*model.BreadthPoint{
		{AsOf: "2026-08-04T14:59:00+08:00", Valid: true},
		{AsOf: "2026-08-04T15:00:00+08:00", Valid: true},
		{AsOf: "2026-08-04T15:01:00+08:00", Valid: false},
	})
	if got != "2026-08-04T15:00:00+08:00" {
		t.Fatalf("as_of = %q", got)
	}
}

func TestSumValidBreadthIgnoresUnavailableSource(t *testing.T) {
	up, down := sumValidBreadth([]*model.BreadthPoint{
		{UpCount: 100, DownCount: 80, Valid: true},
		{UpCount: 20, DownCount: 30, Valid: true},
		{UpCount: 999, DownCount: 999, Valid: false},
		nil,
	})
	if up != 120 || down != 110 {
		t.Fatalf("sum = %d/%d, want 120/110", up, down)
	}
}

func TestValidateLiveBreadthRejectsStaleData(t *testing.T) {
	now := time.Date(2026, 8, 4, 10, 0, 0, 0, liveBreadthLocation)
	err := validateLiveBreadth([]*model.BreadthPoint{
		{Name: "上证指数", AsOf: "2026-08-03T15:00:00+08:00", UpCount: 100, Valid: true},
	}, now)
	if err == nil {
		t.Fatal("expected stale breadth data to be rejected")
	}
}
