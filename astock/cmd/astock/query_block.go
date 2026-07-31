package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/dwh"
)

// addBlockRankCmd 注册 query block rank ——板块涨幅排名（基于 TDX 板块 daily + 成分股事实数据聚合）
//
// 数据源：
//   - astock.kline_daily(type='block') —— 板块自身 close/pre_close/amount（与通达信/同花顺一致）
//   - astock.blocks                    —— 板块元数据（name/type）
//   - astock.block_constituents        —— 成分股映射
//   - astock.kline_daily(type='stock') —— 成分股当日行情
//   - astock.securities                —— 成分股 ST 状态（影响涨停价计算）
//
// 涨停判定复用 query limit 的 round-half-up 规则（floor(x*100+0.5)/100），
// 避免 ClickHouse round() 银行家舍入误判。
//
// 板块类型说明：blocks 表实际只有 concept(270) + style(158)，无独立 industry 类型。
func addBlockRankCmd(blockCmd *cobra.Command) {
	rankCmd := &cobra.Command{
		Use:   "rank [date]",
		Short: "板块涨幅排名（含成分股涨停统计）",
		Long: `板块涨幅排名——基于 TDX 板块 daily + 成分股事实数据聚合。

date 可选，格式 YYYYMMDD；省略则取板块 kline_daily 中最新交易日。
⚠️  日期是位置参数，不是 --date flag：直接写在后面。

示例：
  astock query block rank 20260612              # 概念板块涨幅榜（默认）
  astock query block rank --type style          # 风格板块榜
  astock query block rank --type all --limit 20 # 全板块前 20
  astock query block rank --asc                 # 跌幅榜
  astock query block rank --json                # JSON 输出`,
		Args: cobra.MaximumNArgs(1),
		RunE: runBlockRank,
	}
	rankCmd.Flags().String("type", "concept", "板块类型: concept(默认) / style / all")
	rankCmd.Flags().Int("limit", 50, "返回条数")
	rankCmd.Flags().Bool("asc", false, "升序（跌幅榜）")
	blockCmd.AddCommand(rankCmd)
}

func runBlockRank(cmd *cobra.Command, args []string) error {
	typeStr, _ := cmd.Flags().GetString("type")
	if typeStr != "concept" && typeStr != "style" && typeStr != "all" {
		return fmt.Errorf("--type 必须是 concept/style/all")
	}
	limit, _ := cmd.Flags().GetInt("limit")
	asc, _ := cmd.Flags().GetBool("asc")
	jsonOut := isJSON(cmd)

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	ch, err := dwh.New(ctx, cfg)
	if err != nil {
		return err
	}
	defer ch.Close()

	var date string
	if len(args) == 1 {
		if _, err := time.Parse("20060102", args[0]); err != nil {
			return fmt.Errorf("date 格式应为 YYYYMMDD，如 20260612")
		}
		date = args[0]
	} else {
		row := ch.Conn().QueryRow(ctx,
			fmt.Sprintf("SELECT max(trade_date) FROM %s.kline_daily WHERE type='block'", ch.DB()))
		var d time.Time
		if err := row.Scan(&d); err != nil {
			return fmt.Errorf("查询板块最新交易日失败: %w", err)
		}
		if d.IsZero() {
			return fmt.Errorf("kline_daily 中无板块数据，请先 sync kline --type block --all")
		}
		date = d.Format("20060102")
	}

	list, err := queryBlockRank(ctx, ch, date, typeStr, asc, limit)
	if err != nil {
		return err
	}
	if len(list) == 0 {
		fmt.Fprintf(os.Stderr, "日期 %s 无板块数据（可能板块 daily 未同步该日）\n", formatDate(date))
		return nil
	}

	if jsonOut {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(list)
	}
	printBlockRank(list, formatDate(date), asc)
	return nil
}

// BlockRankRow 板块涨幅榜单行。
type BlockRankRow struct {
	Code         string  `json:"code"`
	Name         string  `json:"name"`
	Type         string  `json:"type"`
	Close        float64 `json:"close"`
	PreClose     float64 `json:"pre_close"`
	ChangePct    float64 `json:"change_pct"`
	Amount       float64 `json:"amount"`
	StockTotal   uint64  `json:"stock_total"`
	UpCount      uint64  `json:"up_count"`
	DownCount    uint64  `json:"down_count"`
	LimitUpCount uint64  `json:"limit_up_count"`
}

