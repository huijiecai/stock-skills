package main

import (
	"testing"

	"github.com/huijiecai/stock/astock/internal/model"
)

func TestIsMainBoardCandidateCode(t *testing.T) {
	for _, code := range []string{"000021", "001389", "002371", "600584", "601318", "603986", "605376"} {
		if !isMainBoardCandidateCode(code) {
			t.Fatalf("expected main-board code: %s", code)
		}
	}
	for _, code := range []string{"300223", "688072", "920001"} {
		if isMainBoardCandidateCode(code) {
			t.Fatalf("unexpected non-main-board code: %s", code)
		}
	}
}

func TestMarketCandidateReasons(t *testing.T) {
	quote := &model.Quote{
		Code: "002371", Price: 744.60, PreClose: 676.91, High: 744.60,
		Low: 678.43, ChangePct: 9.9998, Amount: 10_585_799_680,
	}
	reasons, _, isLimit := marketCandidateReasons(quote, 1_000_000_000)
	if !isLimit {
		t.Fatal("expected limit-up detection")
	}
	if len(reasons) < 2 || reasons[0] != "limit_up" {
		t.Fatalf("unexpected reasons: %#v", reasons)
	}
}
