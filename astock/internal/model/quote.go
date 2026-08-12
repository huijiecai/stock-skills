package model

// Quote 实时报价快照（含五档盘口）。
// 仅在 live 命令使用，不落库。
type Quote struct {
	Code       string  `json:"code"`
	Name       string  `json:"name,omitempty"`
	TradeDate  string  `json:"trade_date"`
	AsOf       string  `json:"as_of"`
	Price      float64 `json:"price"` // 最新价
	PreClose   float64 `json:"pre_close"`
	ChangePct  float64 `json:"change_pct"`
	Volume     int64   `json:"volume"`
	VolumeUnit string  `json:"volume_unit"`
	Amount     float64 `json:"amount"`
	Open       float64 `json:"open,omitempty"`
	High       float64 `json:"high,omitempty"`
	Low        float64 `json:"low,omitempty"`

	// 五档盘口
	Bids [5]QuoteLevel `json:"bids,omitempty"` // 买 1–买 5
	Asks [5]QuoteLevel `json:"asks,omitempty"` // 卖 1–卖 5
}