func queryBlockRank(ctx context.Context, ch *dwh.Client, date, typeStr string, asc bool, limit int) ([]*BlockRankRow, error) {
	typeFilter := ""
	switch typeStr {
	case "concept":
		typeFilter = "AND b.type = 'concept'"
	case "style":
		typeFilter = "AND b.type = 'style'"
	}
	order := "DESC"
	if asc {
		order = "ASC"
	}

	// 单 SQL：板块自身 daily（TDX 板块涨幅）+ 成分股事实数据聚合（涨家数/跌家数/涨停数）
	// 涨停判定: round-half-up 防银行家舍入，按板别 + ST 状态分桶
	sql := fmt.Sprintf(`
WITH
  block_quote AS (
    SELECT b.code AS code, b.name AS name, b.type AS block_type,
           kd.close AS close, kd.pre_close AS pre_close, kd.amount AS amount,
           if(kd.pre_close > 0, (kd.close - kd.pre_close) / kd.pre_close * 100, 0) AS change_pct
    FROM %s.blocks AS b FINAL
    INNER JOIN %s.kline_daily AS kd ON b.code = kd.code
    WHERE kd.type = 'block' AND kd.trade_date = toDate('%s') %s
  ),
  stock_daily AS (
    SELECT k.code AS code, k.close AS close, k.pre_close AS pre_close, k.high AS high,
           multiIf(
             s.name LIKE '%%ST%%' OR s.name LIKE 'S%%ST%%', 0.05,
             k.code LIKE '688%%' OR k.code LIKE '689%%', 0.20,
             k.code LIKE '300%%' OR k.code LIKE '301%%', 0.20,
             k.code LIKE '43%%' OR k.code LIKE '83%%' OR k.code LIKE '87%%' OR k.code LIKE '88%%' OR k.code LIKE '920%%', 0.30,
             0.10
           ) AS pct_limit
    FROM %s.kline_daily AS k
    INNER JOIN %s.securities AS s ON k.code = s.code AND s.type = 'stock'
    WHERE k.type = 'stock' AND k.trade_date = toDate('%s')
  ),
  member_stats AS (
    SELECT bc.block_code AS block_code,
           count() AS stock_total,
           countIf(sd.close > sd.pre_close) AS up_cnt,
           countIf(sd.close < sd.pre_close) AS down_cnt,
           countIf(sd.close = floor(sd.pre_close * (1 + sd.pct_limit) * 100 + 0.5) / 100
                   AND sd.close = sd.high AND sd.pre_close > 0) AS limit_up_cnt
    FROM %s.block_constituents AS bc FINAL
    LEFT JOIN stock_daily AS sd ON bc.stock_code = sd.code
    GROUP BY bc.block_code
  )
SELECT bq.code, bq.name, bq.block_type, bq.close, bq.pre_close, bq.change_pct, bq.amount,
       coalesce(ms.stock_total, 0) AS stock_total,
       coalesce(ms.up_cnt, 0) AS up_cnt,
       coalesce(ms.down_cnt, 0) AS down_cnt,
       coalesce(ms.limit_up_cnt, 0) AS limit_up_cnt
FROM block_quote AS bq
LEFT JOIN member_stats AS ms ON bq.code = ms.block_code
ORDER BY bq.change_pct %s
LIMIT %d`,
		ch.DB(), ch.DB(), formatDate(date), typeFilter,
		ch.DB(), ch.DB(), formatDate(date),
		ch.DB(),
		order, limit)

	rows, err := ch.Conn().Query(ctx, sql)
	if err != nil {
		return nil, fmt.Errorf("query block rank: %w", err)
	}
	defer rows.Close()

	var list []*BlockRankRow
	for rows.Next() {
		var r BlockRankRow
		if err := rows.Scan(&r.Code, &r.Name, &r.Type, &r.Close, &r.PreClose, &r.ChangePct, &r.Amount,
			&r.StockTotal, &r.UpCount, &r.DownCount, &r.LimitUpCount); err != nil {
			return nil, err
		}
		list = append(list, &r)
	}
	return list, nil
}

