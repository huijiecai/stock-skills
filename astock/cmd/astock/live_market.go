package main

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/dwh"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

type liveMarketMeta struct {
	Name     string
	ListDate time.Time
}

type LiveMarketRow struct {
	Market        string  `json:"market"`
	Code          string  `json:"code"`
	Name          string  `json:"name,omitempty"`
	Price         float64 `json:"price"`
	PreClose      float64 `json:"pre_close"`
	Open          float64 `json:"open"`
	High          float64 `json:"high"`
	Low           float64 `json:"low"`
	ChangePct     float64 `json:"change_pct"`
	AmplitudePct  float64 `json:"amplitude_pct"`
	RiseSpeed     float64 `json:"rise_speed"`
	Volume        int64   `json:"volume"`
	CurrentVolume int64   `json:"current_volume"`
	Amount        float64 `json:"amount"`
	InVolume      int64   `json:"in_volume"`
	OutVolume     int64   `json:"out_volume"`
	Active        uint16  `json:"active"`
	State         string  `json:"state"`
	LimitPrice    float64 `json:"limit_price,omitempty"`
}

type LiveMarketResult struct {
	AsOf        string          `json:"as_of"`
	Market      string          `json:"market"`
	Sort        string          `json:"sort"`
	Order       string          `json:"order"`
	State       string          `json:"state"`
	Offset      int             `json:"offset"`
	Limit       int             `json:"limit"`
	Matched     *int            `json:"matched,omitempty"`
	Returned    int             `json:"returned"`
	TDXRequests int             `json:"tdx_requests"`
	ElapsedMS   int64           `json:"elapsed_ms"`
	Rows        []LiveMarketRow `json:"rows"`
	Unresolved  []LiveMarketRow `json:"unresolved,omitempty"`
}

func buildLiveMarketCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "market",
		Short: "全市场个股实时排序与涨跌停过滤",
		Long: `通过 TDX 服务端排行接口查询全市场个股，不在本地逐只拉取报价。

默认按涨跌幅降序返回 50 只；可按成交额、涨速、价格、成交量等排序。
--state limit-up/limit-down/limits 会完整扫描排行头部并精确校验涨跌停价。`,
		Args: cobra.NoArgs,
		RunE: runLiveMarket,
	}
	cmd.Flags().String("market", "all", "市场范围: all/sh/sz/bj")
	cmd.Flags().String("sort", "change", "排序字段: code/price/volume/amount/change/amplitude/speed/activity")
	cmd.Flags().String("order", "desc", "排序方向: desc/asc")
	cmd.Flags().Int("offset", 0, "跳过前 N 条")
	cmd.Flags().Int("limit", 50, "返回条数（1-500）")
	cmd.Flags().String("state", "all", "状态过滤: all/limit-up/limit-down/limits")
	return cmd
}

func runLiveMarket(cmd *cobra.Command, _ []string) error {
	market, _ := cmd.Flags().GetString("market")
	sortBy, _ := cmd.Flags().GetString("sort")
	order, _ := cmd.Flags().GetString("order")
	offset, _ := cmd.Flags().GetInt("offset")
	limit, _ := cmd.Flags().GetInt("limit")
	state, _ := cmd.Flags().GetString("state")
	market = strings.ToLower(market)
	sortBy = strings.ToLower(sortBy)
	order = strings.ToLower(order)
	state = strings.ToLower(state)

	if err := validateLiveMarketOptions(market, sortBy, order, state, offset, limit); err != nil {
		return err
	}
	started := time.Now()
	tc := tdx.New()
	defer tc.Close()
	if err := requireRealtime(tc); err != nil {
		return err
	}
	tdxRequests := 1 // requireRealtime uses one index-minute request.

	metas, tradeDates, err := loadLiveMarketMetadata()
	if err != nil {
		return err
	}

	var rows []LiveMarketRow
	var unresolved []LiveMarketRow
	var matched *int
	if state == "all" {
		items, requests, err := fetchLiveMarketPage(tc, market, sortBy, order, offset, limit)
		if err != nil {
			return err
		}
		tdxRequests += requests
		rows = enrichLiveMarketRows(items, metas, tradeDates, time.Now())
	} else {
		items, requests, err := fetchLiveLimitRows(tc, market, state)
		if err != nil {
			return err
		}
		tdxRequests += requests
		allRows := enrichLiveMarketRows(items, metas, tradeDates, time.Now())
		filtered := allRows[:0]
		for _, row := range allRows {
			if row.State == "unknown" {
				unresolved = append(unresolved, row)
				continue
			}
			if state == "limits" || row.State == strings.ReplaceAll(state, "-", "_") {
				if row.State == "limit_up" || row.State == "limit_down" {
					filtered = append(filtered, row)
				}
			}
		}
		sortLiveMarketRows(filtered, sortBy, order)
		matchedCount := len(filtered)
		matched = &matchedCount
		rows = pageLiveMarketRows(filtered, offset, limit)
	}

	result := LiveMarketResult{
		AsOf: time.Now().Format(time.RFC3339), Market: market, Sort: sortBy, Order: order,
		State: state, Offset: offset, Limit: limit, Matched: matched, Returned: len(rows),
		TDXRequests: tdxRequests, ElapsedMS: time.Since(started).Milliseconds(), Rows: rows,
		Unresolved: unresolved,
	}
	if isJSON(cmd) {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(result)
	}
	printLiveMarketResult(result)
	return nil
}

