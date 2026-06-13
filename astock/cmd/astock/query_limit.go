package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"sort"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/dwh"
)

// addLimitCmd 注册 query limit 子命令——涨停/跌停清单（按日，含连板数与概念标签）。
//
// 数据源：astock.kline_daily + astock.securities + astock.block_constituents + astock.blocks，
// 全部来自 ClickHouse SQL 派生，不依赖任何 TDX 通道。
//
// 字段精度说明（参见 docs/superpowers/specs/2026-05-24-astock-design.md）：
//   - 涨停判定 100% 精确（按板别 + ST 状态分桶 + 收盘=涨停价=最高价）
//   - 连板数 100% 精确（跨日反查 kline_daily 连续涨停记录）
//   - 概念标签 top3 来自 block_constituents JOIN blocks WHERE type='concept'
//   - 不提供：开板次数 / 首封时间 / 封单金额（粒度限制下不可靠或需破单源）
func addLimitCmd(queryCmd *cobra.Command) {
	limitCmd := &cobra.Command{
		Use:   "limit [date]",
		Short: "涨停/跌停清单（含连板数 + 概念标签）",
		Long: `涨停/跌停清单——基于 kline_daily 派生，含连板数与概念标签。

date 可选，格式 YYYYMMDD；省略则取 kline_daily 中最新交易日。

示例：
  astock query limit 20260612              # 涨停清单
  astock query limit 20260612 --side down  # 跌停清单
  astock query limit 20260612 --exclude-st # 涨停清单（排除 ST）
  astock query limit                       # 最近交易日涨停
  astock query limit --json                # JSON 输出`,
		Args: cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			side, _ := cmd.Flags().GetString("side")
			if side != "up" && side != "down" {
				return fmt.Errorf("--side 必须是 up 或 down")
			}
			excludeST, _ := cmd.Flags().GetBool("exclude-st")
			ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			// 解析日期
			var date string
			if len(args) == 1 {
				if _, err := time.Parse("20060102", args[0]); err != nil {
					return fmt.Errorf("date 格式应为 YYYYMMDD，如 20260612")
				}
				date = args[0]
			} else {
				row := ch.Conn().QueryRow(ctx,
					fmt.Sprintf("SELECT max(trade_date) FROM %s.kline_daily WHERE type='stock'", ch.DB()))
				var d time.Time
				if err := row.Scan(&d); err != nil {
					return fmt.Errorf("查询最新交易日失败: %w", err)
				}
				date = d.Format("20060102")
			}

			list, err := queryLimitList(ctx, ch, date, side, excludeST)
			if err != nil {
				return err
			}
			if len(list) == 0 {
				fmt.Printf("日期 %s 无%s股\n", formatDate(date), sideLabel(side))
				return nil
			}

			if isJSON(cmd) {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(list)
			}
			printLimitTable(list, formatDate(date), side)
			return nil
		},
	}
	limitCmd.Flags().String("side", "up", "方向: up(涨停) / down(跌停)")
	limitCmd.Flags().Bool("exclude-st", false, "排除 ST/*ST 股")
	// query limit ladder 作为子命令挂在 limit 下（命名宪法 v1：禁连字符复合命令名）
	limitCmd.AddCommand(buildLimitLadderSubCmd())
	queryCmd.AddCommand(limitCmd)
}

// LimitStock 涨/跌停清单中的一只股票。
type LimitStock struct {
	Code         string   `json:"code"`
	Name         string   `json:"name"`
	Board        string   `json:"board"`              // main/growth/star/beijing/st
	PctLimit     float64  `json:"pct_limit"`          // 涨幅上限（小数）
	Close        float64  `json:"close"`              // 收盘价
	LimitPrice   float64  `json:"limit_price"`        // 涨停价/跌停价
	ChangePct    float64  `json:"change_pct"`         // 涨跌幅 %
	Amount       float64  `json:"amount"`             // 成交额（元）
	ConsecDays   int      `json:"consecutive_days"`   // 连板数（含当日，>=1）
	Concepts     []string `json:"concepts,omitempty"` // 概念标签 top3
}

