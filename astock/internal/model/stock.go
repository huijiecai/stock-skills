package model

type Stock struct {
	Code     string `json:"code"`
	Name     string `json:"name"`
	Exchange string `json:"exchange"`
	Sector   string `json:"sector,omitempty"`
}

type Concept struct {
	Code       string `json:"code"`
	Name       string `json:"name"`
	StockCount int    `json:"stock_count"`
}

type ConceptConstituent struct {
	ConceptCode string `json:"concept_code"`
	StockCode   string `json:"stock_code"`
}