func printBlockRank(list []*BlockRankRow, date string, asc bool) {
	label := "涨幅"
	if asc {
		label = "跌幅"
	}
	fmt.Printf("=== %s 板块%s榜 ===\n", date, label)
	t := newTable("排名", 4, "代码", 8, "名称", 14, "类型", 8, "涨幅%", 8, "成交额(亿)", 10, "成分股", 6, "上涨", 4, "下跌", 4, "涨停", 4)
	for i, r := range list {
		t.Row(
			fmt.Sprintf("%d", i+1),
			r.Code, r.Name, r.Type,
			fmt.Sprintf("%+.2f", r.ChangePct),
			fmt.Sprintf("%.2f", r.Amount/1e8),
			fmt.Sprintf("%d", r.StockTotal),
			fmt.Sprintf("%d", r.UpCount),
			fmt.Sprintf("%d", r.DownCount),
			fmt.Sprintf("%d", r.LimitUpCount),
		)
	}
	t.Print()
	fmt.Printf("\n共 %d 个板块\n", len(list))
}

// addBlockMembersCmd 注册 query block members ——板块成分股清单（增强版含当日行情）
//
// 相比老版本 (代码/名称/行业)，新增：当日 close/涨跌幅/成交额/换手%/涨停状态。
// 默认按涨幅降序排列，方便复盘时一眼看到板块内领涨股。
//
// 数据源：astock.block_constituents + astock.securities + astock.kline_daily(type='stock') + astock.finance（换手率口径）
func addBlockMembersCmd(blockCmd *cobra.Command) {
	membersCmd := &cobra.Command{
		Use:   "members <block_code> [date]",
		Short: "板块成分股（含当日涨幅/成交额/涨停状态）",
		Long: `板块成分股清单 + 当日行情。

block_code 必填（6 位板块代码，880xxx）；date 可选 YYYYMMDD，省略取最新交易日。
默认按涨幅降序排列。

示例：
  astock query block members 880904              # 智能机器板块成分股
  astock query block members 880904 20260612     # 指定日期
  astock query block members 880904 --asc        # 跌幅排序
  astock query block members 880904 --json       # JSON 输出`,
		Args: cobra.RangeArgs(1, 2),
		RunE: runBlockMembers,
	}
	membersCmd.Flags().Bool("asc", false, "升序（跌幅榜）")
	blockCmd.AddCommand(membersCmd)
}

func runBlockMembers(cmd *cobra.Command, args []string) error {
	blockCode := args[0]
	asc, _ := cmd.Flags().GetBool("asc")
	jsonOut := isJSON(cmd)

	ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
	defer cancel()
	ch, err := dwh.New(ctx, cfg)
	if err != nil {
		return err
	}
	defer ch.Close()

	var date string
	if len(args) == 2 {
		if _, err := time.Parse("20060102", args[1]); err != nil {
			return fmt.Errorf("date 格式应为 YYYYMMDD，如 20260612")
		}
		date = args[1]
	} else {
		row := ch.Conn().QueryRow(ctx,
			fmt.Sprintf("SELECT max(trade_date) FROM %s.kline_daily WHERE type='stock'", ch.DB()))
		var d time.Time
		if err := row.Scan(&d); err != nil {
			return fmt.Errorf("查询最新交易日失败: %w", err)
		}
		date = d.Format("20060102")
	}

	// 板块名（用于表头）
	var blockName string
	_ = ch.Conn().QueryRow(ctx,
		fmt.Sprintf("SELECT name FROM %s.blocks FINAL WHERE code = '%s'", ch.DB(), blockCode)).Scan(&blockName)

	list, err := queryBlockMembers(ctx, ch, blockCode, date, asc)
	if err != nil {
		return err
	}
	if len(list) == 0 {
		fmt.Println("无成分股或板块代码不存在")
		return nil
	}

	if jsonOut {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(list)
	}
	printBlockMembers(list, blockCode, blockName, formatDate(date), asc)
	return nil
}

// BlockMemberRow 板块成分股清单单行。
type BlockMemberRow struct {
	Code        string  `json:"code"`
	Name        string  `json:"name"`
	Industry    string  `json:"industry"`
	Close       float64 `json:"close"`
	PreClose    float64 `json:"pre_close"`
	ChangePct   float64 `json:"change_pct"`
	Amount      float64 `json:"amount"`
	Turnover    float64 `json:"turnover"`              // 换手率%（volume 手 * 10000 / float_share 股）
	LimitStatus string  `json:"limit_status"`          // 涨停/跌停/-
	DataSource  string  `json:"data_source,omitempty"` // "minute"/"daily"；query/live 不填
}

