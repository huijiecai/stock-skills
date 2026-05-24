package query

import (
    "context"
    "log"
    "time"

    "github.com/huijiecai/stock/astock/internal/db"
    "github.com/huijiecai/stock/astock/internal/fetch"
    "github.com/huijiecai/stock/astock/internal/model"
)

type Router struct {
    selector *fetch.Selector
}

func NewRouter(s *fetch.Selector) *Router {
    return &Router{selector: s}
}

func isTradingHours() bool {
    now := time.Now()
    weekday := now.Weekday()
    if weekday == time.Saturday || weekday == time.Sunday {
        return false
    }
    hour, min := now.Hour(), now.Minute()
    total := hour*60 + min
    return total >= 570 && total < 900
}

func todayStr() string {
    return time.Now().Format("2006-01-02")
}

func (r *Router) DailyKline(ctx context.Context, code string, tp model.DataType, force bool, opts ...fetch.Option) ([]model.Bar, error) {
    options := &fetch.FetchOptions{}
    for _, o := range opts {
        o(options)
    }
    if !force && !isTradingHours() {
        start, end := options.Start, options.End
        if start == "" && end == "" {
            end = todayStr()
        }
        bars, err := db.QueryDailyK(ctx, code, tp, start, end, options.Limit)
        if err == nil && len(bars) > 0 {
            return bars, nil
        }
    }
    bars, err := r.selector.DailyKline(ctx, code, tp, opts...)
    if err != nil {
        return nil, err
    }
    if force || !isTradingHours() {
        if err := db.UpsertDailyK(context.Background(), bars); err != nil {
            log.Printf("[cache] write daily_k %s: %v", code, err)
        }
    }
    return bars, nil
}

func (r *Router) MinuteKline(ctx context.Context, code string, tp model.DataType, freq model.Freq, date string, force bool, opts ...fetch.Option) ([]model.Bar, error) {
    options := &fetch.FetchOptions{}
    for _, o := range opts {
        o(options)
    }
    queryDate := date
    if queryDate == "" {
        queryDate = todayStr()
    }
    if !force && !isTradingHours() {
        bars, err := db.QueryMinuteK(ctx, code, tp, freq, queryDate)
        if err == nil && len(bars) > 0 {
            return bars, nil
        }
    }
    bars, err := r.selector.MinuteKline(ctx, code, tp, freq, opts...)
    if err != nil {
        return nil, err
    }
    if !isTradingHours() {
        if err := db.UpsertMinuteK(context.Background(), bars); err != nil {
            log.Printf("[cache] write minute_k %s: %v", code, err)
        }
    }
    return bars, nil
}

func (r *Router) StockList(ctx context.Context) ([]model.Stock, error) {
    stocks, err := db.QueryStocks(ctx, "")
    if err == nil && len(stocks) > 0 {
        return stocks, nil
    }
    stocks, err = r.selector.StockList(ctx)
    if err != nil {
        return nil, err
    }
    go func() {
        if err := db.UpsertStockInfo(context.Background(), stocks); err != nil {
            log.Printf("[cache] write stock_info: %v", err)
        }
    }()
    return stocks, nil
}

func (r *Router) ConceptList(ctx context.Context) ([]model.Concept, error) {
    concepts, err := db.QueryConcepts(ctx)
    if err == nil && len(concepts) > 0 {
        return concepts, nil
    }
    concepts, err = r.selector.ConceptList(ctx)
    if err != nil {
        return nil, err
    }
    go func() {
        if err := db.UpsertConceptInfo(context.Background(), concepts); err != nil {
            log.Printf("[cache] write concept_info: %v", err)
        }
    }()
    return concepts, nil
}

func (r *Router) RealTimeQuote(ctx context.Context, codes ...string) ([]model.Quote, error) {
    return r.selector.RealTimeQuote(ctx, codes...)
}

func (r *Router) RankVolume(ctx context.Context, top int) ([]model.Quote, error) {
    return r.selector.RankVolume(ctx, top)
}

func (r *Router) RankLimitUp(ctx context.Context) ([]model.Quote, error) {
    return r.selector.RankLimitUp(ctx)
}
