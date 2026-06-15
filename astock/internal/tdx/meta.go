package tdx

import (
	"fmt"
	"strings"

	"github.com/injoyai/tdx/protocol"

	"github.com/huijiecai/stock/astock/internal/model"
)

// ListSecurities 拉取全市场标的清单（股票 + 指数）。
// 注意：injoyai/tdx 的 GetStockCodeAll 已经按 ExchangeSH/SZ/BJ 三家拉齐并加好 sh/sz/bj 前缀。
// 我们解析前缀后填到 Security.Market；type 由调用方指定（stock/index）。
// 不同步 ETF：项目不交易基金、不需要 ETF 数据。
func (c *Client) ListSecurities() ([]*model.Security, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, err
	}

	out := make([]*model.Security, 0, 8000)

	// 1) 股票（包含主板/科创板/创业板/北交所）
	stocks, err := cli.GetStockCodeAll()
	if err != nil {
		return nil, fmt.Errorf("get stock code all: %w", err)
	}
	for _, prefixed := range stocks {
		market, code, ok := splitPrefixed(prefixed)
		if !ok {
			continue
		}
		out = append(out, &model.Security{
			Code:   code,
			Market: market,
			Type:   model.TypeStock,
		})
	}

	// 2) 指数（手动按 SH/SZ 拉两次 GetCodeAll，过滤指数代码段）
	for _, ex := range []protocol.Exchange{protocol.ExchangeSH, protocol.ExchangeSZ, protocol.ExchangeBJ} {
		resp, err := cli.GetCodeAll(ex)
		if err != nil {
			return nil, fmt.Errorf("get code all %s: %w", ex.String(), err)
		}
		for _, v := range resp.List {
			if !isIndex(ex.String(), v.Code) {
				continue
			}
			out = append(out, &model.Security{
				Code:   v.Code,
				Market: ex.String(),
				Type:   model.TypeIndex,
				Name:   v.Name,
			})
		}
	}

	// （3）ETF：已移除。项目不交易 ETF，避免 securities 表几百行无用数据。

	// 给股票回填名字（GetStockCodeAll 不返回 Name，需要再扫一遍 GetCodeAll）
	nameMap := make(map[string]string, 8000)
	for _, ex := range []protocol.Exchange{protocol.ExchangeSH, protocol.ExchangeSZ, protocol.ExchangeBJ} {
		resp, err := cli.GetCodeAll(ex)
		if err != nil {
			return nil, fmt.Errorf("get code all (name) %s: %w", ex.String(), err)
		}
		for _, v := range resp.List {
			nameMap[ex.String()+":"+v.Code] = v.Name
		}
	}
	for _, s := range out {
		if s.Name != "" {
			continue
		}
		s.Name = nameMap[s.Market+":"+s.Code]
	}

	return out, nil
}

// splitPrefixed 拆 "sz000001" → "sz", "000001"。
func splitPrefixed(prefixed string) (string, string, bool) {
	if len(prefixed) != 8 {
		return "", "", false
	}
	pfx := strings.ToLower(prefixed[:2])
	switch pfx {
	case "sh", "sz", "bj":
		return pfx, prefixed[2:], true
	}
	return "", "", false
}

// isIndex 判断 (market, code) 是否是指数。
//
//	sh: 000xxx
//	sz: 399xxx
//	bj: 899xxx
func isIndex(market, code string) bool {
	if len(code) != 6 {
		return false
	}
	switch market {
	case "sh":
		return strings.HasPrefix(code, "000")
	case "sz":
		return strings.HasPrefix(code, "399")
	case "bj":
		return strings.HasPrefix(code, "899")
	}
	return false
}
