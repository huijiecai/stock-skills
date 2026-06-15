package main

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"sort"
	"time"

	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/dwh"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

// addLiveBlockCmd 注册 live block 子命令树（盘中专用，不落库）。
//
// 与 query block * 的本质区别：
//   - 直拉 TDX MQuote 实时协议，**不读 ClickHouse kline_daily**
//   - 调用前必经 IsRealtimeNow 守门员；非交易日 / 盘前直接拒绝
//   - 数据是"当下分钟级"的，不是"昨日收盘"，盘中决策刚性需求
//
// 共两个子命令：
//
//	live block rank             —— 全市场板块实时涨幅榜
//	live block members <code>   —— 单板块成分股实时涨幅榜
//
// 板块本身用 sh880xxx 代码拉 MQuote（已验证 IndexCode 路由 + GetQuotes 内置 MarketOfIndex）；
// 成分股从 ClickHouse block_constituents 表查 stock_code 列表 + 实时拉报价。
func addLiveBlockCmd(liveCmd *cobra.Command) {
	blockCmd := &cobra.Command{
		Use:   "block",
		Short: "板块实时数据（直拉 TDX 不落库；非交易日拒绝）",
	}

	blockCmd.AddCommand(buildLiveBlockRankCmd())
	blockCmd.AddCommand(buildLiveBlockMembersCmd())
	liveCmd.AddCommand(blockCmd)
}

// LiveBlockRankRow live block rank 单行。
type LiveBlockRankRow struct {
	Code         string  `json:"code"`
	Name         string  `json:"name"`
	BlockType    string  `json:"block_type"` // concept/style
	Price        float64 `json:"price"`
	PreClose     float64 `json:"pre_close"`
	ChangePct    float64 `json:"change_pct"`
	Amount       float64 `json:"amount"`
	LimitUpCount int     `json:"limit_up_count"`
}

func buildLiveBlockRankCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "rank",
		Short: "板块实时涨幅榜（盘中专用）",
		Long: `板块实时涨幅榜——直拉 TDX MQuote 协议，强制 quote.date == today。

非交易日 / 盘前会立即拒绝，不返回历史快照。

示例：
  astock live block rank                    # 全部板块（按涨幅 DESC）
  astock live block rank --type concept     # 仅概念板块
  astock live block rank --type style       # 仅风格板块
  astock live block rank --asc              # 跌幅榜
  astock live block rank --limit 20         # 仅取前 20
  astock live block rank --json`,
		Args: cobra.NoArgs,
		RunE: runLiveBlockRank,
	}
	cmd.Flags().String("type", "all", "板块类型: concept/style/all")
	cmd.Flags().Bool("asc", false, "升序（跌幅榜）")
	cmd.Flags().Int("limit", 50, "返回前 N（默认 50；0 表示不限制）")
	return cmd
}

