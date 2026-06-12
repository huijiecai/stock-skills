package model

import "time"

// Security 一只可交易标的（股票/指数/ETF/可转债）。
// 对应 ClickHouse 表 securities。
type Security struct {
	Code       string    `json:"code"`         // 6 位代码
	Market     string    `json:"market"`       // sh/sz/bj
	Type       DataType  `json:"type"`         // stock/index/etf/bond
	Name       string    `json:"name"`         // 中文名称
	ListDate   time.Time `json:"list_date"`    // 上市日期
	DelistDate time.Time `json:"delist_date,omitempty"`
	// F10 公司信息
	Industry string `json:"industry,omitempty"` // 申万二级行业
	Sector   string `json:"sector,omitempty"`   // 申万一级行业
	Province string `json:"province,omitempty"` // 注册地
	Business string `json:"business,omitempty"` // 主营业务简述
}

// Block 板块/概念（行业、地域、风格、指数板）。
type Block struct {
	Code       string `json:"code"`        // TDX 板块代码，如 880472
	Name       string `json:"name"`        // 板块名称
	Type       string `json:"type"`        // concept/region/style/index
	StockCount uint32 `json:"stock_count"` // 成分股数量
}

// BlockConstituent 板块成分股关系。
type BlockConstituent struct {
	BlockCode string `json:"block_code"`
	StockCode string `json:"stock_code"`
}

// TradeCalendar 交易日历。
type TradeCalendar struct {
	TradeDate time.Time `json:"trade_date"`
	IsOpen    uint8     `json:"is_open"` // 1 开市 / 0 休市
}

// XDXR 除权除息记录（复权计算的基础原料）。
type XDXR struct {
	Code        string    `json:"code"`
	ExDate      time.Time `json:"ex_date"` // 除权除息日
	Type        string    `json:"type"`    // dividend/split/rights
	Bonus       float32   `json:"bonus"`   // 每 10 股送股
	Transfer    float32   `json:"transfer"` // 每 10 股转增
	Dividend    float32   `json:"dividend"` // 每 10 股派息（元）
	RightsPrice float32   `json:"rights_price"`
	RightsRatio float32   `json:"rights_ratio"`
}

// Finance 财务数据（季度报告期）。
type Finance struct {
	Code           string    `json:"code"`
	ReportDate     time.Time `json:"report_date"`
	Revenue        float64   `json:"revenue"`         // 营收
	NetProfit      float64   `json:"net_profit"`      // 净利
	EPS            float32   `json:"eps"`             // 每股收益
	BPS            float32   `json:"bps"`             // 每股净资产
	ROE            float32   `json:"roe"`             // 净资产收益率 %
	TotalShare     uint64    `json:"total_share"`     // 总股本
	FloatShare     uint64    `json:"float_share"`     // 流通股本
	TotalAssets    float64   `json:"total_assets"`
	TotalLiability float64   `json:"total_liability"`
}

// QuoteLevel 五档盘口中的一档。
type QuoteLevel struct {
	Price  float64 `json:"price"`
	Volume int64   `json:"volume"`
}
