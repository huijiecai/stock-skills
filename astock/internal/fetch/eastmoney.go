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

type EastMoney struct {
	client  *http.Client
	baseURL string
}

func NewEastMoney() *EastMoney {
	return &EastMoney{
		client:  &http.Client{Timeout: 30 * time.Second},
		baseURL: "https://push2.eastmoney.com/api/qt/stock",
	}
}

func (e *EastMoney) doGet(ctx context.Context, urlStr string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", urlStr, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "Mozilla/5.0")
	req.Header.Set("Referer", "https://quote.eastmoney.com/")
	resp, err := e.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("eastmoney get: %w", err)
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}
	return body, nil
}

func (e *EastMoney) toSecID(code string, tp model.DataType) string {
	switch tp {
	case model.TypeIndex:
		if strings.HasPrefix(code, "000") || strings.HasPrefix(code, "880") {
			return "1." + code
		}
		return "0." + code
	default:
		return "0." + code
	}
}

func (e *EastMoney) DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error) {
	secID := e.toSecID(code, tp)
	options := &FetchOptions{}
	for _, o := range opts {
		o(options)
	}
	params := url.Values{}
	params.Set("secid", secID)
	params.Set("fields1", "f1,f2,f3,f4,f5,f6")
	params.Set("fields2", "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61")
	params.Set("klt", "101")
	params.Set("fqt", "1")
	if options.Limit > 0 {
		params.Set("lmt", strconv.Itoa(options.Limit))
	} else {
		params.Set("lmt", "30")
	}
	if options.Start != "" {
		params.Set("beg", options.Start)
	}
	if options.End != "" {
		params.Set("end", options.End)
	}
	urlStr := "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + params.Encode()
	body, err := e.doGet(ctx, urlStr)
	if err != nil {
		return nil, err
	}
	var result struct {
		Data struct {
			Klined string `json:"klined"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("parse kline: %w", err)
	}
	if result.Data.Klined == "" {
		return nil, fmt.Errorf("empty kline data for %s", code)
	}
	lines := strings.Split(strings.TrimSpace(result.Data.Klined), ";")
	bars := make([]model.Bar, 0, len(lines))
	for _, line := range lines {
		parts := strings.Split(line, ",")
		if len(parts) < 11 {
			continue
		}
		bar := model.Bar{
			Code:      code,
			Type:      tp,
			TradeDate: parts[0],
		}
		bar.Open, _ = strconv.ParseFloat(parts[1], 64)
		bar.Close, _ = strconv.ParseFloat(parts[2], 64)
		bar.High, _ = strconv.ParseFloat(parts[3], 64)
		bar.Low, _ = strconv.ParseFloat(parts[4], 64)
		bar.PreClose, _ = strconv.ParseFloat(parts[5], 64)
		bar.ChangePct, _ = strconv.ParseFloat(parts[6], 64)
		bar.Volume, _ = strconv.ParseInt(parts[7], 10, 64)
		bar.Amount, _ = strconv.ParseFloat(parts[8], 64)
		bar.Turnover, _ = strconv.ParseFloat(parts[9], 64)
		bars = append(bars, bar)
	}
	return bars, nil
}

func (e *EastMoney) StockList(ctx context.Context) ([]model.Stock, error) {
	urlStr := "https://push2.eastmoney.com/api/qt/clist/get?" + url.Values{
		"pn": {"1"}, "pz": {"10000"}, "po": {"0"}, "np": {"1"},
		"ut": {"bd1d9ddb04089700cf9c27f6f7426281"},
		"fltt": {"2"}, "invt": {"2"}, "fid": {"f3"},
		"fs": {"m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"},
		"fields": {"f12,f14"},
	}.Encode()
	body, err := e.doGet(ctx, urlStr)
	if err != nil {
		return nil, err
	}
	var result struct {
		Data struct {
			Total int `json:"total"`
			Diff  []struct {
				F12 string `json:"f12"`
				F14 string `json:"f14"`
			} `json:"diff"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("parse stock list: %w", err)
	}
	stocks := make([]model.Stock, 0, result.Data.Total)
	for _, d := range result.Data.Diff {
		exchange := "sz"
		if strings.HasPrefix(d.F12, "6") || strings.HasPrefix(d.F12, "9") {
			exchange = "sh"
		} else if strings.HasPrefix(d.F12, "8") {
			exchange = "bj"
		}
		stocks = append(stocks, model.Stock{Code: d.F12, Name: d.F14, Exchange: exchange})
	}
	return stocks, nil
}

func (e *EastMoney) ConceptList(ctx context.Context) ([]model.Concept, error) {
	urlStr := "https://push2.eastmoney.com/api/qt/clist/get?" + url.Values{
		"pn": {"1"}, "pz": {"500"}, "po": {"0"}, "np": {"1"},
		"ut": {"bd1d9ddb04089700cf9c27f6f7426281"},
		"fltt": {"2"}, "invt": {"2"}, "fid": {"f3"},
		"fs": {"m:0+t:10"},
		"fields": {"f12,f14,f20"},
	}.Encode()
	body, err := e.doGet(ctx, urlStr)
	if err != nil {
		return nil, err
	}
	var result struct {
		Data struct {
			Total int `json:"total"`
			Diff  []struct {
				F12 string `json:"f12"`
				F14 string `json:"f14"`
				F20 int    `json:"f20"`
			} `json:"diff"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("parse concept list: %w", err)
	}
	concepts := make([]model.Concept, 0, result.Data.Total)
	for _, d := range result.Data.Diff {
		concepts = append(concepts, model.Concept{Code: d.F12, Name: d.F14, StockCount: d.F20})
	}
	return concepts, nil
}

func (e *EastMoney) ConceptConstituents(ctx context.Context, code string) ([]string, error) {
	urlStr := "https://push2.eastmoney.com/api/qt/clist/get?" + url.Values{
		"pn": {"1"}, "pz": {"1000"}, "po": {"0"}, "np": {"1"},
		"ut": {"bd1d9ddb04089700cf9c27f6f7426281"},
		"fltt": {"2"}, "invt": {"2"}, "fid": {"f3"},
		"fs": {"b:" + code},
		"fields": {"f12"},
	}.Encode()
	body, err := e.doGet(ctx, urlStr)
	if err != nil {
		return nil, err
	}
	var result struct {
		Data struct {
			Diff []struct {
				F12 string `json:"f12"`
			} `json:"diff"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("parse constituents: %w", err)
	}
	codes := make([]string, 0, len(result.Data.Diff))
	for _, d := range result.Data.Diff {
		codes = append(codes, d.F12)
	}
	return codes, nil
}

func (e *EastMoney) TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error) {
	secID := e.toSecID(code, tp)
	params := url.Values{}
	params.Set("secid", secID)
	params.Set("fields1", "f1,f2,f3,f4,f5,f6,f7")
	params.Set("fields2", "f51,f52,f53,f54,f55")
	params.Set("lmt", "500")
	params.Set("is_cr", "0")
	urlStr := e.baseURL + "/kline/get?" + params.Encode()
	body, err := e.doGet(ctx, urlStr)
	if err != nil {
		return nil, err
	}
	var result struct {
		Data *struct {
			Klined string `json:"klined"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("parse today minute: %w", err)
	}
	if result.Data == nil || result.Data.Klined == "" {
		return nil, fmt.Errorf("empty today minute data for %s", code)
	}
	lines := strings.Split(strings.TrimSpace(result.Data.Klined), ";")
	ticks := make([]model.Tick, 0, len(lines))
	for _, line := range lines {
		parts := strings.Split(line, ",")
		if len(parts) < 5 {
			continue
		}
		tick := model.Tick{
			Code: code, Time: parts[0],
			Price:    mustFloat(parts[1]),
			AvgPrice: mustFloat(parts[3]),
			Volume:   mustInt(parts[4]),
			Amount:   mustFloat(parts[5]),
		}
		ticks = append(ticks, tick)
	}
	return ticks, nil
}

func (e *EastMoney) RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error) {
	if len(codes) == 0 {
		return nil, nil
	}
	secIDs := make([]string, len(codes))
	for i, c := range codes {
		secIDs[i] = "0." + c
	}
	params := url.Values{}
	params.Set("secid", strings.Join(secIDs, ","))
	params.Set("fields", "f2,f3,f4,f5,f6,f12,f14,f15,f16,f17,f18,f20,f21")
	urlStr := e.baseURL + "/get?" + params.Encode()
	body, err := e.doGet(ctx, urlStr)
	if err != nil {
		return nil, err
	}
	var result struct {
		Data struct {
			Total int `json:"total"`
			Diff  []struct {
				F12 string  `json:"f12"`
				F14 string  `json:"f14"`
				F2  float64 `json:"f2"`
				F3  float64 `json:"f3"`
				F4  float64 `json:"f4"`
				F5  float64 `json:"f5"`
				F6  float64 `json:"f6"`
				F15 float64 `json:"f15"`
				F16 float64 `json:"f16"`
				F17 float64 `json:"f17"`
				F18 float64 `json:"f18"`
				F20 float64 `json:"f20"`
				F21 float64 `json:"f21"`
			} `json:"diff"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("parse quote: %w", err)
	}
	quotes := make([]model.Quote, 0, len(result.Data.Diff))
	for _, d := range result.Data.Diff {
		quotes = append(quotes, model.Quote{
			Code: d.F12, Name: d.F14, Open: d.F15, High: d.F16, Low: d.F17,
			Price: d.F2, PreClose: d.F18, ChangePct: d.F3,
			Volume: int64(d.F4), Amount: d.F5, HighLimit: d.F20, LowLimit: d.F21,
		})
	}
	return quotes, nil
}

func (e *EastMoney) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
	limit := top
	if limit <= 0 {
		limit = 30
	}
	params := url.Values{}
	params.Set("pn", "1")
	params.Set("pz", strconv.Itoa(limit))
	params.Set("po", "1")
	params.Set("np", "1")
	params.Set("ut", "bd1d9ddb04089700cf9c27f6f7426281")
	params.Set("fltt", "2")
	params.Set("invt", "2")
	params.Set("fid", "f6")
	params.Set("fs", "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23")
	params.Set("fields", "f2,f3,f4,f5,f6,f12,f14,f15,f16,f17,f18,f20,f21")
	urlStr := "https://push2.eastmoney.com/api/qt/clist/get?" + params.Encode()
	body, err := e.doGet(ctx, urlStr)
	if err != nil {
		return nil, err
	}
	var result struct {
		Data struct {
			Diff []struct {
				F12 string  `json:"f12"`
				F14 string  `json:"f14"`
				F2  float64 `json:"f2"`
				F3  float64 `json:"f3"`
				F6  float64 `json:"f6"`
				F15 float64 `json:"f15"`
				F16 float64 `json:"f16"`
				F17 float64 `json:"f17"`
				F18 float64 `json:"f18"`
			} `json:"diff"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("parse rank volume: %w", err)
	}
	quotes := make([]model.Quote, 0, len(result.Data.Diff))
	for _, d := range result.Data.Diff {
		quotes = append(quotes, model.Quote{
			Code: d.F12, Name: d.F14, Price: d.F2, ChangePct: d.F3,
			Amount: d.F6, Open: d.F15, High: d.F16, Low: d.F17, PreClose: d.F18,
		})
	}
	return quotes, nil
}

func (e *EastMoney) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
	params := url.Values{}
	params.Set("pn", "1")
	params.Set("pz", "200")
	params.Set("po", "0")
	params.Set("np", "1")
	params.Set("ut", "bd1d9ddb04089700cf9c27f6f7426281")
	params.Set("fltt", "2")
	params.Set("invt", "2")
	params.Set("fid", "f3")
	params.Set("fs", "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23")
	params.Set("fields", "f2,f3,f4,f12,f14,f15,f16,f17,f18,f20")
	urlStr := "https://push2.eastmoney.com/api/qt/clist/get?" + params.Encode()
	body, err := e.doGet(ctx, urlStr)
	if err != nil {
		return nil, err
	}
	var result struct {
		Data struct {
			Diff []struct {
				F12 string  `json:"f12"`
				F14 string  `json:"f14"`
				F2  float64 `json:"f2"`
				F3  float64 `json:"f3"`
				F4  float64 `json:"f4"`
				F15 float64 `json:"f15"`
				F16 float64 `json:"f16"`
				F17 float64 `json:"f17"`
				F18 float64 `json:"f18"`
				F20 float64 `json:"f20"`
			} `json:"diff"`
		} `json:"data"`
	}
	if err := json.Unmarshal(body, &result); err != nil {
		return nil, fmt.Errorf("parse limit up: %w", err)
	}
	quotes := make([]model.Quote, 0, len(result.Data.Diff))
	for _, d := range result.Data.Diff {
		if d.F3 < 9.5 {
			continue
		}
		quotes = append(quotes, model.Quote{
			Code: d.F12, Name: d.F14, Price: d.F2, ChangePct: d.F3,
			Volume: int64(d.F4), Open: d.F15, High: d.F16, Low: d.F17,
			PreClose: d.F18, HighLimit: d.F20,
		})
	}
	return quotes, nil
}

// compile-time interface check
var _ Fetcher = (*EastMoney)(nil)

// MinuteKline is not supported by EastMoney
func (e *EastMoney) MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, opts ...Option) ([]model.Bar, error) {
    return nil, fmt.Errorf("EastMoney: MinuteKline not implemented, use TDX")
}

// helpers
func mustFloat(s string) float64 {
	v, _ := strconv.ParseFloat(s, 64)
	return v
}
func mustInt(s string) int64 {
	v, _ := strconv.ParseInt(s, 10, 64)
	return v
}