func validateLiveMarketOptions(market, sortBy, order, state string, offset, limit int) error {
	validMarkets := map[string]bool{"all": true, "sh": true, "sz": true, "bj": true}
	if !validMarkets[market] {
		return fmt.Errorf("market 只能是 all、sh、sz 或 bj")
	}
	validSorts := map[string]bool{
		"code": true, "price": true, "volume": true, "amount": true,
		"change": true, "amplitude": true, "speed": true, "activity": true,
	}
	if !validSorts[sortBy] {
		return fmt.Errorf("sort 只能是 code、price、volume、amount、change、amplitude、speed 或 activity")
	}
	if order != "asc" && order != "desc" {
		return fmt.Errorf("order 只能是 desc 或 asc")
	}
	validStates := map[string]bool{"all": true, "limit-up": true, "limit-down": true, "limits": true}
	if !validStates[state] {
		return fmt.Errorf("state 只能是 all、limit-up、limit-down 或 limits")
	}
	if offset < 0 || offset > math.MaxUint16 {
		return fmt.Errorf("offset 必须在 0-%d 之间", math.MaxUint16)
	}
	if limit < 1 || limit > 500 || offset+limit > math.MaxUint16 {
		return fmt.Errorf("limit 必须在 1-500 之间，且 offset+limit 不能超过 %d", math.MaxUint16)
	}
	return nil
}

func fetchLiveMarketPage(tc *tdx.Client, market, sortBy, order string, offset, limit int) ([]tdx.MarketRankItem, int, error) {
	items := make([]tdx.MarketRankItem, 0, limit)
	requests := 0
	for len(items) < limit {
		count := limit - len(items)
		if count > 100 {
			count = 100
		}
		page, err := tc.GetMarketRank(tdx.MarketRankRequest{
			Market: market, Sort: sortBy, Order: order, Offset: offset + len(items), Limit: count,
		})
		requests++
		if err != nil {
			return nil, requests, err
		}
		items = append(items, page...)
		if len(page) < count {
			break
		}
	}
	return items, requests, nil
}

func fetchLiveLimitRows(tc *tdx.Client, market, state string) ([]tdx.MarketRankItem, int, error) {
	var sides []string
	switch state {
	case "limit-up":
		sides = []string{"up"}
	case "limit-down":
		sides = []string{"down"}
	default:
		sides = []string{"up", "down"}
	}

	all := make([]tdx.MarketRankItem, 0, 100)
	requests := 0
	seen := make(map[string]bool)
	for _, side := range sides {
		order := "desc"
		if side == "down" {
			order = "asc"
		}
		for offset := 0; offset <= math.MaxUint16-100; offset += 100 {
			page, err := tc.GetMarketRank(tdx.MarketRankRequest{
				Market: market, Sort: "change", Order: order, Offset: offset, Limit: 100,
			})
			requests++
			if err != nil {
				return nil, requests, err
			}
			boundaryReached := false
			for _, item := range page {
				if side == "up" && item.ChangePct < 4.5 {
					boundaryReached = true
					break
				}
				if side == "down" && item.ChangePct > -4.5 {
					boundaryReached = true
					break
				}
				key := item.Market + item.Code
				if !seen[key] {
					seen[key] = true
					all = append(all, item)
				}
			}
			if boundaryReached || len(page) < 100 {
				break
			}
		}
	}
	return all, requests, nil
}

