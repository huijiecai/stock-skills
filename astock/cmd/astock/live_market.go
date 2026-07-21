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
	"github.com/huijiecai/stock/astock/internal/model"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

type liveMarketMeta struct {
	name, industry, sector, business string
}

// LiveMarketCandidate is an attention signal. It is deliberately not named a leader.
type LiveMarketCandidate struct {
	Code       string   `json:"code"`
	Name       string   `json:"name"`
	Industry   string   `json:"industry,omitempty"`
	Sector     string   `json:"sector,omitempty"`
	Business   string   `json:"business,omitempty"`
	Price      float64  `json:"price"`
	PreClose   float64  `json:"pre_close"`
	ChangePct  float64  `json:"change_pct"`
	Amount     float64  `json:"amount"`
	Low        float64  `json:"low"`
	ReboundPct float64  `json:"rebound_pct"`
	LimitUp    bool     `json:"limit_up"`
	Reasons    []string `json:"reasons,omitempty"`
}

type LiveMarketScan struct {
	AsOf          string                 `json:"as_of"`
	CoverageMode  string                 `json:"coverage_mode"`
	Universe      int                    `json:"universe"`
	Scanned       int                    `json:"scanned"`
	MissingQuotes int                    `json:"missing_quotes"`
	FailedBatches int                    `json:"failed_batches"`
	TopAmount     []*LiveMarketCandidate `json:"top_amount"`
	Candidates    []*LiveMarketCandidate `json:"candidates"`
}

func buildLiveMarketCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "market",
		Short: "全主板实时异动候选扫描（候选不是龙头）",
		Long: `批量扫描沪深主板实时报价，输出无方向异动候选和成交额前列股票。

该命令只产生注意信号。发现候选后必须搜索市场正在交易的具体预期，列出关联股票，
并验证核心关联股是否成片同步上涨，才能确认归因和方向龙头。`,
		Args: cobra.NoArgs,
		RunE: runLiveMarket,
	}
	cmd.Flags().Int("amount-limit", 50, "返回成交额前 N")
	cmd.Flags().Float64("min-amount", 5_000_000_000, "高影响力异动候选最低当时累计成交额（元）")
	return cmd
}

func isMainBoardCandidateCode(code string) bool {
	for _, prefix := range []string{"000", "001", "002", "600", "601", "603", "605"} {
		if strings.HasPrefix(code, prefix) {
			return true
		}
	}
	return false
}

func marketCandidateReasons(q *model.Quote, minAmount float64) ([]string, float64, bool) {
	if q.PreClose <= 0 || q.Price <= 0 {
		return nil, 0, false
	}
	rebound := 0.0
	if q.Low > 0 {
		rebound = (q.Price - q.Low) / q.PreClose * 100
	}
	limitPrice := math.Floor(q.PreClose*1.10*100+0.5) / 100
	isLimit := q.Price == q.High && q.Price == limitPrice
	if q.Amount < minAmount {
		return nil, rebound, isLimit
	}
	reasons := make([]string, 0, 3)
	if isLimit {
		reasons = append(reasons, "limit_up")
	}
	if q.ChangePct >= 7 {
		reasons = append(reasons, "strong_move")
	}
	if q.ChangePct >= 3 && rebound >= 8 {
		reasons = append(reasons, "deep_reversal")
	}
	return reasons, rebound, isLimit
}

