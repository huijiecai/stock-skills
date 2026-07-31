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

// addReplayLimitCmd 注册 replay limit 子命令树（limit + limit ladder）。
func addReplayLimitCmd(replayCmd *cobra.Command) {
	limitCmd := &cobra.Command{
		Use:   "limit",
		Short: "涨停清单回放",
	}
	limitCmd.AddCommand(buildReplayLimitListCmd())
	limitCmd.AddCommand(buildReplayLimitLadderCmd())
	replayCmd.AddCommand(limitCmd)
}

// ReplayLimitStock 涨停清单中的一只股票（带分钟级状态）。
type ReplayLimitStock struct {
	Code        string   `json:"code"`
	Name        string   `json:"name"`
	Industry    string   `json:"industry,omitempty"`
	Sector      string   `json:"sector,omitempty"`
	Business    string   `json:"business,omitempty"`
	Board       string   `json:"board"`
	PctLimit    float64  `json:"pct_limit"`
	DailyClose  float64  `json:"daily_close"`      // 收盘价
	LimitPrice  float64  `json:"limit_price"`      // 涨停价
	ChangePct   float64  `json:"change_pct"`       // 日线涨跌幅 %
	DailyAmount float64  `json:"daily_amount"`     // 全天成交额
	ConsecDays  int      `json:"consecutive_days"` // 连板数
	Concepts    []string `json:"concepts,omitempty"`
	// 分钟级 replay 字段（仅 replay time 模式有值）
	ReplayPrice   float64 `json:"replay_price,omitempty"`    // replay 时间点价格
	ReplayAmount  float64 `json:"replay_amount,omitempty"`   // 到 replay 时间累计成交额
	Status        string  `json:"status,omitempty"`          // sealed/broken/pending
	FirstSealTime string  `json:"first_seal_time,omitempty"` // 首次封板时间
}

// buildReplayLimitListCmd 构建 `astock replay limit <date> [time]` 命令。
func buildReplayLimitListCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "list <date> [time]",
		Short: "涨停清单（支持分钟级封板状态）",
		Long: `涨停清单——支持分钟级封板状态。

无 time 参数：返回日线终值涨停清单（同 query limit）。
有 time 参数：对每只涨停股查分钟线，标注到该时间点的状态：
  sealed  = 封板中（当前价=涨停价）
  broken  = 炸板（触过涨停但已跌破）
  pending = 未封（尚未到涨停价）

示例：
  astock replay limit 20260730               # 收盘涨停清单
  astock replay limit 20260730 10:30           # 10:30 时涨停状态
  astock replay limit 20260730 10:30 --json`,
		Args: cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			date, err := parseReplayDate(args[0])
			if err != nil {
				return err
			}
			timeStr := ""
			if len(args) >= 2 {
				timeStr = args[1]
			}
			hhmmss, err := parseReplayTime(timeStr)
			if err != nil {
				return err
			}
			excludeST, _ := cmd.Flags().GetBool("exclude-st")

			ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			if hhmmss == "" {
				// 无 time：复用 queryLimitList（日线终值）
				list, err := queryLimitList(ctx, ch, date, "up", excludeST)
				if err != nil {
					return err
				}
				if len(list) == 0 {
					fmt.Fprintf(os.Stderr, "日期 %s 无涨停股\n", formatDate(date))
					return nil
				}
				if isJSON(cmd) {
					enc := json.NewEncoder(os.Stdout)
					enc.SetIndent("", "  ")
					return enc.Encode(list)
				}
				printLimitTable(list, formatDate(date), "up")
				return nil
			}

			// 有 time：分钟级涨停状态
			list, err := queryReplayLimitList(ctx, ch, date, hhmmss, excludeST)
			if err != nil {
				return err
			}
			if len(list) == 0 {
				fmt.Fprintf(os.Stderr, "日期 %s 无涨停股\n", formatDate(date))
				return nil
			}

			if isJSON(cmd) {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(list)
			}
			printReplayLimitTable(list, formatDate(date), timeStr)
			return nil
		},
	}
	cmd.Flags().Bool("exclude-st", false, "排除 ST/*ST 股")
	return cmd
}

