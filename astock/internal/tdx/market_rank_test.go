package tdx

import (
	"encoding/binary"
	"math"
	"testing"
)

func TestDecodeMarketRank(t *testing.T) {
	body := make([]byte, 4)
	binary.LittleEndian.PutUint16(body[2:4], 1)
	body = append(body, 0)
	body = append(body, []byte("000636")...)
	body = binary.LittleEndian.AppendUint16(body, 17)
	for _, value := range []int64{
		5196, -261, -396, 122, -495, 0, 0, 1810210, 3067,
	} {
		body = append(body, encodeMarketRankValue(value)...)
	}
	body = binary.LittleEndian.AppendUint32(body, math.Float32bits(9_207_767_040))
	for _, value := range []int64{800000, 1010210, 0, 0, 1, 1, 3067, 2218} {
		body = append(body, encodeMarketRankValue(value)...)
	}
	tail := make([]byte, 56)
	binary.LittleEndian.PutUint16(tail[2:4], uint16(int16(125)))
	body = append(body, tail...)

	items, err := decodeMarketRank(body)
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 {
		t.Fatalf("len=%d", len(items))
	}
	got := items[0]
	if got.Market != "SZ" || got.Code != "000636" || got.Active != 17 {
		t.Fatalf("identity mismatch: %#v", got)
	}
	if got.Price != 51.96 || got.PreClose != 49.35 || got.Open != 48.00 || got.High != 53.18 || got.Low != 47.01 {
		t.Fatalf("prices mismatch: %#v", got)
	}
	if got.Volume != 1810210 || got.CurrentVolume != 3067 || got.InVolume != 800000 || got.OutVolume != 1010210 {
		t.Fatalf("volumes mismatch: %#v", got)
	}
	if got.RiseSpeed != 1.25 {
		t.Fatalf("rise speed=%f", got.RiseSpeed)
	}
}

func TestDecodeMarketRankRejectsTruncatedRow(t *testing.T) {
	body := []byte{0, 0, 1, 0, 0}
	if _, err := decodeMarketRank(body); err == nil {
		t.Fatal("expected truncated row error")
	}
}

func TestMarketRankCategory(t *testing.T) {
	for market, want := range map[string]uint16{"all": 6, "sh": 0, "sz": 2, "bj": 12} {
		got, err := marketRankCategory(market)
		if err != nil || got != want {
			t.Fatalf("market=%s got=%d err=%v", market, got, err)
		}
	}
	if _, err := marketRankCategory("hk"); err == nil {
		t.Fatal("expected invalid market error")
	}
}

func encodeMarketRankValue(value int64) []byte {
	negative := value < 0
	if negative {
		value = -value
	}
	first := byte(value & 0x3F)
	value >>= 6
	if negative {
		first |= 0x40
	}
	if value > 0 {
		first |= 0x80
	}
	result := []byte{first}
	for value > 0 {
		part := byte(value & 0x7F)
		value >>= 7
		if value > 0 {
			part |= 0x80
		}
		result = append(result, part)
	}
	return result
}
