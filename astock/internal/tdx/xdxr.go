package tdx

import (
	"fmt"

	"github.com/huijiecai/stock/astock/internal/model"
)

// GetXDXR 拉取一只股票全部除权除息历史。
// 返回结果按 ex_date 升序，已转换为 model.XDXR。
//
// injoyai/tdx 的 GetGbbq 返回 GbbqResp，其中包含送转/分红/配股以及股本变动等多类事件，
// Category=1 才是 XRXD（除权除息），其他 category 用于股本变动跟踪。本函数只提取 Category=1。
func (c *Client) GetXDXR(code string) ([]*model.XDXR, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, err
	}

	resp, err := cli.GetGbbq(code)
	if err != nil {
		return nil, fmt.Errorf("get gbbq %s: %w", code, err)
	}
	if resp == nil {
		return nil, nil
	}

	out := make([]*model.XDXR, 0, len(resp.List))
	for _, g := range resp.List {
		if !g.IsXRXD() {
			continue
		}
		x := g.XRXD()
		// 类型推断：bonus/transfer 任一 > 0 是 split；rights > 0 是 rights；否则 dividend。
		evType := model.XDXRDividend
		if x.Songzhuangu > 0 {
			evType = model.XDXRSplit
		} else if x.Peigu > 0 {
			evType = model.XDXRRights
		}
		out = append(out, &model.XDXR{
			Code:        code,
			ExDate:      x.Time,
			Type:        evType,
			Bonus:       0, // 通达信 Songzhuangu 是"送+转"合计，bonus/transfer 无法单独区分，统一计入 Transfer
			Transfer:    float32(x.Songzhuangu),
			Dividend:    float32(x.Fenhong),
			RightsPrice: float32(x.Peigujia),
			RightsRatio: float32(x.Peigu),
		})
	}
	return out, nil
}
