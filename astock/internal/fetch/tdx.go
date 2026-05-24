package fetch

import (
	"context"
	"fmt"
	"net"
	"strings"
	"time"

	"github.com/injoyai/ios"
	"github.com/injoyai/tdx"
	"github.com/injoyai/tdx/protocol"
	"github.com/huijiecai/stock/astock/internal/model"
)

const tdxDialTimeout = 5 * time.Second

var _ Fetcher = (*TDX)(nil)

type TDX struct {
	client *tdx.Client
}

func NewTDX() (*TDX, error) {
	dialer := &net.Dialer{Timeout: tdxDialTimeout}
	dial := func(ctx context.Context) (ios.ReadWriteCloser, string, error) {
		var lastErr error
		for _, host := range tdx.Hosts {
			addr := host
			if !strings.Contains(addr, ":") {
				addr += ":7709"
			}
			c, err := dialer.DialContext(ctx, "tcp", addr)
			if err == nil {
				return c, addr, nil
			}
			lastErr = err
		}
		return nil, "", fmt.Errorf("all %d TDX hosts unreachable: %w", len(tdx.Hosts), lastErr)
	}
	c, err := tdx.DialWith(dial)
	if err != nil {
		return nil, fmt.Errorf("connect tdx: %w", err)
	}
	return &TDX{client: c}, nil
}

func (t *TDX) Close() {
	if t.client != nil {
		t.client.Close()
	}
}

// MinuteKline fetches minute-level kline data for the given code and frequency.
// For stocks, uses GetKline* methods; for indices, uses GetIndex* methods.
// Results are in chronological order (oldest first).
func (t *TDX) MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, opts ...Option) ([]model.Bar, error) {
	if t == nil || t.client == nil {
		return nil, fmt.Errorf("TDX not initialized")
	}
	options := &FetchOptions{}
	for _, o := range opts {
		o(options)
	}
	count := options.Limit
	if count <= 0 {
		count = 240
	}
	reqCount := uint16(count)
	if reqCount > 800 {
		reqCount = 800
	}

	isIndex := tp == model.TypeIndex
	code6 := code
	if len(code6) > 6 {
		code6 = code[len(code)-6:]
	}

	var resp *protocol.KlineResp
	var err error

	switch freq {
	case model.Freq1m:
		if isIndex {
			resp, err = t.client.GetIndexMinute(code6, 0, reqCount)
		} else {
			resp, err = t.client.GetKlineMinute(code6, 0, reqCount)
		}
	case model.Freq5m:
		if isIndex {
			resp, err = t.client.GetIndex5Minute(code6, 0, reqCount)
		} else {
			resp, err = t.client.GetKline5Minute(code6, 0, reqCount)
		}
	case model.Freq15m:
		if isIndex {
			resp, err = t.client.GetIndex15Minute(code6, 0, reqCount)
		} else {
			resp, err = t.client.GetKline15Minute(code6, 0, reqCount)
		}
	case model.Freq30m:
		if isIndex {
			resp, err = t.client.GetIndex30Minute(code6, 0, reqCount)
		} else {
			resp, err = t.client.GetKline30Minute(code6, 0, reqCount)
		}
	case model.Freq60m:
		if isIndex {
			resp, err = t.client.GetIndex60Minute(code6, 0, reqCount)
		} else {
			resp, err = t.client.GetKline60Minute(code6, 0, reqCount)
		}
	default:
		return nil, fmt.Errorf("unsupported freq: %s", freq)
	}
	if err != nil {
		return nil, fmt.Errorf("tdx minute kline: %w", err)
	}

	bars := make([]model.Bar, 0, len(resp.List))
	for _, k := range resp.List {
		bar := model.Bar{
			Code:   code,
			Type:   tp,
			Freq:   freq,
			Time:   k.Time,
			Open:   k.Open.Float64(),
			High:   k.High.Float64(),
			Low:    k.Low.Float64(),
			Close:  k.Close.Float64(),
			Volume: k.Volume,
			Amount: k.Amount.Float64(),
		}
		if options.Start != "" {
			startT, err := time.Parse("2006-01-02", options.Start)
			if err == nil && bar.Time.Before(startT) {
				continue
			}
		}
		if options.End != "" {
			endT, err := time.Parse("2006-01-02", options.End)
			if err == nil && bar.Time.After(endT.Add(24*time.Hour)) {
				continue
			}
		}
		bars = append(bars, bar)
	}
	return bars, nil
}

// DailyKline fetches daily kline data for the given code.
// Uses GetKlineDay for stocks, GetIndexDay for indices.
func (t *TDX) DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error) {
	if t == nil || t.client == nil {
		return nil, fmt.Errorf("TDX not initialized")
	}
	options := &FetchOptions{}
	for _, o := range opts {
		o(options)
	}
	count := options.Limit
	if count <= 0 {
		count = 30
	}
	reqCount := uint16(count)
	if reqCount > 800 {
		reqCount = 800
	}

	code6 := code
	if len(code6) > 6 {
		code6 = code[len(code)-6:]
	}

	var resp *protocol.KlineResp
	var err error
	if tp == model.TypeIndex {
		resp, err = t.client.GetIndexDay(code6, 0, reqCount)
	} else {
		resp, err = t.client.GetKlineDay(code6, 0, reqCount)
	}
	if err != nil {
		return nil, fmt.Errorf("tdx daily kline: %w", err)
	}

	bars := make([]model.Bar, 0, len(resp.List))
	for _, k := range resp.List {
		bars = append(bars, model.Bar{
			Code:      code,
			Type:      tp,
			TradeDate: k.Time.Format("2006-01-02"),
			Open:      k.Open.Float64(),
			High:      k.High.Float64(),
			Low:       k.Low.Float64(),
			Close:     k.Close.Float64(),
			Volume:    k.Volume,
			Amount:    k.Amount.Float64(),
		})
	}
	return bars, nil
}

func (t *TDX) TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error) {
	return nil, fmt.Errorf("TDX: TodayMinute not implemented, use EastMoney")
}

func (t *TDX) RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error) {
	return nil, fmt.Errorf("TDX: RealTimeQuote not implemented, use EastMoney")
}

func (t *TDX) StockList(ctx context.Context) ([]model.Stock, error) {
	return nil, fmt.Errorf("TDX: StockList not implemented, use EastMoney")
}

func (t *TDX) ConceptList(ctx context.Context) ([]model.Concept, error) {
	return nil, fmt.Errorf("TDX: ConceptList not implemented, use EastMoney")
}

func (t *TDX) ConceptConstituents(ctx context.Context, code string) ([]string, error) {
	return nil, fmt.Errorf("TDX: ConceptConstituents not implemented, use EastMoney")
}

func (t *TDX) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
	return nil, fmt.Errorf("TDX: RankVolume not implemented, use EastMoney")
}

func (t *TDX) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
	return nil, fmt.Errorf("TDX: RankLimitUp not implemented, use EastMoney")
}