func runLiveMarket(cmd *cobra.Command, _ []string) error {
	amountLimit, _ := cmd.Flags().GetInt("amount-limit")
	minAmount, _ := cmd.Flags().GetFloat64("min-amount")

	tc := tdx.New()
	defer tc.Close()
	ok, reason, err := tc.IsRealtimeNow()
	if err != nil {
		return err
	}
	if !ok {
		return fmt.Errorf("拒绝：%s（历史回放请用 replay_minute_signals.py）", reason)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	ch, err := dwh.New(ctx, cfg)
	if err != nil {
		return err
	}
	defer ch.Close()

	rows, err := ch.Conn().Query(ctx, fmt.Sprintf(`
SELECT code, name, industry, sector, business
FROM %s.securities FINAL
WHERE type = 'stock'
ORDER BY code`, ch.DB()))
	if err != nil {
		return fmt.Errorf("查询主板股票池失败: %w", err)
	}
	metas := make(map[string]liveMarketMeta)
	codes := make([]string, 0, 3500)
	for rows.Next() {
		var code string
		var meta liveMarketMeta
		if err := rows.Scan(&code, &meta.name, &meta.industry, &meta.sector, &meta.business); err != nil {
			rows.Close()
			return err
		}
		if !isMainBoardCandidateCode(code) || strings.Contains(strings.ToUpper(meta.name), "ST") {
			continue
		}
		metas[code] = meta
		codes = append(codes, code)
	}
	rows.Close()

	const batchSize = 50
	quotes := make([]*model.Quote, 0, len(codes))
	failedBatches := 0
	for start := 0; start < len(codes); start += batchSize {
		end := start + batchSize
		if end > len(codes) {
			end = len(codes)
		}
		batch, err := tc.GetQuotes(codes[start:end])
		if err != nil {
			failedBatches++
			continue
		}
		quotes = append(quotes, batch...)
	}
	if len(quotes) == 0 {
		return fmt.Errorf("全主板实时报价扫描失败：%d个批次均无可用数据", failedBatches)
	}

	all := make([]*LiveMarketCandidate, 0, len(quotes))
	for _, q := range quotes {
		meta, exists := metas[q.Code]
		if !exists || q.Price <= 0 || q.PreClose <= 0 {
			continue
		}
		reasons, rebound, isLimit := marketCandidateReasons(q, minAmount)
		all = append(all, &LiveMarketCandidate{
			Code: q.Code, Name: meta.name, Industry: meta.industry, Sector: meta.sector,
			Business: meta.business, Price: q.Price, PreClose: q.PreClose,
			ChangePct: q.ChangePct, Amount: q.Amount, Low: q.Low, ReboundPct: rebound,
			LimitUp: isLimit, Reasons: reasons,
		})
	}
	sort.Slice(all, func(i, j int) bool { return all[i].Amount > all[j].Amount })
	if amountLimit < 0 {
		amountLimit = 0
	}
	topEnd := amountLimit
	if topEnd > len(all) {
		topEnd = len(all)
	}
	topAmount := append([]*LiveMarketCandidate(nil), all[:topEnd]...)

	for rank, row := range topAmount {
		if rank < 20 && row.ChangePct >= 5 && len(row.Reasons) == 0 {
			row.Reasons = append(row.Reasons, "top_amount_strength")
		}
	}
	candidates := make([]*LiveMarketCandidate, 0)
	for _, row := range all {
		if len(row.Reasons) > 0 {
			candidates = append(candidates, row)
		}
	}

	output := LiveMarketScan{
		AsOf: time.Now().Format("2006-01-02 15:04:05"), CoverageMode: "all_main_board_snapshot",
		Universe: len(codes), Scanned: len(all), MissingQuotes: len(codes) - len(all), FailedBatches: failedBatches,
		TopAmount: topAmount, Candidates: candidates,
	}
	if isJSON(cmd) {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(output)
	}

	fmt.Printf("=== 全主板异动候选 %s ===\n", output.AsOf)
	fmt.Printf("覆盖：%d/%d，缺失报价：%d，失败批次：%d；候选不是龙头，必须继续归因\n",
		output.Scanned, output.Universe, output.MissingQuotes, output.FailedBatches)
	table := newTable("代码", 8, "名称", 12, "涨跌%", 8, "低点反转", 9, "成交额", 10, "信号", 28)
	for _, row := range candidates {
		table.Row(row.Code, row.Name, fmt.Sprintf("%+.2f%%", row.ChangePct),
			fmt.Sprintf("%+.2f%%", row.ReboundPct), formatAmount(row.Amount), strings.Join(row.Reasons, "/"))
	}
	table.Print()
	return nil
}
