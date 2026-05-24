package fetch

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
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
	req.Header.Set("Accept", "application/vnd.finance-web.v1+json")
	req.Header.Set("Origin", "https://gushitong.baidu.com")
	req.Header.Set("Referer", "https://gushitong.baidu.com/")
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
// Returns ~60 trading days by default, in chronological order.
func (b *Baidu) DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error) {
	options := &FetchOptions{}
	for _, o := range opts {
		o(options)
	}
	limit := options.Limit
	if limit <= 0 {
		limit = 60
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
	params.Set("ktype", "1")
	if options.Start != "" {
		params.Set("start_time", options.Start)
	}

	u := "https://finance.pae.baidu.com/selfselect/getstockquotation?" + params.Encode()
	body, err := b.doGet(ctx, u)
	if err != nil {
		return nil, err
	}

	var resp struct {
		ResultCode string          `json:"ResultCode"`
		Result     json.RawMessage `json:"Result"`
	}
	if err := json.Unmarshal(body, &resp); err != nil {
		return nil, fmt.Errorf("baidu parse: %w", err)
	}
	if resp.ResultCode != "0" {
		return nil, fmt.Errorf("baidu error code: %s", resp.ResultCode)
	}

	var inner struct {
		NewMarketData struct {
			MarketData string `json:"marketData"`
		} `json:"newMarketData"`
	}
	if err := json.Unmarshal(resp.Result, &inner); err != nil {
		return nil, fmt.Errorf("baidu parse inner: %w", err)
	}

	md := strings.TrimSpace(inner.NewMarketData.MarketData)
	if md == "" {
		return nil, fmt.Errorf("empty baidu kline data for %s", code)
	}

	// marketData is semicolon-delimited, each row is comma-separated:
	// timestamp,date,open,close,volume,high,low,amount,range,ratio,turnoverratio,preClose,...
	fields := strings.Split(md, ";")
	// marketData has "--" for MA fields, but the core fields are at fixed positions:
	// 0:timestamp, 1:date, 2:open, 3:close, 4:volume, 5:high, 6:low, 7:amount, 8:range,
	// 9:ratio(change%), 10:turnoverratio, 11:preClose

	bars := make([]model.Bar, 0, len(fields))
	for _, row := range fields {
		cols := strings.Split(row, ",")
		if len(cols) < 12 {
			continue
		}
		dateStr := cols[1]
		if dateStr == "" || dateStr == "--" {
			continue
		}

		if options.Start != "" && dateStr < options.Start {
			continue
		}
		if options.End != "" && dateStr > options.End {
			continue
		}

		bar := model.Bar{
			Code:      code,
			Type:      tp,
			TradeDate: dateStr,
			Open:      parseFloat(cols[2]),
			Close:     parseFloat(cols[3]),
			Volume:    parseInt(cols[4]),
			High:      parseFloat(cols[5]),
			Low:       parseFloat(cols[6]),
			Amount:    parseFloat(cols[7]),
			ChangePct: parseFloat(cols[9]),
			Turnover:  parseFloat(cols[10]),
			PreClose:  parseFloat(cols[11]),
		}
		bars = append(bars, bar)
	}

	if len(bars) > limit {
		bars = bars[len(bars)-limit:]
	}
	return bars, nil
}

func parseFloat(s string) float64 {
	if s == "" || s == "--" {
		return 0
	}
	v, _ := strconv.ParseFloat(s, 64)
	return v
}

func parseInt(s string) int64 {
	if s == "" || s == "--" {
		return 0
	}
	v, _ := strconv.ParseInt(s, 10, 64)
	return v
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