// queryReplayLimitList 查询分钟级涨停清单。
func queryReplayLimitList(ctx context.Context, ch *dwh.Client, date, hhmmss string, excludeST bool) ([]*ReplayLimitStock, error) {
	dateFormatted := formatDate(date)
	stFilter := ""
	if excludeST {
		stFilter = "AND s.name NOT LIKE '%ST%' AND s.name NOT LIKE 'S%ST%'"
	}

	sql := fmt.Sprintf(`
WITH limit_up_stocks AS (
  SELECT k.code AS code, k.pre_close AS pre_close, k.close AS daily_close,
         k.high AS high, k.amount AS daily_amount,
         s.name AS name, s.industry AS industry, s.sector AS sector, s.business AS business,
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
         ) AS pct_limit,
         floor(k.pre_close * (1 + pct_limit) * 100 + 0.5) / 100 AS limit_price
  FROM %s.kline_daily AS k FINAL
  INNER JOIN %s.securities AS s FINAL ON k.code = s.code AND s.type = 'stock'
  WHERE k.type='stock' AND k.trade_date = toDate('%s')
    AND k.close = floor(k.pre_close * (1 + pct_limit) * 100 + 0.5) / 100
    AND k.close = k.high AND k.pre_close > 0 %s
),
minute_joined AS (
  SELECT lus.code AS code, lus.name AS name, lus.industry AS industry,
         lus.sector AS sector, lus.business AS business, lus.board AS board,
         lus.pct_limit AS pct_limit, lus.pre_close AS pre_close,
         lus.daily_close AS daily_close, lus.limit_price AS limit_price,
         lus.daily_amount AS daily_amount,
         km.dt AS m_dt, km.close AS m_close, km.amount AS m_amount
  FROM limit_up_stocks AS lus
  LEFT JOIN %s.kline_minute AS km ON lus.code = km.code
    AND km.type = 'stock' AND km.freq = '1m'
    AND toDate(km.dt) = toDate('%s')
    AND km.dt <= toDateTime('%s')
)
SELECT code, name, industry, sector, business, board, pct_limit,
       daily_close, limit_price,
       (daily_close - pre_close) / pre_close * 100 AS change_pct,
       daily_amount,
       argMax(m_close, m_dt) AS replay_price,
       sum(m_amount) AS replay_amount,
       multiIf(
         argMax(m_close, m_dt) = limit_price, 'sealed',
         max(m_close) >= limit_price, 'broken',
         'pending'
       ) AS status,
       formatDateTime(minIf(m_dt, m_close >= limit_price), '%%H:%%i') AS first_seal_time
FROM minute_joined
GROUP BY code, name, industry, sector, business, board, pct_limit,
         pre_close, daily_close, limit_price, daily_amount
ORDER BY daily_amount DESC`,
		ch.DB(), ch.DB(), dateFormatted, stFilter,
		ch.DB(), dateFormatted, replayDateTime(date, hhmmss))

	rows, err := ch.Conn().Query(ctx, sql)
	if err != nil {
		return nil, fmt.Errorf("query replay limit list: %w", err)
	}
	defer rows.Close()

	var list []*ReplayLimitStock
	codeSet := make(map[string]*ReplayLimitStock)
	for rows.Next() {
		var s ReplayLimitStock
		var firstSealTime *string
		if err := rows.Scan(
			&s.Code, &s.Name, &s.Industry, &s.Sector, &s.Business,
			&s.Board, &s.PctLimit, &s.DailyClose, &s.LimitPrice,
			&s.ChangePct, &s.DailyAmount,
			&s.ReplayPrice, &s.ReplayAmount,
			&s.Status, &firstSealTime,
		); err != nil {
			return nil, err
		}
		s.ConsecDays = 1
		if firstSealTime != nil {
			s.FirstSealTime = *firstSealTime
		}
		if existing := codeSet[s.Code]; existing != nil {
			if s.DailyAmount > existing.DailyAmount {
				*existing = s
			}
			continue
		}
		list = append(list, &s)
		codeSet[s.Code] = &s
	}
	if len(list) == 0 {
		return list, nil
	}

	// 重建指针映射
	codeSet = make(map[string]*ReplayLimitStock, len(list))
	for _, p := range list {
		codeSet[p.Code] = p
	}

	// 填充连板数
	if err := fillReplayConsecDays(ctx, ch, list, date); err != nil {
		fmt.Fprintf(os.Stderr, "warning: 连板数查询失败: %v\n", err)
	}

	// 填充概念标签
	if err := fillReplayConcepts(ctx, ch, list, codeSet); err != nil {
		fmt.Fprintf(os.Stderr, "warning: 概念标签查询失败: %v\n", err)
	}

	return list, nil
}