// queryLimitList 派生当日涨停（或跌停）清单。
//
// 流程：
//  1. 单 SQL 取当日涨/跌停股 + 当日数据 + 板别（约几十只）
//  2. 单 SQL 拉这些股最近 30 个交易日 daily 数据 → 在 Go 层计算连板数
//  3. 单 SQL 拉这些股的概念标签 top3 → 填充
//
// 涨跌停价采用 A 股交易所规则：四舍五入到分（round-half-up），
// 用 floor(x*100+0.5)/100 实现，避免 ClickHouse round() 的银行家舍入误判。
func queryLimitList(ctx context.Context, ch *dwh.Client, date, side string, excludeST bool) ([]*LimitStock, error) {
	// ----- 1. 当日涨/跌停股 -----
	var hitExpr, limitPriceExpr string
	if side == "up" {
		hitExpr = "close = floor(pre_close * (1 + pct_limit) * 100 + 0.5) / 100 AND close = high AND pre_close > 0"
		limitPriceExpr = "floor(pre_close * (1 + pct_limit) * 100 + 0.5) / 100"
	} else {
		hitExpr = "close = floor(pre_close * (1 - pct_limit) * 100 + 0.5) / 100 AND close = low AND pre_close > 0"
		limitPriceExpr = "floor(pre_close * (1 - pct_limit) * 100 + 0.5) / 100"
	}
	stFilter := ""
	if excludeST {
		// stFilter 作为 %s 占位符传入 fmt.Sprintf，不会二次格式化，用单 %%
		stFilter = "AND s.name NOT LIKE '%ST%' AND s.name NOT LIKE 'S%ST%'"
	}

	sql1 := fmt.Sprintf(`
WITH joined AS (
  SELECT
    k.code AS code,
    k.close AS close,
    k.pre_close AS pre_close,
    k.high AS high,
    k.low AS low,
    k.amount AS amount,
    s.name AS name,
    multiIf(
      s.name LIKE '%%ST%%' OR s.name LIKE 'S%%ST%%', 'st',
      k.code LIKE '688%%' OR k.code LIKE '689%%', 'star',
      k.code LIKE '300%%' OR k.code LIKE '301%%', 'growth',
      k.code LIKE '43%%' OR k.code LIKE '83%%' OR k.code LIKE '87%%' OR k.code LIKE '88%%' OR k.code LIKE '920%%', 'beijing',
      'main'
    ) AS board,
    multiIf(
      s.name LIKE '%%ST%%' OR s.name LIKE 'S%%ST%%', 0.05,
      k.code LIKE '688%%' OR k.code LIKE '689%%', 0.20,
      k.code LIKE '300%%' OR k.code LIKE '301%%', 0.20,
      k.code LIKE '43%%' OR k.code LIKE '83%%' OR k.code LIKE '87%%' OR k.code LIKE '88%%' OR k.code LIKE '920%%', 0.30,
      0.10
    ) AS pct_limit
  FROM %s.kline_daily AS k
  INNER JOIN %s.securities AS s ON k.code = s.code AND s.type = 'stock'
  WHERE k.type='stock' AND k.trade_date = toDate('%s') %s
)
SELECT code, name, board, pct_limit, close, %s AS limit_price,
       (close - pre_close) / pre_close * 100 AS change_pct, amount
FROM joined
WHERE %s
ORDER BY amount DESC`,
		ch.DB(), ch.DB(), formatDate(date), stFilter, limitPriceExpr, hitExpr)

	rows, err := ch.Conn().Query(ctx, sql1)
	if err != nil {
		return nil, fmt.Errorf("query limit list: %w", err)
	}
	defer rows.Close()

	var list []*LimitStock
	codeSet := make(map[string]*LimitStock)
	for rows.Next() {
		var s LimitStock
		if err := rows.Scan(&s.Code, &s.Name, &s.Board, &s.PctLimit, &s.Close,
			&s.LimitPrice, &s.ChangePct, &s.Amount); err != nil {
			return nil, err
		}
		s.ConsecDays = 1 // 当日涨停默认 1，下面跨日反查会更新
		list = append(list, &s)
		codeSet[s.Code] = &s
	}
	if len(list) == 0 {
		return list, nil
	}
	// 重新建立指针映射（list 中是 &s 的复制问题修复）
	codeSet = make(map[string]*LimitStock, len(list))
	for _, p := range list {
		codeSet[p.Code] = p
	}

	// ----- 2. 计算连板数（仅 side=up 才计算；跌停连板较少需求） -----
	if side == "up" {
		if err := fillConsecutiveDays(ctx, ch, list, codeSet, date); err != nil {
			return nil, fmt.Errorf("fill consec: %w", err)
		}
	}

	// ----- 3. 概念标签 top3 -----
	if err := fillConcepts(ctx, ch, list, codeSet); err != nil {
		// 概念标签是非关键字段，失败不应导致整体失败
		fmt.Fprintf(os.Stderr, "warning: 概念标签查询失败: %v\n", err)
	}

	return list, nil
}