func loadLiveMarketMetadata() (map[string]liveMarketMeta, []time.Time, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	ch, err := dwh.New(ctx, cfg)
	if err != nil {
		return nil, nil, err
	}
	defer ch.Close()

	rows, err := ch.Conn().Query(ctx, fmt.Sprintf(`
SELECT code, name, list_date
FROM %s.securities FINAL
WHERE type = 'stock'`, ch.DB()))
	if err != nil {
		return nil, nil, fmt.Errorf("查询股票名称失败: %w", err)
	}
	metas := make(map[string]liveMarketMeta, 6000)
	for rows.Next() {
		var code string
		var meta liveMarketMeta
		if err := rows.Scan(&code, &meta.Name, &meta.ListDate); err != nil {
			rows.Close()
			return nil, nil, err
		}
		metas[code] = meta
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return nil, nil, err
	}
	rows.Close()

	calRows, err := ch.Conn().Query(ctx, fmt.Sprintf(`
SELECT trade_date
FROM %s.trade_cal FINAL
WHERE is_open = 1 AND trade_date <= today()
ORDER BY trade_date`, ch.DB()))
	if err != nil {
		return nil, nil, fmt.Errorf("查询交易日历失败: %w", err)
	}
	tradeDates := make([]time.Time, 0, 4000)
	for calRows.Next() {
		var date time.Time
		if err := calRows.Scan(&date); err != nil {
			calRows.Close()
			return nil, nil, err
		}
		tradeDates = append(tradeDates, date)
	}
	if err := calRows.Err(); err != nil {
		calRows.Close()
		return nil, nil, err
	}
	calRows.Close()
	return metas, tradeDates, nil
}

func enrichLiveMarketRows(items []tdx.MarketRankItem, metas map[string]liveMarketMeta, tradeDates []time.Time, asOf time.Time) []LiveMarketRow {
	rows := make([]LiveMarketRow, 0, len(items))
	for _, item := range items {
		meta, hasMeta := metas[item.Code]
		row := LiveMarketRow{
			Market: item.Market, Code: item.Code, Name: meta.Name,
			Price: item.Price, PreClose: item.PreClose, Open: item.Open, High: item.High, Low: item.Low,
			ChangePct: item.ChangePct, AmplitudePct: item.AmplitudePct, RiseSpeed: item.RiseSpeed,
			Volume: item.Volume, CurrentVolume: item.CurrentVolume, Amount: item.Amount,
			InVolume: item.InVolume, OutVolume: item.OutVolume, Active: item.Active, State: "normal",
		}
		if hasMeta {
			row.State, row.LimitPrice = livePriceLimitState(row, meta, tradeDates, asOf)
		} else {
			row.State = "unknown"
		}
		rows = append(rows, row)
	}
	return rows
}

func livePriceLimitState(row LiveMarketRow, meta liveMarketMeta, tradeDates []time.Time, asOf time.Time) (string, float64) {
	if row.Price <= 0 || row.PreClose <= 0 {
		return "unknown", 0
	}
	if !hasDailyPriceLimit(row.Market, meta.ListDate, tradeDates, asOf) {
		return "no_price_limit", 0
	}
	rate := 0.10
	upperName := strings.ToUpper(meta.Name)
	switch {
	case strings.Contains(upperName, "ST"):
		rate = 0.05
	case strings.HasPrefix(row.Code, "300"), strings.HasPrefix(row.Code, "301"),
		strings.HasPrefix(row.Code, "688"), strings.HasPrefix(row.Code, "689"):
		rate = 0.20
	case row.Market == "BJ":
		rate = 0.30
	}
	priceCents := int64(math.Round(row.Price * 100))
	upCents := int64(math.Floor(row.PreClose*(1+rate)*100 + 0.5))
	downCents := int64(math.Floor(row.PreClose*(1-rate)*100 + 0.5))
	if priceCents == upCents {
		return "limit_up", float64(upCents) / 100
	}
	if priceCents == downCents {
		return "limit_down", float64(downCents) / 100
	}
	return "normal", 0
}

