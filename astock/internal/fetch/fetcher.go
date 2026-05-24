package fetch

import (
	"context"

	"github.com/huijiecai/stock/astock/internal/model"
)

type Option func(*FetchOptions)

type FetchOptions struct {
	Start string
	End   string
	Limit int
	Top   int
}

func WithStart(s string) Option    { return func(o *FetchOptions) { o.Start = s } }
func WithEnd(s string) Option      { return func(o *FetchOptions) { o.End = s } }
func WithLimit(n int) Option       { return func(o *FetchOptions) { o.Limit = n } }
func WithTop(n int) Option         { return func(o *FetchOptions) { o.Top = n } }

type Fetcher interface {
	DailyKline(ctx context.Context, code string, tp model.DataType, opts ...Option) ([]model.Bar, error)
	MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, opts ...Option) ([]model.Bar, error)
	TodayMinute(ctx context.Context, code string, tp model.DataType) ([]model.Tick, error)
	RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error)
	StockList(ctx context.Context) ([]model.Stock, error)
	ConceptList(ctx context.Context) ([]model.Concept, error)
	ConceptConstituents(ctx context.Context, code string) ([]string, error)
	RankVolume(ctx context.Context, top int) ([]model.Quote, error)
	RankLimitUp(ctx context.Context) ([]model.Quote, error)
}
