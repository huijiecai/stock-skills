package tdx

import (
	"fmt"
	"strings"

	"github.com/injoyai/tdx/protocol"

	"github.com/huijiecai/stock/astock/internal/model"
)

// ListSecurities 拉取全市场标的清单（股票 + 指数）。
// 不使用依赖库的 GetStockCodeAll：其北交所规则只接受 92xxxx，会漏掉
// 43/83/87/88xxxx 存量股票。这里一次遍历三地代码表并按市场自行分类。
func (c *Client) ListSecurities() ([]*model.Security, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, err
	}

	out := make([]*model.Security, 0, 8000)

	// 股票和指数共用同一次代码表结果；ETF 等其他证券不入库。
	for _, ex := range []protocol.Exchange{protocol.ExchangeSH, protocol.ExchangeSZ, protocol.ExchangeBJ} {
		resp, err := cli.GetCodeAll(ex)
		if err != nil {
			return nil, fmt.Errorf("get code all %s: %w", ex.String(), err)
		}
		for _, v := range resp.List {
			typ := model.DataType("")
			switch {
			case isStockSecurity(ex.String(), v.Code):
				typ = model.TypeStock
			case isIndex(ex.String(), v.Code):
				typ = model.TypeIndex
			default:
				continue
			}
			out = append(out, &model.Security{
				Code:   v.Code,
				Market: ex.String(),
				Type:   typ,
				Name:   v.Name,
			})
		}
	}

	return out, nil
}

func isStockSecurity(market, code string) bool {
	if len(code) != 6 {
		return false
	}
	switch market {
	case "sh":
		return strings.HasPrefix(code, "6")
	case "sz":
		return strings.HasPrefix(code, "0") || strings.HasPrefix(code, "30")
	case "bj":
		for _, prefix := range []string{"43", "83", "87", "88", "92"} {
			if strings.HasPrefix(code, prefix) {
				return true
			}
		}
	}
	return false
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