// fillReplayConsecDays 复用 fillConsecutiveDays 的逻辑，适配 ReplayLimitStock。
func fillReplayConsecDays(ctx context.Context, ch *dwh.Client, list []*ReplayLimitStock, date string) error {
	// 转换为 []*LimitStock 复用现有逻辑
	limList := make([]*LimitStock, len(list))
	for i, s := range list {
		limList[i] = &LimitStock{
			Code: s.Code, Name: s.Name, Board: s.Board,
			Close: s.DailyClose, LimitPrice: s.LimitPrice,
			ChangePct: s.ChangePct, Amount: s.DailyAmount,
			ConsecDays: 1,
		}
	}
	codeSet := make(map[string]*LimitStock, len(limList))
	for _, p := range limList {
		codeSet[p.Code] = p
	}
	if err := fillConsecutiveDays(ctx, ch, limList, codeSet, date); err != nil {
		return err
	}
	for i, ls := range limList {
		list[i].ConsecDays = ls.ConsecDays
	}
	return nil
}

// fillReplayConcepts 复用 fillConcepts 的逻辑，适配 ReplayLimitStock。
func fillReplayConcepts(ctx context.Context, ch *dwh.Client, list []*ReplayLimitStock, codeSet map[string]*ReplayLimitStock) error {
	limList := make([]*LimitStock, len(list))
	for i, s := range list {
		limList[i] = &LimitStock{Code: s.Code}
	}
	limCodeSet := make(map[string]*LimitStock, len(limList))
	for _, p := range limList {
		limCodeSet[p.Code] = p
	}
	if err := fillConcepts(ctx, ch, limList, limCodeSet); err != nil {
		return err
	}
	for i, ls := range limList {
		list[i].Concepts = ls.Concepts
	}
	return nil
}

// printReplayLimitTable 分钟级涨停清单表格输出。
func printReplayLimitTable(list []*ReplayLimitStock, dateLabel, timeLabel string) {
	fmt.Fprintf(os.Stderr, "=== %s %s 涨停清单 ===\n", dateLabel, timeLabel)
	t := newTable(
		"代码", 6, "名称", 12, "板别", 6,
		"涨停价", 8, "当时价", 8, "涨跌%", 8,
		"成交额", 10, "连板", 4,
		"状态", 8, "首封", 6,
		"概念标签", 30,
	)
	for _, s := range list {
		concepts := strings.Join(s.Concepts, "/")
		t.Row(
			s.Code, s.Name, boardLabel(s.Board),
			fmt.Sprintf("%.2f", s.LimitPrice),
			fmt.Sprintf("%.2f", s.ReplayPrice),
			fmt.Sprintf("%+.2f%%", s.ChangePct),
			formatAmount(s.ReplayAmount),
			fmt.Sprintf("%d", s.ConsecDays),
			s.Status,
			s.FirstSealTime,
			concepts,
		)
	}
	t.Print()
	sealed := 0
	broken := 0
	pending := 0
	for _, s := range list {
		switch s.Status {
		case "sealed":
			sealed++
		case "broken":
			broken++
		case "pending":
			pending++
		}
	}
	fmt.Fprintf(os.Stderr, "\n共 %d 只（封板 %d / 炸板 %d / 未封 %d）\n",
		len(list), sealed, broken, pending)
}