// fillConsecutiveDays 跨日反查 kline_daily，从 date 往前数连续涨停天数。
//
// 实现：单 SQL 拉所有目标股最近 30 个交易日的「涨停标记 + trade_date」，
// 在 Go 层按 code 分组并从最新日往前累加连续 true。
func fillConsecutiveDays(ctx context.Context, ch *dwh.Client, list []*LimitStock, codeSet map[string]*LimitStock, date string) error {
	codes := make([]string, 0, len(list))
	for _, s := range list {
		codes = append(codes, "'"+s.Code+"'")
	}
	codeIn := strings.Join(codes, ",")

	sql := fmt.Sprintf(`
WITH joined AS (
  SELECT
    k.code AS code,
    k.trade_date AS trade_date,
    k.close AS close,
    k.pre_close AS pre_close,
    k.high AS high,
    multiIf(
      s.name LIKE '%%ST%%' OR s.name LIKE 'S%%ST%%', 0.05,
      k.code LIKE '688%%' OR k.code LIKE '689%%', 0.20,
      k.code LIKE '300%%' OR k.code LIKE '301%%', 0.20,
      k.code LIKE '43%%' OR k.code LIKE '83%%' OR k.code LIKE '87%%' OR k.code LIKE '88%%' OR k.code LIKE '920%%', 0.30,
      0.10
    ) AS pct_limit
  FROM %s.kline_daily AS k
  INNER JOIN %s.securities AS s ON k.code = s.code AND s.type = 'stock'
  WHERE k.type='stock'
    AND k.code IN (%s)
    AND k.trade_date <= toDate('%s')
    AND k.trade_date >= toDate('%s') - INTERVAL 60 DAY
)
SELECT code, trade_date,
       (close = floor(pre_close * (1 + pct_limit) * 100 + 0.5) / 100 AND close = high AND pre_close > 0) AS is_lu
FROM joined
ORDER BY code ASC, trade_date DESC`,
		ch.DB(), ch.DB(), codeIn, formatDate(date), formatDate(date))

	rows, err := ch.Conn().Query(ctx, sql)
	if err != nil {
		return err
	}
	defer rows.Close()

	type record struct {
		date time.Time
		isLU bool
	}
	codeRecords := make(map[string][]record)
	for rows.Next() {
		var code string
		var d time.Time
		var isLU bool
		if err := rows.Scan(&code, &d, &isLU); err != nil {
			return err
		}
		codeRecords[code] = append(codeRecords[code], record{date: d, isLU: isLU})
	}

	// 每只股从最新日（list[0]）往前数连续 isLU=true 天数
	for _, s := range list {
		recs := codeRecords[s.Code]
		// 已经按 trade_date DESC 排好；recs[0] 是当天
		consec := 0
		for _, r := range recs {
			if r.isLU {
				consec++
			} else {
				break
			}
		}
		if consec < 1 {
			consec = 1 // 当日明明涨停，至少 1 板
		}
		s.ConsecDays = consec
	}
	return nil
}

