package fetch

import (
	"context"
	"fmt"
	"log"

	"github.com/huijiecai/stock/astock/internal/model"
)

type Selector struct {
	eastMoney *EastMoney
	tdx       *TDX
	tencent   *Tencent
	ths       *THS
}

func NewSelector(em *EastMoney, tdx *TDX, ten *Tencent, ths *THS) *Selector {
	return &Selector{
		eastMoney: em,
		tdx:       tdx,
		tencent:   ten,
		ths:       ths,
	}
}

func (s *Selector) DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error) {
	switch tp {
	case model.TypeConcept:
		return tryFetch(ctx, []Fetcher{s.tdx, s.ths},
			func(f Fetcher) (any, error) { return f.DailyKline(ctx, code, tp, opts...) })
	case model.TypeIndex:
		return tryFetch(ctx, []Fetcher{s.tdx, s.eastMoney},
			func(f Fetcher) (any, error) { return f.DailyKline(ctx, code, tp, opts...) })
	default:
		return tryFetch(ctx, []Fetcher{s.eastMoney, s.tdx},
			func(f Fetcher) (any, error) { return f.DailyKline(ctx, code, tp, opts...) })
	}
}

func (s *Selector) MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, opts ...Option) ([]model.Bar, error) {
	return s.tdx.MinuteKline(ctx, code, tp, freq, opts...)
}

func (s *Selector) TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error) {
	result, err := tryFetch(ctx, []Fetcher{s.eastMoney, s.tdx},
		func(f Fetcher) (any, error) { return f.TodayMinute(ctx, code, tp) })
	if err != nil {
		return nil, err
	}
	return result.([]model.Tick), nil
}

func (s *Selector) RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error) {
	result, err := tryFetch(ctx, []Fetcher{s.eastMoney, s.tencent},
		func(f Fetcher) (any, error) { return f.RealTimeQuote(ctx, codes...) })
	if err != nil {
		return nil, err
	}
	return result.([]model.Quote), nil
}

func (s *Selector) StockList(ctx context.Context) ([]model.Stock, error) {
	return s.eastMoney.StockList(ctx)
}

func (s *Selector) ConceptList(ctx context.Context) ([]model.Concept, error) {
	return s.eastMoney.ConceptList(ctx)
}

func (s *Selector) ConceptConstituents(ctx context.Context, code string) ([]string, error) {
	return s.eastMoney.ConceptConstituents(ctx, code)
}

func (s *Selector) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
	return s.eastMoney.RankVolume(ctx, top)
}

func (s *Selector) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
	result, err := tryFetch(ctx, []Fetcher{s.eastMoney, s.tdx},
		func(f Fetcher) (any, error) { return f.RankLimitUp(ctx) })
	if err != nil {
		return nil, err
	}
	return result.([]model.Quote), nil
}

func tryFetch(ctx context.Context, sources []Fetcher, fn func(Fetcher) (any, error)) (any, error) {
	var lastErr error
	for _, src := range sources {
		if src == nil {
			continue
		}
		result, err := fn(src)
		if err == nil {
			return result, nil
		}
		lastErr = err
		log.Printf("[warn] source failed: %v, trying next", err)
	}
	return nil, fmt.Errorf("all sources failed: %w", lastErr)
}

var _ Fetcher = (*Selector)(nil)