func hasDailyPriceLimit(market string, listDate time.Time, tradeDates []time.Time, asOf time.Time) bool {
	if listDate.IsZero() || asOf.Sub(listDate) > 14*24*time.Hour {
		return true
	}
	tradingDays := 0
	for _, date := range tradeDates {
		if date.Before(listDate) || date.After(asOf) {
			continue
		}
		tradingDays++
	}
	if market == "BJ" {
		return tradingDays > 1
	}
	return tradingDays > 5
}

func pageLiveMarketRows(rows []LiveMarketRow, offset, limit int) []LiveMarketRow {
	if offset >= len(rows) {
		return []LiveMarketRow{}
	}
	end := offset + limit
	if end > len(rows) {
		end = len(rows)
	}
	return rows[offset:end]
}

func sortLiveMarketRows(rows []LiveMarketRow, sortBy, order string) {
	value := func(row LiveMarketRow) float64 {
		switch sortBy {
		case "price":
			return row.Price
		case "volume":
			return float64(row.Volume)
		case "amount":
			return row.Amount
		case "change":
			return row.ChangePct
		case "amplitude":
			return row.AmplitudePct
		case "speed":
			return row.RiseSpeed
		case "activity":
			return float64(row.Active)
		default:
			return 0
		}
	}
	sort.SliceStable(rows, func(i, j int) bool {
		if sortBy == "code" {
			if order == "desc" {
				return rows[i].Code > rows[j].Code
			}
			return rows[i].Code < rows[j].Code
		}
		left, right := value(rows[i]), value(rows[j])
		if left == right {
			return rows[i].Code < rows[j].Code
		}
		if order == "desc" {
			return left > right
		}
		return left < right
	})
}

func printLiveMarketResult(result LiveMarketResult) {
	title := "全市场个股排行"
	switch result.State {
	case "limit-up":
		title = "实时涨停股"
	case "limit-down":
		title = "实时跌停股"
	case "limits":
		title = "实时涨跌停股"
	}
	fmt.Printf("=== %s（获取时间 %s）===\n", title, result.AsOf)
	fmt.Printf("范围：%s  排序：%s %s  返回：%d", marketDisplayName(result.Market), result.Sort, orderDisplayName(result.Order), result.Returned)
	if result.Matched != nil {
		fmt.Printf("/%d", *result.Matched)
	}
	if len(result.Unresolved) > 0 {
		fmt.Printf("  未判定候选：%d", len(result.Unresolved))
	}
	fmt.Printf("  TDX：%d 次请求  耗时：%dms\n\n", result.TDXRequests, result.ElapsedMS)

	table := newTable("代码", 8, "名称", 12, "市场", 4, "现价", 9, "涨跌%", 8, "涨速%", 8, "成交量", 10, "成交额", 10, "状态", 10)
	for _, row := range result.Rows {
		table.Row(row.Code, row.Name, row.Market, fmt.Sprintf("%.2f", row.Price),
			fmt.Sprintf("%+.2f%%", row.ChangePct), fmt.Sprintf("%+.2f%%", row.RiseSpeed),
			fmt.Sprintf("%d", row.Volume), formatAmount(row.Amount), liveMarketStateName(row.State))
	}
	table.Print()
	if len(result.Unresolved) > 0 {
		fmt.Println("\n以下边界候选缺少本地名称/上市日期，未猜测涨跌停状态：")
		unresolvedTable := newTable("代码", 8, "市场", 4, "现价", 9, "涨跌%", 8, "成交额", 10)
		for _, row := range result.Unresolved {
			unresolvedTable.Row(row.Code, row.Market, fmt.Sprintf("%.2f", row.Price),
				fmt.Sprintf("%+.2f%%", row.ChangePct), formatAmount(row.Amount))
		}
		unresolvedTable.Print()
	}
}

func marketDisplayName(market string) string {
	switch market {
	case "sh":
		return "上海A股"
	case "sz":
		return "深圳A股"
	case "bj":
		return "北交所"
	default:
		return "全部A股"
	}
}

func orderDisplayName(order string) string {
	if order == "asc" {
		return "升序"
	}
	return "降序"
}

func liveMarketStateName(state string) string {
	switch state {
	case "limit_up":
		return "涨停"
	case "limit_down":
		return "跌停"
	case "no_price_limit":
		return "无涨跌停"
	case "unknown":
		return "未知"
	default:
		return "-"
	}
}