func runLiveBlockRank(cmd *cobra.Command, args []string) error {
	blockType, _ := cmd.Flags().GetString("type")
	if blockType != "all" && blockType != "concept" && blockType != "style" {
		return fmt.Errorf("--type 必须是 all/concept/style")
	}
	asc, _ := cmd.Flags().GetBool("asc")
	limit, _ := cmd.Flags().GetInt("limit")
	jsonOut := isJSON(cmd)

	tc := tdx.New()
	defer tc.Close()

	// 1. 守门员：非交易日 / 盘前 → 拒绝
	ok, reason, err := tc.IsRealtimeNow()
	if err != nil {
		return err
	}
	if !ok {
		return fmt.Errorf("拒绝：%s（如需复盘请用 query block rank）", reason)
	}

	// 2. 从 CH 拉板块清单（code, name, type）
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	ch, err := dwh.New(ctx, cfg)
	if err != nil {
		return err
	}
	defer ch.Close()

	typeFilter := ""
	if blockType != "all" {
		typeFilter = fmt.Sprintf(" WHERE type = '%s'", blockType)
	}
	sqlBlk := fmt.Sprintf("SELECT code, name, type FROM %s.blocks FINAL%s ORDER BY code",
		ch.DB(), typeFilter)
	rows, err := ch.Conn().Query(ctx, sqlBlk)
	if err != nil {
		return fmt.Errorf("查询板块清单失败: %w", err)
	}
	type blockMeta struct {
		code, name, btype string
	}
	var metas []blockMeta
	for rows.Next() {
		var m blockMeta
		if err := rows.Scan(&m.code, &m.name, &m.btype); err != nil {
			rows.Close()
			return err
		}
		metas = append(metas, m)
	}
	rows.Close()
	if len(metas) == 0 {
		return fmt.Errorf("blocks 表为空，请先 sync info")
	}

	// 3. 分批拉 TDX 实时报价（MQuote 单批上限 ~50，安全 50）
	const batch = 50
	codes := make([]string, len(metas))
	for i, m := range metas {
		codes[i] = m.code
	}
	priceMap := make(map[string]struct {
		price, preClose, change, amount float64
	}, len(metas))
	for i := 0; i < len(codes); i += batch {
		end := i + batch
		if end > len(codes) {
			end = len(codes)
		}
		quotes, err := tc.GetQuotes(codes[i:end])
		if err != nil {
			return fmt.Errorf("拉板块实时报价失败 [%d:%d]: %w", i, end, err)
		}
		for _, q := range quotes {
			priceMap[q.Code] = struct {
				price, preClose, change, amount float64
			}{q.Price, q.PreClose, q.ChangePct, q.Amount}
		}
	}

	// 4. 计算各板块涨停数：拉成分股实时报价 + ST判断 + round-half-up 涨停判定
	limitUpMap := calcLiveLimitUp(ctx, ch, tc, codes)

	// 5. 拼装 + 排序 + 截断
	rowsOut := make([]*LiveBlockRankRow, 0, len(metas))
	for _, m := range metas {
		p, ok := priceMap[m.code]
		if !ok || p.price == 0 {
			continue // 板块无实时数据则跳过
		}
		rowsOut = append(rowsOut, &LiveBlockRankRow{
			Code: m.code, Name: m.name, BlockType: m.btype,
			Price: p.price, PreClose: p.preClose, ChangePct: p.change, Amount: p.amount,
			LimitUpCount: limitUpMap[m.code],
		})
	}
	sort.Slice(rowsOut, func(i, j int) bool {
		if asc {
			return rowsOut[i].ChangePct < rowsOut[j].ChangePct
		}
		return rowsOut[i].ChangePct > rowsOut[j].ChangePct
	})
	if limit > 0 && len(rowsOut) > limit {
		rowsOut = rowsOut[:limit]
	}

	if jsonOut {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(rowsOut)
	}
	dir := "涨幅榜"
	if asc {
		dir = "跌幅榜"
	}
	fmt.Printf("=== 实时板块%s（%s · 共 %d）===\n", dir, time.Now().Format("15:04:05"), len(rowsOut))
	t := newTable(
		"代码", 8,
		"名称", 16,
		"类型", 8,
		"现价", 10,
		"昨收", 10,
		"涨跌%", 8,
		"成交额", 10,
		"涨停", 4,
	)
	for _, r := range rowsOut {
		t.Row(
			r.Code, r.Name, r.BlockType,
			fmt.Sprintf("%.2f", r.Price),
			fmt.Sprintf("%.2f", r.PreClose),
			fmt.Sprintf("%+.2f%%", r.ChangePct),
			formatAmount(r.Amount),
			fmt.Sprintf("%d", r.LimitUpCount),
		)
	}
	t.Print()
	return nil
}

