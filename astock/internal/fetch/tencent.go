package fetch

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/huijiecai/stock/astock/internal/model"
)

var _ Fetcher = (*Tencent)(nil)

type Tencent struct {
	client *http.Client
}

func NewTencent() *Tencent {
	return &Tencent{
		client: &http.Client{Timeout: 15 * time.Second},
	}
}

func (t *Tencent) RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error) {
	if len(codes) == 0 {
		return nil, nil
	}
	qtCodes := make([]string, len(codes))
	for i, c := range codes {
		if strings.HasPrefix(c, "6") {
			qtCodes[i] = "sh" + c
		} else {
			qtCodes[i] = "sz" + c
		}
	}
	urlStr := "http://qt.gtimg.cn/q=" + strings.Join(qtCodes, ",")
	req, err := http.NewRequestWithContext(ctx, "GET", urlStr, nil)
	if err != nil {
		return nil, err
	}
	resp, err := t.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("tencent quote: %w", err)
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	lines := strings.Split(strings.TrimSpace(string(body)), ";")
	var quotes []model.Quote
	for _, line := range lines {
		if !strings.Contains(line, "=") {
			continue
		}
		parts := strings.Split(line, "~")
		if len(parts) < 10 {
			continue
		}
		price, _ := strconv.ParseFloat(parts[3], 64)
		preClose, _ := strconv.ParseFloat(parts[4], 64)
		change := price - preClose
		changePct := 0.0
		if preClose > 0 {
			changePct = change / preClose * 100
		}
		volume, _ := strconv.ParseInt(parts[6], 10, 64)
		amount, _ := strconv.ParseFloat(parts[37], 64)
		quotes = append(quotes, model.Quote{
			Code:      strings.TrimPrefix(parts[2], "sh"),
			Name:      parts[1],
			Price:     price,
			PreClose:  preClose,
			ChangePct: changePct,
			Volume:    volume,
			Amount:    amount,
		})
	}
	return quotes, nil
}

func (t *Tencent) DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error) {
	return nil, fmt.Errorf("Tencent: DailyKline not implemented")
}
func (t *Tencent) MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, opts ...Option) ([]model.Bar, error) {
	return nil, fmt.Errorf("Tencent: MinuteKline not implemented")
}
func (t *Tencent) TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error) {
	return nil, fmt.Errorf("Tencent: TodayMinute not implemented")
}
func (t *Tencent) StockList(ctx context.Context) ([]model.Stock, error) {
	return nil, fmt.Errorf("Tencent: StockList not implemented, use EastMoney")
}
func (t *Tencent) ConceptList(ctx context.Context) ([]model.Concept, error) {
	return nil, fmt.Errorf("Tencent: ConceptList not implemented, use EastMoney")
}
func (t *Tencent) ConceptConstituents(ctx context.Context, code string) ([]string, error) {
	return nil, fmt.Errorf("Tencent: ConceptConstituents not implemented, use EastMoney")
}
func (t *Tencent) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
	return nil, fmt.Errorf("Tencent: RankVolume not implemented, use EastMoney")
}
func (t *Tencent) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
	return nil, fmt.Errorf("Tencent: RankLimitUp not implemented, use EastMoney")
}
