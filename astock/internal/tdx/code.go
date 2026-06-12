// Package tdx 代码工具：解析市场前缀、修复指数代码识别。
//
// 背景：injoyai/tdx 的 AddPrefix 把 "000001" 识别为 sz000001（深圳平安银行），
// 而上证综指也叫 000001（应为 sh000001）。所以拉指数时必须自己拼好 sh/sz/bj 前缀，
// 否则 GetIndexDay("000001") 会被路由到深圳，结果 panic 或返回错误数据。
//
// 经验来源：astock 历史 indexCode 修复（v0.0.78 兼容补丁）。
package tdx

import "strings"

// MarketOf 从 6 位代码推断交易所（默认按"股票"语义）。
//
//	60xxxx, 68xxxx, 9xxxxx → sh
//	00xxxx, 30xxxx, 20xxxx → sz
//	8xxxxx, 4xxxxx → bj
//	否则返回 "" 表示无法判断。
func MarketOf(code string) string {
	if len(code) != 6 {
		return ""
	}
	switch code[:2] {
	case "60", "68":
		return "sh"
	case "00", "30", "20":
		return "sz"
	}
	switch code[:1] {
	case "9":
		return "sh"
	case "8", "4":
		return "bj"
	}
	return ""
}

// IndexCode 把 6 位指数代码补全为带前缀的形式（指数语义）：
//
//	000xxx → sh000xxx（上证系列：上证综指、上证 50、沪深 300 等）
//	399xxx → sz399xxx（深证系列：深证成指、创业板指、中证 500 等）
//	899xxx → bj899xxx（北证系列）
//
// 已经带前缀（长度 8 且开头是 sh/sz/bj）则原样返回。
func IndexCode(code string) string {
	low := strings.ToLower(code)
	if len(low) == 8 && (strings.HasPrefix(low, "sh") || strings.HasPrefix(low, "sz") || strings.HasPrefix(low, "bj")) {
		return low
	}
	if len(code) != 6 {
		return code
	}
	switch code[:3] {
	case "000":
		return "sh" + code
	case "399":
		return "sz" + code
	case "899":
		return "bj" + code
	}
	// 通达信板块指数：880xxx 概念、881xxx 行业、884xxx 风格、885xxx 地域 → sh 市场
	switch code[:2] {
	case "88":
		return "sh" + code
	}
	return code
}

// MarketOfIndex 返回指数代码所属市场（sh/sz/bj），输入 6 位代码。
func MarketOfIndex(code string) string {
	if len(code) != 6 {
		return ""
	}
	switch code[:3] {
	case "000":
		return "sh"
	case "399":
		return "sz"
	case "899":
		return "bj"
	}
	// 通达信板块指数统一作为 sh 市场识别
	if code[:2] == "88" {
		return "sh"
	}
	return ""
}