// calcLiveLimitUp 拉取所有成分股实时报价，计算各板块涨停数。
// 逻辑复用 query block rank 的 round-half-up 涨停判定规则：
//   - ST: 5%, 创业板/科创板: 20%, 北交所: 30%, 主板: 10%
//   - 涨停条件: price == high AND price == floor(preClose * (1+pctLimit) * 100 + 0.5) / 100
func calcLiveLimitUp(ctx context.Context, ch *dwh.Client, tc *tdx.Client, blockCodes []string) map[string]int {
	result := make(map[string]int, len(blockCodes))

	// 1. 从 CH 拉全部 block_constituents + securities ST状态
	sql := fmt.Sprintf(`
SELECT bc.block_code, bc.stock_code, s.name
FROM %s.block_constituents AS bc FINAL
INNER JOIN %s.securities AS s ON bc.stock_code = s.code AND s.type = 'stock'`,
		ch.DB(), ch.DB())

	rows, err := ch.Conn().Query(ctx, sql)
	if err != nil {
		return result
	}
	defer rows.Close()

	// block_code -> []stock_code, stock_code -> name (for ST detection)
	blockStocks := make(map[string][]string)  // block -> stocks
	stockNames := make(map[string]string)      // stock -> name
	uniqueStocks := make(map[string]struct{})  // dedup
	for rows.Next() {
		var blockCode, stockCode, stockName string
		if err := rows.Scan(&blockCode, &stockCode, &stockName); err != nil {
			continue
		}
		blockStocks[blockCode] = append(blockStocks[blockCode], stockCode)
		stockNames[stockCode] = stockName
		uniqueStocks[stockCode] = struct{}{}
	}

	// 2. 批量拉全部唯一股票实时报价
	allCodes := make([]string, 0, len(uniqueStocks))
	for code := range uniqueStocks {
		allCodes = append(allCodes, code)
	}

	type stockQuote struct {
		price, preClose, high float64
	}
	quoteMap := make(map[string]stockQuote, len(allCodes))

	const batch = 50
	for i := 0; i < len(allCodes); i += batch {
		end := i + batch
		if end > len(allCodes) {
			end = len(allCodes)
		}
		quotes, err := tc.GetQuotes(allCodes[i:end])
		if err != nil {
			continue
		}
		for _, q := range quotes {
			quoteMap[q.Code] = stockQuote{q.Price, q.PreClose, q.High}
		}
	}

	// 3. 判定每只股票是否涨停
	isLimitUp := make(map[string]bool, len(allCodes))
	for code, q := range quoteMap {
		if q.preClose <= 0 || q.price <= 0 {
			continue
		}
		// 涨停幅度
		pctLimit := 0.10
		name := stockNames[code]
		if contains(name, "ST") {
			pctLimit = 0.05
		} else if len(code) >= 3 {
			prefix := code[:3]
			switch {
			case prefix == "300" || prefix == "301":
				pctLimit = 0.20
			case prefix == "688" || prefix == "689":
				pctLimit = 0.20
			case prefix == "920" || prefix == "430" || prefix == "830" || prefix == "870" || prefix == "880":
				pctLimit = 0.30
			}
		}
		// round-half-up 涨停价
		limitPrice := math.Floor(q.preClose*(1+pctLimit)*100+0.5) / 100
		if q.price == q.high && q.price == limitPrice {
			isLimitUp[code] = true
		}
	}

	// 4. 汇总各板块涨停数
	for _, blockCode := range blockCodes {
		cnt := 0
		for _, sc := range blockStocks[blockCode] {
			if isLimitUp[sc] {
				cnt++
			}
		}
		result[blockCode] = cnt
	}
	return result
}

// contains 检查字符串是否包含子串（用于 ST 判定）
func contains(s, sub string) bool {
	return len(s) >= len(sub) && (s == sub || len(s) > 0 && containsStr(s, sub))
}

func containsStr(s, sub string) bool {
	for i := 0; i <= len(s)-len(sub); i++ {
		if s[i:i+len(sub)] == sub {
			return true
		}
	}
	return false
}

// LiveBlockMemberRow live block members 单行。
type LiveBlockMemberRow struct {
	Code      string  `json:"code"`
	Name      string  `json:"name"`
	Industry  string  `json:"industry,omitempty"`
	Price     float64 `json:"price"`
	PreClose  float64 `json:"pre_close"`
	ChangePct float64 `json:"change_pct"`
	Amount    float64 `json:"amount"`
}

func buildLiveBlockMembersCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "members <block_code>",
		Short: "板块成分股实时涨幅榜（盘中专用）",
		Long: `板块成分股实时涨幅榜——成分股清单来自 ClickHouse block_constituents，
报价来自 TDX MQuote 协议，强制 quote.date == today。

非交易日 / 盘前会立即拒绝。

示例：
  astock live block members 880904           # 智能机器板块（涨幅 DESC）
  astock live block members 880904 --asc     # 升序
  astock live block members 880904 --limit 10
  astock live block members 880904 --json`,
		Args: cobra.ExactArgs(1),
		RunE: runLiveBlockMembers,
	}
	cmd.Flags().Bool("asc", false, "升序")
	cmd.Flags().Int("limit", 0, "返回前 N（默认全部）")
	return cmd
}

