package tdx

import "testing"

func TestIsStockSecurityIncludesLegacyBeijingCodes(t *testing.T) {
	for _, tc := range []struct {
		market, code string
		want         bool
	}{
		{"sh", "600000", true},
		{"sz", "000001", true},
		{"sz", "300001", true},
		{"bj", "430047", true},
		{"bj", "830799", true},
		{"bj", "870001", true},
		{"bj", "880001", true},
		{"bj", "920001", true},
		{"bj", "899050", false},
		{"sh", "000001", false},
		{"sz", "399001", false},
	} {
		if got := isStockSecurity(tc.market, tc.code); got != tc.want {
			t.Fatalf("isStockSecurity(%q, %q)=%v want %v", tc.market, tc.code, got, tc.want)
		}
	}
}