func queryBlockMembers(ctx context.Context, ch *dwh.Client, blockCode, date string, asc bool) ([]*BlockMemberRow, error) {
	order := "DESC"
	if asc {
		order = "ASC"
	}

	// 单 SQL：成分股 + securities + kline_daily + 涨停状态判定（round-half-up）+ finance.float_share 算换手率
	// 换手率口径：volume(手) * 10000 / float_share(股) = volume股 * 100 / float_share（与 query kline 一致）
	// kline_daily.turnover 字段 TDX 未填（全 0），必须实时计算
	sql := fmt.Sprintf(`
WITH
  finance_latest AS (
    SELECT code, argMax(float_share, report_date) AS float_share
    FROM %s.finance FINAL
    GROUP BY code
  ),
  member_kd AS (
    SELECT k.code AS code, k.close AS close, k.pre_close AS pre_close, k.high AS high, k.low AS low,
           k.amount AS amount, k.volume AS volume,
           multiIf(
             s.name LIKE '%%ST%%' OR s.name LIKE 'S%%ST%%', 0.05,
             k.code LIKE '688%%' OR k.code LIKE '689%%', 0.20,
             k.code LIKE '300%%' OR k.code LIKE '301%%', 0.20,
             k.code LIKE '43%%' OR k.code LIKE '83%%' OR k.code LIKE '87%%' OR k.code LIKE '88%%' OR k.code LIKE '920%%', 0.30,
             0.10
           ) AS pct_limit,
           s.name AS name, s.industry AS industry,
           coalesce(f.float_share, 0) AS float_share
    FROM %s.kline_daily AS k
    INNER JOIN %s.securities AS s ON k.code = s.code AND s.type = 'stock'
    LEFT JOIN finance_latest AS f ON k.code = f.code
    WHERE k.type = 'stock' AND k.trade_date = toDate('%s')
      AND k.code IN (SELECT stock_code FROM %s.block_constituents FINAL WHERE block_code = '%s')
  )
SELECT code, name, industry, close, pre_close,
       if(pre_close > 0, (close - pre_close) / pre_close * 100, 0) AS change_pct,
       amount,
       if(float_share > 0, volume * 10000.0 / float_share, 0) AS turnover_pct,
       multiIf(
         close = floor(pre_close * (1 + pct_limit) * 100 + 0.5) / 100 AND close = high AND pre_close > 0, '涨停',
         close = floor(pre_close * (1 - pct_limit) * 100 + 0.5) / 100 AND close = low AND pre_close > 0, '跌停',
         '-'
       ) AS limit_status
FROM member_kd
ORDER BY change_pct %s`,
		ch.DB(), ch.DB(), ch.DB(), formatDate(date), ch.DB(), blockCode, order)

	rows, err := ch.Conn().Query(ctx, sql)
	if err != nil {
		return nil, fmt.Errorf("query block members: %w", err)
	}
	defer rows.Close()

	var list []*BlockMemberRow
	for rows.Next() {
		var r BlockMemberRow
		if err := rows.Scan(&r.Code, &r.Name, &r.Industry, &r.Close, &r.PreClose,
			&r.ChangePct, &r.Amount, &r.Turnover, &r.LimitStatus); err != nil {
			return nil, err
		}
		list = append(list, &r)
	}
	return list, nil
}

func printBlockMembers(list []*BlockMemberRow, blockCode, blockName, date string, asc bool) {
	label := "涨幅"
	if asc {
		label = "跌幅"
	}
	fmt.Printf("=== %s [%s %s] 成分股%s榜 ===\n", date, blockCode, blockName, label)
	t := newTable("代码", 8, "名称", 12, "行业", 12, "收盘", 8, "涨跌%", 8, "成交额(亿)", 10, "换手%", 8, "状态", 6)
	minuteCnt := 0
	for _, r := range list {
		// data_source == "daily" 表示无分钟数据，显示为空
		noData := r.DataSource == "daily"
		closeStr := "-"
		chgStr := "-"
		amt := "-"
		turn := "-"
		if !noData {
			minuteCnt++
			closeStr = fmt.Sprintf("%.2f", r.Close)
			chgStr = fmt.Sprintf("%+.2f", r.ChangePct)
			if r.Amount > 0 {
				amt = fmt.Sprintf("%.2f", r.Amount/1e8)
			}
			if r.Turnover > 0 {
				turn = fmt.Sprintf("%.2f", r.Turnover)
			}
		}
		t.Row(r.Code, r.Name, r.Industry, closeStr, chgStr, amt, turn, r.LimitStatus)
	}
	t.Print()
	fmt.Printf("\n共 %d 只成分股（%d 只有分钟数据，%d 只无分钟数据）\n", len(list), minuteCnt, len(list)-minuteCnt)
}