// buildReplayLimitLadderCmd 构建 `astock replay limit ladder <date> [time]` 命令。
func buildReplayLimitLadderCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "ladder <date> [time]",
		Short: "连板天梯（支持分钟级，仅统计当时封板中的票）",
		Long: `连板天梯——支持分钟级。

无 time 参数：同 query limit ladder（日线终值）。
有 time 参数：仅统计到该时间点仍封板中（status=sealed）的票，按连板数分组。

示例：
  astock replay limit ladder 20260730             # 收盘天梯
  astock replay limit ladder 20260730 10:30         # 10:30 天梯
  astock replay limit ladder 20260730 10:30 --min-board 3 --json`,
		Args: cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			date, err := parseReplayDate(args[0])
			if err != nil {
				return err
			}
			timeStr := ""
			if len(args) >= 2 {
				timeStr = args[1]
			}
			hhmmss, err := parseReplayTime(timeStr)
			if err != nil {
				return err
			}
			minBoard, _ := cmd.Flags().GetInt("min-board")
			if minBoard < 1 {
				return fmt.Errorf("--min-board 必须 >= 1")
			}
			excludeST, _ := cmd.Flags().GetBool("exclude-st")

			ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			if hhmmss == "" {
				// 无 time：复用日线终值逻辑
				all, err := queryLimitList(ctx, ch, date, "up", excludeST)
				if err != nil {
					return err
				}
				filtered := make([]*LimitStock, 0, len(all))
				for _, s := range all {
					if s.ConsecDays >= minBoard {
						filtered = append(filtered, s)
					}
				}
				sort.Slice(filtered, func(i, j int) bool {
					if filtered[i].ConsecDays != filtered[j].ConsecDays {
						return filtered[i].ConsecDays > filtered[j].ConsecDays
					}
					return filtered[i].Amount > filtered[j].Amount
				})
				if len(filtered) == 0 {
					fmt.Fprintf(os.Stderr, "日期 %s 无 ≥%d 板涨停股\n", formatDate(date), minBoard)
					return nil
				}
				if isJSON(cmd) {
					enc := json.NewEncoder(os.Stdout)
					enc.SetIndent("", "  ")
					return enc.Encode(filtered)
				}
				printLimitLadder(filtered, formatDate(date), minBoard)
				return nil
			}

			// 有 time：分钟级，仅 sealed 的票
			all, err := queryReplayLimitList(ctx, ch, date, hhmmss, excludeST)
			if err != nil {
				return err
			}
			filtered := make([]*ReplayLimitStock, 0, len(all))
			for _, s := range all {
				if s.Status == "sealed" && s.ConsecDays >= minBoard {
					filtered = append(filtered, s)
				}
			}
			sort.Slice(filtered, func(i, j int) bool {
				if filtered[i].ConsecDays != filtered[j].ConsecDays {
					return filtered[i].ConsecDays > filtered[j].ConsecDays
				}
				return filtered[i].DailyAmount > filtered[j].DailyAmount
			})

			if len(filtered) == 0 {
				fmt.Fprintf(os.Stderr, "%s %s 无 ≥%d 板封板中涨停股\n",
					formatDate(date), timeStr, minBoard)
				return nil
			}

			if isJSON(cmd) {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(filtered)
			}
			printReplayLimitLadder(filtered, formatDate(date), timeStr, minBoard)
			return nil
		},
	}
	cmd.Flags().Int("min-board", 2, "最低连板数（默认 2）")
	cmd.Flags().Bool("exclude-st", false, "排除 ST/*ST 股")
	return cmd
}

// printReplayLimitLadder 分钟级连板天梯表格输出。
func printReplayLimitLadder(list []*ReplayLimitStock, dateLabel, timeLabel string, minBoard int) {
	fmt.Fprintf(os.Stderr, "=== %s %s 连板天梯（≥%d 板，仅封板中） ===\n\n",
		dateLabel, timeLabel, minBoard)

	type group struct {
		consec int
		stocks []*ReplayLimitStock
	}
	var groups []group
	cur := group{consec: list[0].ConsecDays}
	for _, s := range list {
		if s.ConsecDays != cur.consec {
			groups = append(groups, cur)
			cur = group{consec: s.ConsecDays}
		}
		cur.stocks = append(cur.stocks, s)
	}
	groups = append(groups, cur)

	for _, g := range groups {
		fmt.Fprintf(os.Stderr, "━━ %d 板（%d 只） ━━\n", g.consec, len(g.stocks))
		t := newTable(
			"代码", 6, "名称", 12, "板别", 6,
			"涨停价", 8, "当时价", 8, "成交额", 10,
			"连板", 4, "首封", 6, "概念标签", 30,
		)
		for _, s := range g.stocks {
			concepts := strings.Join(s.Concepts, "/")
			t.Row(
				s.Code, s.Name, boardLabel(s.Board),
				fmt.Sprintf("%.2f", s.LimitPrice),
				fmt.Sprintf("%.2f", s.ReplayPrice),
				formatAmount(s.ReplayAmount),
				fmt.Sprintf("%d", s.ConsecDays),
				s.FirstSealTime,
				concepts,
			)
		}
		t.Print()
		fmt.Fprintln(os.Stderr)
	}
	fmt.Fprintf(os.Stderr, "共 %d 只 ≥%d 板（封板中）\n", len(list), minBoard)
}
