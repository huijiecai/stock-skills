package model

type DataType string

const (
	TypeStock   DataType = "stock"
	TypeIndex   DataType = "index"
	TypeConcept DataType = "concept"
)

type Freq string

const (
	Freq1m  Freq = "1m"
	Freq5m  Freq = "5m"
	Freq15m Freq = "15m"
	Freq30m Freq = "30m"
	Freq60m Freq = "60m"
)

type Exchange string

const (
	ExchangeSH Exchange = "sh"
	ExchangeSZ Exchange = "sz"
	ExchangeBJ Exchange = "bj"
)
