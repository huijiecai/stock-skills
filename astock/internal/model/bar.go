package model

import "time"

type Bar struct {
	Code      string    `json:"code"`
	Type      DataType  `json:"type"`
	TradeDate string    `json:"trade_date"`
	Time      time.Time `json:"time,omitempty"`
	Freq      Freq      `json:"freq,omitempty"`
	Open      float64   `json:"open"`
	High      float64   `json:"high"`
	Low       float64   `json:"low"`
	Close     float64   `json:"close"`
	PreClose  float64   `json:"pre_close,omitempty"`
	ChangePct float64   `json:"change_pct,omitempty"`
	Volume    int64     `json:"volume"`
	Amount    float64   `json:"amount"`
	Turnover  float64   `json:"turnover,omitempty"`
	AvgPrice  float64   `json:"avg_price,omitempty"`
}

type Tick struct {
	Code      string  `json:"code"`
	Time      string  `json:"time"`
	Price     float64 `json:"price"`
	Volume    int64   `json:"volume"`
	Amount    float64 `json:"amount"`
	AvgPrice  float64 `json:"avg_price,omitempty"`
}
