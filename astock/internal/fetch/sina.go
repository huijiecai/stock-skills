package fetch

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/huijiecai/stock/astock/internal/model"
)

type sinaStock struct {
	Code          string      `json:"code"`
	Name          string      `json:"name"`
	Trade         string      `json:"trade"`
	PriceChange   json.Number `json:"pricechange"`
	ChangePercent json.Number `json:"changepercent"`
	Settlement    string      `json:"settlement"`
	Open          string      `json:"open"`
	High          string      `json:"high"`
	Low           string      `json:"low"`
	Volume        int64       `json:"volume"`
	Amount        float64     `json:"amount"`
	Symbol        string      `json:"symbol"`
}

func parseSinaJSON(body []byte) ([]sinaStock, error) {
	dec := json.NewDecoder(strings.NewReader(string(body)))
	dec.UseNumber()
	var stocks []sinaStock
	if err := dec.Decode(&stocks); err != nil {
		return nil, fmt.Errorf("sina parse: %w", err)
	}
	return stocks, nil
}

func sinaFloat64(n json.Number) float64 {
	v, _ := n.Float64()
	return v
}

var _ Fetcher = (*Sina)(nil)

type Sina struct {
	client *http.Client
}

func NewSina() *Sina {
	return &Sina{
		client: &http.Client{Timeout: 30 * time.Second},
	}
}

func (s *Sina) doGet(ctx context.Context, urlStr string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, "GET", urlStr, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36")
	resp, err := s.client.Do(req)
	if err != nil {
		return nil, fmt.Errorf("sina get: %w", err)
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read body: %w", err)
	}
	return body, nil
}

func (s *Sina) fetchAllStocks(ctx context.Context) ([]sinaStock, error) {
	urlStr := "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=5000&sort=symbol&asc=1&node=hs_a"
	body, err := s.doGet(ctx, urlStr)
	if err != nil {
		return nil, err
	}
	return parseSinaJSON(body)
}

func (s *Sina) StockList(ctx context.Context) ([]model.Stock, error) {
	stocks, err := s.fetchAllStocks(ctx)
	if err != nil {
		return nil, err
	}
	result := make([]model.Stock, 0, len(stocks))
	for _, st := range stocks {
		code := st.Code
		exchange := "sz"
		if strings.HasPrefix(code, "6") || strings.HasPrefix(code, "9") {
			exchange = "sh"
		} else if strings.HasPrefix(code, "8") {
			exchange = "bj"
		}
		result = append(result, model.Stock{
			Code:     code,
			Name:     st.Name,
			Exchange: exchange,
		})
	}
	return result, nil
}

func (s *Sina) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
	urlStr := "http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=200&sort=changepercent&asc=0&node=hs_a"
	body, err := s.doGet(ctx, urlStr)
	if err != nil {
		return nil, err
	}
	stocks, err := parseSinaJSON(body)
	if err != nil {
		return nil, err
	}
	quotes := make([]model.Quote, 0, len(stocks))
	for _, st := range stocks {
		chgPct := sinaFloat64(st.ChangePercent)
		if chgPct < 9.5 {
			continue
		}
		price, _ := strconv.ParseFloat(st.Trade, 64)
		preClose, _ := strconv.ParseFloat(st.Settlement, 64)
		highLimit := preClose * 1.1
		highLimit = float64(int(highLimit*100+0.5)) / 100
		quotes = append(quotes, model.Quote{
			Code:      st.Code,
			Name:      st.Name,
			Price:     price,
			PreClose:  preClose,
			ChangePct: chgPct,
			Volume:    st.Volume,
			Amount:    st.Amount,
			HighLimit: highLimit,
		})
	}
	return quotes, nil
}

// Unimplemented methods
func (s *Sina) DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error) {
	return nil, fmt.Errorf("Sina: DailyKline not implemented, use Baidu")
}
func (s *Sina) MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, opts ...Option) ([]model.Bar, error) {
	return nil, fmt.Errorf("Sina: MinuteKline not implemented, use TDX")
}
func (s *Sina) TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error) {
	return nil, fmt.Errorf("Sina: TodayMinute not implemented, use EastMoney")
}
func (s *Sina) RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error) {
	return nil, fmt.Errorf("Sina: RealTimeQuote not implemented, use EastMoney")
}
func (s *Sina) ConceptList(ctx context.Context) ([]model.Concept, error) {
	return nil, fmt.Errorf("Sina: ConceptList not implemented, use EastMoney")
}
func (s *Sina) ConceptConstituents(ctx context.Context, code string) ([]string, error) {
	return nil, fmt.Errorf("Sina: ConceptConstituents not implemented, use EastMoney")
}
func (s *Sina) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
	if top <= 0 {
		top = 30
	}
	if top > 200 {
		top = 200
	}
	urlStr := fmt.Sprintf("http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=%d&sort=amount&asc=0&node=hs_a", top)
	body, err := s.doGet(ctx, urlStr)
	if err != nil {
		return nil, err
	}
	stocks, err := parseSinaJSON(body)
	if err != nil {
		return nil, err
	}
	quotes := make([]model.Quote, 0, len(stocks))
	for _, st := range stocks {
		price, _ := strconv.ParseFloat(st.Trade, 64)
		preClose, _ := strconv.ParseFloat(st.Settlement, 64)
		quotes = append(quotes, model.Quote{
			Code:      st.Code,
			Name:      st.Name,
			Price:     price,
			PreClose:  preClose,
			ChangePct: sinaFloat64(st.ChangePercent),
			Volume:    st.Volume,
			Amount:    st.Amount,
		})
	}
	return quotes, nil
}
