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

var sinaNodes = []string{"sh_a", "sz_a", "hs_a"}

const sinaPageSize = 100

func (s *Sina) fetchNodeStocks(ctx context.Context, node string, sort string, asc int) ([]sinaStock, error) {
	var all []sinaStock
	page := 1
	for {
		urlStr := fmt.Sprintf("http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=%d&num=%d&sort=%s&asc=%d&node=%s", page, sinaPageSize, sort, asc, node)
		body, err := s.doGet(ctx, urlStr)
		if err != nil {
			return nil, err
		}
		if len(body) == 0 || body[0] != '[' {
			break // no more data
		}
		stocks, err := parseSinaJSON(body)
		if err != nil {
			return nil, fmt.Errorf("parse %s: %w", node, err)
		}
		if len(stocks) == 0 {
			break
		}
		all = append(all, stocks...)
		if len(stocks) < sinaPageSize {
			break
		}
		page++
	}
	return all, nil
}

func (s *Sina) fetchAllStocks(ctx context.Context) ([]sinaStock, error) {
	var all []sinaStock
	for _, node := range sinaNodes {
		stocks, err := s.fetchNodeStocks(ctx, node, "symbol", 1)
		if err != nil {
			return nil, err
		}
		all = append(all, stocks...)
	}
	return all, nil
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
		} else if strings.HasPrefix(code, "8") || strings.HasPrefix(code, "920") {
			exchange = "bj"
		} else if strings.HasPrefix(code, "4") {
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

func (s *Sina) fetchNodeTop(ctx context.Context, node string, top int, sort string) ([]sinaStock, error) {
	urlStr := fmt.Sprintf("http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData?page=1&num=%d&sort=%s&asc=0&node=%s", top, sort, node)
	body, err := s.doGet(ctx, urlStr)
	if err != nil {
		return nil, err
	}
	return parseSinaJSON(body)
}

func (s *Sina) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
	var all []sinaStock
	for _, node := range sinaNodes {
		stocks, err := s.fetchNodeTop(ctx, node, 200, "changepercent")
		if err != nil {
			continue
		}
		all = append(all, stocks...)
	}
	quotes := make([]model.Quote, 0, len(all))
	for _, st := range all {
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
	var all []sinaStock
	for _, node := range sinaNodes {
		stocks, err := s.fetchNodeTop(ctx, node, top, "amount")
		if err != nil {
			continue
		}
		all = append(all, stocks...)
	}
	// Sort by amount descending across all nodes
	quotes := make([]model.Quote, 0, len(all))
	for _, st := range all {
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
	// Simple bubble sort by amount descending
	for i := 0; i < len(quotes); i++ {
		for j := i + 1; j < len(quotes); j++ {
			if quotes[j].Amount > quotes[i].Amount {
				quotes[i], quotes[j] = quotes[j], quotes[i]
			}
		}
	}
	if len(quotes) > top {
		quotes = quotes[:top]
	}
	return quotes, nil
}
