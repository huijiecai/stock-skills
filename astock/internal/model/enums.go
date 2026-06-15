package model

type DataType string

const (
	TypeStock DataType = "stock"
	TypeIndex DataType = "index"
	TypeBond  DataType = "bond"
	TypeBlock DataType = "block"
)

type Freq string

const (
	Freq1m  Freq = "1m"
	Freq5m  Freq = "5m"
	Freq15m Freq = "15m"
	Freq30m Freq = "30m"
	Freq60m Freq = "60m"
	FreqDay Freq = "day"
)

type Exchange string

const (
	ExchangeSH Exchange = "sh"
	ExchangeSZ Exchange = "sz"
	ExchangeBJ Exchange = "bj"
)

// XDXR 事件类型
const (
	XDXRDividend = "dividend" // 派息
	XDXRSplit    = "split"    // 送转
	XDXRRights   = "rights"   // 配股
)

// 板块类型
const (
	BlockConcept = "concept" // 概念
	BlockRegion  = "region"  // 地域
	BlockStyle   = "style"   // 风格
	BlockIndex   = "index"   // 指数板
)

