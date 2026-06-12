package tdx

import (
	"fmt"

	"github.com/huijiecai/stock/astock/internal/model"
	"github.com/injoyai/tdx/protocol"
)

// GetQuotes 拉取一组实时报价（含五档盘口）。code 不带前缀，函数内部按规则补 sh/sz/bj。
// 绕过 cli.GetQuote 避免 DefaultCodes 依赖，直接使用底层 Frame 协议。
func (c *Client) GetQuotes(codes []string) ([]*model.Quote, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, err
	}

	prefixed := make([]string, 0, len(codes))
	for _, code := range codes {
		if m := MarketOfIndex(code); m != "" {
			prefixed = append(prefixed, m+code)
			continue
		}
		if m := MarketOf(code); m != "" {
			prefixed = append(prefixed, m+code)
			continue
		}
		prefixed = append(prefixed, code)
	}

	// 直接使用底层协议，避免 DefaultCodes 未初始化问题
	f, err := protocol.MQuote.Frame(prefixed...)
	if err != nil {
		return nil, fmt.Errorf("quote frame: %w", err)
	}
	result, err := cli.SendFrame(f)
	if err != nil {
		return nil, fmt.Errorf("get quote: %w", err)
	}
	resp := result.(protocol.QuotesResp)

	out := make([]*model.Quote, 0, len(resp))
	for _, q := range resp {
		quote := &model.Quote{
			Code:     q.Code,
			Price:    q.K.Close.Float64(),
			PreClose: q.K.Last.Float64(),
			Open:     q.K.Open.Float64(),
			High:     q.K.High.Float64(),
			Low:      q.K.Low.Float64(),
			Volume:   int64(q.TotalHand),
			Amount:   q.Amount,
		}
		if quote.PreClose > 0 {
			quote.ChangePct = (quote.Price - quote.PreClose) / quote.PreClose * 100
		}
		for i := 0; i < 5; i++ {
			quote.Bids[i] = model.QuoteLevel{
				Price:  q.BuyLevel[i].Price.Float64(),
				Volume: int64(q.BuyLevel[i].Number),
			}
			quote.Asks[i] = model.QuoteLevel{
				Price:  q.SellLevel[i].Price.Float64(),
				Volume: int64(q.SellLevel[i].Number),
			}
		}
		out = append(out, quote)
	}
	return out, nil
}

// GetTradeAll 拉取一只股票当日全部分笔成交（最早 9:25 集合竞价 → 最新一笔）。
func (c *Client) GetTradeAll(code string) ([]*model.Tick, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, err
	}

	resp, err := cli.GetTradeAll(code)
	if err != nil {
		return nil, fmt.Errorf("get trade all %s: %w", code, err)
	}
	if resp == nil {
		return nil, nil
	}

	out := make([]*model.Tick, 0, len(resp.List))
	for _, t := range resp.List {
		out = append(out, &model.Tick{
			Code:   code,
			Time:   t.Time.Format("15:04:05"),
			Price:  t.Price.Float64(),
			Volume: int64(t.Volume),
			Amount: float64(t.Volume) * t.Price.Float64(),
		})
	}
	return out, nil
}

// GetMinute 拉取一只标的当日实时分时（241 个时间点：9:30 起每分钟一个）。
func (c *Client) GetMinute(code string, dataType model.DataType) ([]*model.Tick, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, err
	}

	target := code
	if dataType == model.TypeIndex {
		target = IndexCode(code)
	}
	resp, err := cli.GetMinute(target)
	if err != nil {
		return nil, fmt.Errorf("get minute %s: %w", code, err)
	}
	if resp == nil {
		return nil, nil
	}

	out := make([]*model.Tick, 0, len(resp.List))
	for _, m := range resp.List {
		out = append(out, &model.Tick{
			Code:   code,
			Time:   m.Time,
			Price:  m.Price.Float64(),
			Volume: int64(m.Number),
			Amount: float64(m.Number) * m.Price.Float64(),
		})
	}
	return out, nil
}
