package fetch

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"time"

	"github.com/huijiecai/stock/astock/internal/model"
)

var _ Fetcher = (*Baidu)(nil)

type Baidu struct {
	client *http.Client
}

func NewBaidu() *Baidu {
	return &Baidu{
		client: &http.Client{Timeout: 15 * time.Second},
	}
}

func (b *Baidu) doGet(ctx context.Context, urlStr string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", urlStr, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
	resp, err := b.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("baidu get: %w", err)
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}
	return body, nil
}

// DailyKline fetches daily kline data from Baidu Finance API.
func (b *Baidu) DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error) {
	options := &FetchOptions{}
	for _, o := range opts {
		o(options)
	}
	limit := options.Limit
	if limit <= 0 {
		limit = 30
	}

	params := url.Values{}
	params.Set("all", "1")
	params.Set("isIndex", "false")
	params.Set("isBk", "false")
	params.Set("isBlock", "false")
	params.Set("isFutures", "false")
	params.Set("isStock", "true")
	params.Set("newFormat", "1")
	params.Set("group", "quotation_kline_ab")
	params.Set("finClientType", "pc")
	params.Set("code", code)
	params.Set("ktype", "1") // 1=daily kline

	urlStr := "https://finance.pae.baidu.com/selfselect/getstockquotation?" + params.Encode()
	body, err := b.doGet(ctx, urlStr)
	if err != nil {
		return nil, err
	}

	var resp struct {
		ResultCode string          `json:"ResultCode"`
		Result     json.RawMessage `json:"Result"`
	}
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, fmt.Errorf("baidu parse response: %w", err)
	}
	if resp.ResultCode != "0" {
		return nil, fmt.Errorf("baidu api error code: %s", resp.ResultCode)
	}

	// Use decoder with UseNumber to preserve precision for volume/amount
	rdr := json.NewDecoder(bytes.NewReader(resp.Result))
	rdr.UseNumber()
	var baiduResult struct {
		NewMarketData struct {
			Keys    []string `json:"keys"`
			Headers []string `json:"headers"`
			Rows    [][]any  `json:"rows"`
		} `json:"newMarketData"`
	}
	if err := rdr.Decode(&baiduResult); err != nil {
		return nil, fmt.Errorf("baidu parse result: %w", err)
	}

	if len(baiduResult.NewMarketData.Rows) == 0 {
		return nil, fmt.Errorf("empty baidu kline data for %s", code)
	}

	// keys: timestamp, time, open, close, volume, high, low, amount, range, ratio, turnoverratio, preClose, ...
	// Row values are [timestamp, "2026-05-22", open, close, volume, high, low, amount, ...]
	bars := make([]model.Bar, 0, len(baiduResult.NewMarketData.Rows))
	for _, row := range baiduResult.NewMarketData.Rows {
		if len(row) < 12 {
			continue
		}
		dateStr, _ := row[1].(string)
		if dateStr == "" {
			continue
		}
		bar := model.Bar{
			Code:      code,
			Type:      tp,
			TradeDate: dateStr,
		}
		bar.Open = toFloat64(row[2])
		bar.Close = toFloat64(row[3])
		bar.Volume = toInt64(row[4])
		bar.High = toFloat64(row[5])
		bar.Low = toFloat64(row[6])
		bar.Amount = toFloat64(row[7])
		bar.ChangePct = toFloat64(row[9])
		bar.Turnover = toFloat64(row[10])
		bar.PreClose = toFloat64(row[11])

		if options.Start != "" && dateStr < options.Start {
			continue
		}
		if options.End != "" && dateStr > options.End {
			continue
		}
		bars = append(bars, bar)
	}

	if len(bars) > limit {
		bars = bars[len(bars)-limit:]
	}
	return bars, nil
}

// Unimplemented methods — Baidu is daily-kline only.
func (b *Baidu) MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, opts ...Option) ([]model.Bar, error) {
	return nil, fmt.Errorf("Baidu: MinuteKline not implemented")
}
func (b *Baidu) TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error) {
	return nil, fmt.Errorf("Baidu: TodayMinute not implemented")
}
func (b *Baidu) RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error) {
	return nil, fmt.Errorf("Baidu: RealTimeQuote not implemented")
}
func (b *Baidu) StockList(ctx context.Context) ([]model.Stock, error) {
	return nil, fmt.Errorf("Baidu: StockList not implemented")
}
func (b *Baidu) ConceptList(ctx context.Context) ([]model.Concept, error) {
	return nil, fmt.Errorf("Baidu: ConceptList not implemented")
}
func (b *Baidu) ConceptConstituents(ctx context.Context, code string) ([]string, error) {
	return nil, fmt.Errorf("Baidu: ConceptConstituents not implemented")
}
func (b *Baidu) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
	return nil, fmt.Errorf("Baidu: RankVolume not implemented")
}
func (b *Baidu) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
	return nil, fmt.Errorf("Baidu: RankLimitUp not implemented")
}

func toFloat64(v any) float64 {
	switch x := v.(type) {
	case float64:
		return x
	case string:
		f, _ := strconv.ParseFloat(x, 64)
		return f
	case json.Number:
		f, _ := x.Float64()
		return f
	}
	return 0
}

func toInt64(v any) int64 {
	switch x := v.(type) {
	case float64:
		return int64(x)
	case string:
		i, _ := strconv.ParseInt(x, 10, 64)
		return i
	case json.Number:
		i, _ := x.Int64()
		return i
	}
	return 0
}

// Ensure generic JSON numbers are decoded properly.
