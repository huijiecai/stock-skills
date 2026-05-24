package fetch

import (
	"context"
	"fmt"

	"github.com/huijiecai/stock/astock/internal/model"
)

var _ Fetcher = (*THS)(nil)

type THS struct{}

func NewTHS() *THS {
	return &THS{}
}

func (t *THS) DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error) {
	return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
func (t *THS) MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, opts ...Option) ([]model.Bar, error) {
	return nil, fmt.Errorf("THS: not implemented, use TDX")
}
func (t *THS) TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error) {
	return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
func (t *THS) RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error) {
	return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
func (t *THS) StockList(ctx context.Context) ([]model.Stock, error) {
	return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
func (t *THS) ConceptList(ctx context.Context) ([]model.Concept, error) {
	return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
func (t *THS) ConceptConstituents(ctx context.Context, code string) ([]string, error) {
	return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
func (t *THS) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
	return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
func (t *THS) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
	return nil, fmt.Errorf("THS: not implemented, use EastMoney")
}
