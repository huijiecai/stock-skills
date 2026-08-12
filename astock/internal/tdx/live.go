package tdx

import (
	"fmt"
	"time"

	"github.com/huijiecai/stock/astock/internal/model"
	"github.com/injoyai/tdx/protocol"
)

// GetQuotes 拉取一组实时报价（含五档盘口）。code 不带前缀。
//
// 分流逻辑：
//   - 股票代码 → cli.GetQuote（上游已验证，内部 AddPrefix + 响应数量校验）
//   - 板块/指数代码 → 直接 protocol.MQuote framing（绕开 cli.GetQuote 的 DefaultCodes 依赖，K.Close 即真实点位）
//
// 为什么分流：之前全走自实现 framing 时，股票响应中 q.Code 会错位、五档盘口全 0；
// 上游 cli.GetQuote 对股票路径还做了响应校验与位置对齐，股票场景必须走上游。
func (c *Client) GetQuotes(codes []string) ([]*model.Quote, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, err
	}

	stockCodes := make([]string, 0, len(codes))
	indexCodes := make([]string, 0)
	for _, code := range codes {
		if IsBlockOrPureIndex(code) {
			indexCodes = append(indexCodes, code)
		} else {
			stockCodes = append(stockCodes, code)
		}
	}

	out := make([]*model.Quote, 0, len(codes))
	snapshotAt := liveSnapshotTime()

	// 股票走 cli.GetQuote（上游会 AddPrefix、验证响应数量、按请求顺序返回）
	if len(stockCodes) > 0 {
		// cli.GetQuote 内部会以 AddPrefix 原地改写 codes（共享底层数组），这里复制一份避免污染 stockCodes。
		args := append([]string(nil), stockCodes...)
		resp, err := cli.GetQuote(args...)
		if err != nil {
			return nil, fmt.Errorf("get stock quote: %w", err)
		}
		for i, q := range resp {
			if i >= len(stockCodes) {
				break
			}
			out = append(out, mapQuote(stockCodes[i], q, snapshotAt))
		}
	}

	// 板块/指数走底层 framing
	if len(indexCodes) > 0 {
		quotes, err := c.GetIndexQuotes(indexCodes)
		if err != nil {
			return nil, err
		}
		out = append(out, quotes...)
	}

	return out, nil
}

// GetIndexQuotes explicitly treats every code as an index and avoids stock-code ambiguity.
func (c *Client) GetIndexQuotes(codes []string) ([]*model.Quote, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, err
	}
	prefixed := make([]string, len(codes))
	for i, code := range codes {
		prefixed[i] = IndexCode(code)
	}
	f, err := protocol.MQuote.Frame(prefixed...)
	if err != nil {
		return nil, fmt.Errorf("index quote frame: %w", err)
	}
	result, err := cli.SendFrame(f)
	if err != nil {
		return nil, fmt.Errorf("get index quote: %w", err)
	}
	resp := result.(protocol.QuotesResp)
	if len(resp) != len(codes) {
		return nil, fmt.Errorf(
			"index quote count mismatch: requested %d, returned %d",
			len(codes), len(resp),
		)
	}
	out := make([]*model.Quote, 0, len(codes))
	snapshotAt := liveSnapshotTime()
	for i, q := range resp {
		out = append(out, mapQuote(codes[i], q, snapshotAt))
	}
	return out, nil
}

// mapQuote 将 protocol.Quote 转为 model.Quote。Code 取请求原始代码（响应中的 Code 不可信）。
func mapQuote(code string, q *protocol.Quote, snapshotAt time.Time) *model.Quote {
	quote := &model.Quote{
		Code:       code,
		TradeDate:  snapshotAt.Format("2006-01-02"),
		AsOf:       snapshotAt.Format(time.RFC3339),
		Price:      q.K.Close.Float64(),
		PreClose:   q.K.Last.Float64(),
		Open:       q.K.Open.Float64(),
		High:       q.K.High.Float64(),
		Low:        q.K.Low.Float64(),
		Volume:     int64(q.TotalHand),
		VolumeUnit: "hand",
		Amount:     q.Amount,
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
	return quote
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
	snapshotAt := liveSnapshotTime()
	for _, t := range resp.List {
		out = append(out, mapTrade(code, t, snapshotAt))
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
	snapshotAt := liveSnapshotTime()
	for _, m := range resp.List {
		out = append(out, mapMinute(code, m, snapshotAt))
	}
	return out, nil
}

var shanghaiLocation = time.FixedZone("Asia/Shanghai", 8*60*60)

func liveSnapshotTime() time.Time {
	return time.Now().In(shanghaiLocation)
}

func mapTrade(code string, trade *protocol.Trade, snapshotAt time.Time) *model.Tick {
	side := "neutral"
	switch trade.Status {
	case 0:
		side = "buy"
	case 1:
		side = "sell"
	}
	return &model.Tick{
		Code:       code,
		TradeDate:  trade.Time.Format("2006-01-02"),
		AsOf:       snapshotAt.Format(time.RFC3339),
		Time:       trade.Time.Format("15:04:05"),
		Price:      trade.Price.Float64(),
		Volume:     int64(trade.Volume),
		VolumeUnit: "hand",
		Amount:     float64(trade.Volume) * 100 * trade.Price.Float64(),
		Side:       side,
		OrderCount: trade.Number,
	}
}

func mapMinute(code string, minute protocol.PriceNumber, snapshotAt time.Time) *model.Tick {
	return &model.Tick{
		Code:            code,
		TradeDate:       snapshotAt.Format("2006-01-02"),
		AsOf:            snapshotAt.Format(time.RFC3339),
		Time:            minute.Time,
		Price:           minute.Price.Float64(),
		Volume:          int64(minute.Number),
		VolumeUnit:      "hand",
		Amount:          float64(minute.Number) * 100 * minute.Price.Float64(),
		AmountEstimated: true,
	}
}