func runLiveBlockMembers(cmd *cobra.Command, args []string) error {
	input := args[0]
	asc, _ := cmd.Flags().GetBool("asc")
	limit, _ := cmd.Flags().GetInt("limit")
	jsonOut := isJSON(cmd)

	tc := tdx.New()
	defer tc.Close()

	// 守门员
	ok, reason, err := tc.IsRealtimeNow()
	if err != nil {
		return err
	}
	if !ok {
		return fmt.Errorf("拒绝：%s（如需复盘请用 query block members）", reason)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()
	ch, err := dwh.New(ctx, cfg)
	if err != nil {
		return err
	}
	defer ch.Close()

	// 1. 验板块存在——先按代码精确查，失败再按名称查（UX：支持传入名称如 "有色金属"）
	var blockCode, blockName, blockType string
	rowCode := ch.Conn().QueryRow(ctx,
		fmt.Sprintf("SELECT code, name, type FROM %s.blocks FINAL WHERE code = '%s' LIMIT 1", ch.DB(), input))
	if e := rowCode.Scan(&blockCode, &blockName, &blockType); e != nil {
		rowName := ch.Conn().QueryRow(ctx,
			fmt.Sprintf("SELECT code, name, type FROM %s.blocks FINAL WHERE name = '%s' LIMIT 1", ch.DB(), input))
		if e2 := rowName.Scan(&blockCode, &blockName, &blockType); e2 != nil {
			return fmt.Errorf("板块 %s 不存在（既无此代码也无此名称）", input)
		}
	}

	memSQL := fmt.Sprintf(`
SELECT bc.stock_code, s.name, s.industry
FROM %s.block_constituents AS bc FINAL
INNER JOIN %s.securities AS s ON bc.stock_code = s.code AND s.type = 'stock'
WHERE bc.block_code = '%s'
ORDER BY bc.stock_code`,
		ch.DB(), ch.DB(), blockCode)
	rows, err := ch.Conn().Query(ctx, memSQL)
	if err != nil {
		return fmt.Errorf("查询成分股失败: %w", err)
	}
	type stockMeta struct {
		code, name, industry string
	}
	var metas []stockMeta
	for rows.Next() {
		var m stockMeta
		if err := rows.Scan(&m.code, &m.name, &m.industry); err != nil {
			rows.Close()
			return err
		}
		metas = append(metas, m)
	}
	rows.Close()
	if len(metas) == 0 {
		return fmt.Errorf("板块 %s 无成分股", blockCode)
	}

	// 2. 分批拉实时报价
	const batch = 50
	codes := make([]string, len(metas))
	for i, m := range metas {
		codes[i] = m.code
	}
	priceMap := make(map[string]struct {
		price, preClose, change, amount float64
	}, len(metas))
	for i := 0; i < len(codes); i += batch {
		end := i + batch
		if end > len(codes) {
			end = len(codes)
		}
		quotes, err := tc.GetQuotes(codes[i:end])
		if err != nil {
			return fmt.Errorf("拉成分股实时报价失败 [%d:%d]: %w", i, end, err)
		}
		for _, q := range quotes {
			priceMap[q.Code] = struct {
				price, preClose, change, amount float64
			}{q.Price, q.PreClose, q.ChangePct, q.Amount}
		}
	}

	// 3. 拼装 + 排序 + 截断
	rowsOut := make([]*LiveBlockMemberRow, 0, len(metas))
	for _, m := range metas {
		p, ok := priceMap[m.code]
		if !ok || p.price == 0 {
			continue
		}
		rowsOut = append(rowsOut, &LiveBlockMemberRow{
			Code: m.code, Name: m.name, Industry: m.industry,
			Price: p.price, PreClose: p.preClose, ChangePct: p.change, Amount: p.amount,
		})
	}
	sort.Slice(rowsOut, func(i, j int) bool {
		if asc {
			return rowsOut[i].ChangePct < rowsOut[j].ChangePct
		}
		return rowsOut[i].ChangePct > rowsOut[j].ChangePct
	})
	if limit > 0 && len(rowsOut) > limit {
		rowsOut = rowsOut[:limit]
	}

	if jsonOut {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(rowsOut)
	}
	fmt.Printf("=== %s（%s · %s） · 实时%s · 共 %d ===\n",
		blockName, blockCode, blockType,
		map[bool]string{true: "升序", false: "涨幅榜"}[asc], len(rowsOut))
	t := newTable(
		"代码", 6,
		"名称", 12,
		"行业", 16,
		"现价", 10,
		"昨收", 10,
		"涨跌%", 8,
		"成交额", 10,
	)
	for _, r := range rowsOut {
		t.Row(
			r.Code, r.Name, r.Industry,
			fmt.Sprintf("%.2f", r.Price),
			fmt.Sprintf("%.2f", r.PreClose),
			fmt.Sprintf("%+.2f%%", r.ChangePct),
			formatAmount(r.Amount),
		)
	}
	t.Print()
	return nil
}
