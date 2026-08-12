package tdx

import (
	"testing"
	"time"

	"github.com/injoyai/tdx/protocol"
)

func TestMapTradePreservesUnitsAndAggressorSide(t *testing.T) {
	snapshotAt := time.Date(2026, 8, 3, 14, 30, 0, 0, shanghaiLocation)
	trade := &protocol.Trade{
		Time:   time.Date(2026, 8, 3, 14, 29, 0, 0, shanghaiLocation),
		Price:  protocol.Price(51960),
		Volume: 100,
		Status: 0,
		Number: 12,
	}

	got := mapTrade("000636", trade, snapshotAt)

	if got.VolumeUnit != "hand" {
		t.Fatalf("volume unit = %q, want hand", got.VolumeUnit)
	}
	if got.Amount != 519_600 {
		t.Fatalf("amount = %v, want 519600", got.Amount)
	}
	if got.Side != "buy" {
		t.Fatalf("side = %q, want buy", got.Side)
	}
	if got.OrderCount != 12 {
		t.Fatalf("order count = %d, want 12", got.OrderCount)
	}
	if got.TradeDate != "2026-08-03" || got.AsOf != "2026-08-03T14:30:00+08:00" {
		t.Fatalf("unexpected timestamps: trade_date=%q as_of=%q", got.TradeDate, got.AsOf)
	}
}

func TestMapTradeMapsSellAndNeutral(t *testing.T) {
	now := time.Date(2026, 8, 3, 14, 30, 0, 0, shanghaiLocation)
	for status, want := range map[int]string{1: "sell", 2: "neutral"} {
		got := mapTrade("000636", &protocol.Trade{Time: now, Status: status}, now)
		if got.Side != want {
			t.Fatalf("status %d: side = %q, want %q", status, got.Side, want)
		}
	}
}

func TestMapMinuteMarksEstimatedAmountInYuan(t *testing.T) {
	now := time.Date(2026, 8, 3, 14, 30, 0, 0, shanghaiLocation)
	got := mapMinute("000636", protocol.PriceNumber{
		Time: "14:29", Price: protocol.Price(51960), Number: 100,
	}, now)

	if got.Amount != 519_600 {
		t.Fatalf("amount = %v, want 519600", got.Amount)
	}
	if !got.AmountEstimated {
		t.Fatal("minute amount must be marked estimated")
	}
	if got.VolumeUnit != "hand" {
		t.Fatalf("volume unit = %q, want hand", got.VolumeUnit)
	}
}
