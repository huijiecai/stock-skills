package fetch

import (
	"context"
	"fmt"
	"log"

	"github.com/huijiecai/stock/astock/internal/model"
)

type Selector struct {
	eastMoney *EastMoney
	baidu     *Baidu
	sina      *Sina
	tdx       *TDX
	tdxErr    error
	tencent   *Tencent
	ths       *THS
}

func NewSelector(em *EastMoney, bd *Baidu, tdx *TDX, ten *Tencent, ths *THS, sina *Sina) *Selector {
	s := &Selector{
		eastMoney: em,
		baidu:     bd,
		sina:      sina,
		tencent:   ten,
		ths:       ths,
	}
	if tdx != nil {
		s.tdx = tdx
	}
	return s
}

func (s *Selector) DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error) {
	var fns []Fetcher
	switch tp {
	case model.TypeConcept:
		fns = s.fetchers(s.tdx, s.ths)
	case model.TypeIndex:
		fns = s.fetchers(s.tdx, s.baidu, s.eastMoney)
	default:
		fns = s.fetchers(s.eastMoney, s.baidu, s.tdx)
	}
	result, err := tryFetch(ctx, fns,
		func(f Fetcher) (any, error) { return f.DailyKline(ctx, code, tp, opts...) })
	if err != nil {
		return nil, err
	}
	return result.([]model.Bar), nil
}

func (s *Selector) MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, opts ...Option) ([]model.Bar, error) {
	if err := s.ensureTDX(); err != nil {
		return nil, err
	}
	return s.tdx.MinuteKline(ctx, code, tp, freq, opts...)
}

// ensureTDX lazily initializes the TDX connection on first use.
// Subsequent calls reuse the result (success or failure).
func (s *Selector) ensureTDX() error {
	if s.tdx != nil {
		return nil
	}
	if s.tdxErr != nil {
		return s.tdxErr
	}
	tdx, err := NewTDX()
	if err != nil {
		s.tdxErr = fmt.Errorf("TDX unavailable: %w", err)
		return s.tdxErr
	}
	s.tdx = tdx
	return nil
}

func (s *Selector) TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error) {
	result, err := tryFetch(ctx, s.fetchers(s.eastMoney, s.tdx),
		func(f Fetcher) (any, error) { return f.TodayMinute(ctx, code, tp) })
	if err != nil {
		return nil, err
	}
	return result.([]model.Tick), nil
}

func (s *Selector) RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error) {
	result, err := tryFetch(ctx, s.fetchers(s.eastMoney, s.tencent),
		func(f Fetcher) (any, error) { return f.RealTimeQuote(ctx, codes...) })
	if err != nil {
		return nil, err
	}
	return result.([]model.Quote), nil
}

func (s *Selector) StockList(ctx context.Context) ([]model.Stock, error) {
	result, err := tryFetch(ctx, s.fetchers(s.eastMoney, s.sina),
		func(f Fetcher) (any, error) { return f.StockList(ctx) })
	if err != nil {
		return nil, err
	}
	return result.([]model.Stock), nil
}

func (s *Selector) ConceptList(ctx context.Context) ([]model.Concept, error) {
	result, err := tryFetch(ctx, s.fetchers(s.eastMoney),
		func(f Fetcher) (any, error) { return f.ConceptList(ctx) })
	if err == nil {
		return result.([]model.Concept), nil
	}
	// Fallback: use internal sector classification as concepts
	log.Printf("[warn] concept list API failed: %v, using internal sectors", err)
	return sectorConcepts(), nil
}

// sectorConcepts generates concept-like entries from the curated sector stock map.
func sectorConcepts() []model.Concept {
	concepts := make([]model.Concept, 0, len(TargetSectors))
	for _, sec := range TargetSectors {
		codes := SectorStockMap[sec]
		concepts = append(concepts, model.Concept{
			Code:       sec,
			Name:       sec,
			StockCount: len(codes),
		})
	}
	return concepts
}

func (s *Selector) ConceptConstituents(ctx context.Context, code string) ([]string, error) {
	return s.eastMoney.ConceptConstituents(ctx, code)
}

func (s *Selector) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
	result, err := tryFetch(ctx, s.fetchers(s.eastMoney, s.sina),
		func(f Fetcher) (any, error) { return f.RankVolume(ctx, top) })
	if err != nil {
		return nil, err
	}
	return result.([]model.Quote), nil
}

func (s *Selector) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
	result, err := tryFetch(ctx, s.fetchers(s.eastMoney, s.tdx, s.sina),
		func(f Fetcher) (any, error) { return f.RankLimitUp(ctx) })
	if err != nil {
		return nil, err
	}
	return result.([]model.Quote), nil
}

// fetchers builds a non-nil fetcher list from concrete pointers,
// avoiding Go's nil interface pitfall (nil *T → non-nil interface).
func (s *Selector) fetchers(list ...any) []Fetcher {
	out := make([]Fetcher, 0, len(list))
	for _, f := range list {
		switch v := f.(type) {
		case *TDX:
			if v != nil {
				out = append(out, v)
			}
		case *EastMoney:
			if v != nil {
				out = append(out, v)
			}
		case *Baidu:
			if v != nil {
				out = append(out, v)
			}
		case *Tencent:
			if v != nil {
				out = append(out, v)
			}
		case *THS:
			if v != nil {
				out = append(out, v)
			}
		case *Sina:
			if v != nil {
				out = append(out, v)
			}
		}
	}
	return out
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