// fillConcepts 取每只股的概念标签 top3。
//
// 概念排序规则：按板块成员数 ASC（成员少的概念越具体精准，AI 归因价值更高）。
// 可选地未来支持 --concept-sort=desc 切换。
func fillConcepts(ctx context.Context, ch *dwh.Client, list []*LimitStock, codeSet map[string]*LimitStock) error {
	if len(list) == 0 {
		return nil
	}
	codes := make([]string, 0, len(list))
	for _, s := range list {
		codes = append(codes, "'"+s.Code+"'")
	}
	codeIn := strings.Join(codes, ",")

	// 取所有目标股的所有 concept 板块（不限制 top3，在 Go 层裁剪）
	sql := fmt.Sprintf(`
SELECT bc.stock_code, b.name, b.stock_count
FROM %s.block_constituents AS bc
INNER JOIN %s.blocks AS b ON bc.block_code = b.code
WHERE b.type = 'concept' AND bc.stock_code IN (%s)
ORDER BY bc.stock_code, b.stock_count ASC`, ch.DB(), ch.DB(), codeIn)

	rows, err := ch.Conn().Query(ctx, sql)
	if err != nil {
		return err
	}
	defer rows.Close()

	type cb struct {
		name  string
		count uint32
	}
	codeBlocks := make(map[string][]cb)
	for rows.Next() {
		var code, name string
		var cnt uint32
		if err := rows.Scan(&code, &name, &cnt); err != nil {
			return err
		}
		codeBlocks[code] = append(codeBlocks[code], cb{name: name, count: cnt})
	}

	for _, s := range list {
		blks := codeBlocks[s.Code]
		// 按 stock_count ASC 排序（取最具体的概念）
		sort.Slice(blks, func(i, j int) bool { return blks[i].count < blks[j].count })
		// 取 top3
		if len(blks) > 3 {
			blks = blks[:3]
		}
		s.Concepts = make([]string, 0, len(blks))
		for _, b := range blks {
			s.Concepts = append(s.Concepts, b.name)
		}
	}
	return nil
}

// printLimitTable 中文表格输出。
func printLimitTable(list []*LimitStock, dateLabel, side string) {
	t := newTable(
		"代码", 6,
		"名称", 12,
		"板别", 6,
		"涨幅%", 8,
		"收盘价", 8,
		"涨停价", 8,
		"成交额", 10,
		"连板", 4,
		"概念标签", 30,
	)
	for _, s := range list {
		concepts := strings.Join(s.Concepts, "/")
		consec := fmt.Sprintf("%d", s.ConsecDays)
		if side == "down" {
			consec = "-" // 跌停不计连板
		}
		t.Row(
			s.Code,
			s.Name,
			boardLabel(s.Board),
			fmt.Sprintf("%+.2f%%", s.ChangePct),
			fmt.Sprintf("%.2f", s.Close),
			fmt.Sprintf("%.2f", s.LimitPrice),
			formatAmount(s.Amount),
			consec,
			concepts,
		)
	}
	t.Print()
	fmt.Printf("\n%s 共 %d 只%s\n", dateLabel, len(list), sideLabel(side))
}

// boardLabel 板别字符串到中文显示。
func boardLabel(b string) string {
	switch b {
	case "main":
		return "主板"
	case "growth":
		return "创业板"
	case "star":
		return "科创板"
	case "beijing":
		return "北交所"
	case "st":
		return "ST"
	default:
		return b
	}
}

// sideLabel 涨/跌停中文标签。
func sideLabel(s string) string {
	if s == "down" {
		return "跌停"
	}
	return "涨停"
}
