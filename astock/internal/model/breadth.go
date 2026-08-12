package model

// BreadthPoint 是 TDX 指数 K 线携带的市场涨跌家数快照。
// Scope 标识统计市场，Name/Code 记录承载这组统计值的指数。
type BreadthPoint struct {
	Scope     string `json:"scope"`
	Name      string `json:"name"`
	Code      string `json:"code"`
	AsOf      string `json:"as_of"`
	UpCount   int    `json:"up_count"`
	DownCount int    `json:"down_count"`
	Valid     bool   `json:"valid"`
}
