package model

type Quote struct {
	Code      string  `json:"code"`
	Name      string  `json:"name,omitempty"`
	Price     float64 `json:"price"`
	PreClose  float64 `json:"pre_close"`
	ChangePct float64 `json:"change_pct"`
	Volume    int64   `json:"volume"`
	Amount    float64 `json:"amount"`
	PE        float64 `json:"pe,omitempty"`
	PB        float64 `json:"pb,omitempty"`
	MarketCap float64 `json:"market_cap,omitempty"`
	High      float64 `json:"high,omitempty"`
	Low       float64 `json:"low,omitempty"`
	Open      float64 `json:"open,omitempty"`
	HighLimit float64 `json:"high_limit,omitempty"`
	LowLimit  float64 `json:"low_limit,omitempty"`
}
