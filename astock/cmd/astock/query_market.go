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

// addMarketCmd 注册 query market 子命令——市场全景快照（按日聚合派生）。
//
// 数据源：astock.kline_daily JOIN astock.securities，纯 ClickHouse SQL 派生，
// 不依赖任何 TDX 通道，不打破单源原则。
//
// 板别涨跌停规则（A 股 2026 现行版）：
//   - 主板：60xxxx / 00xxxx / 001xxx / 002xxx / 003xxx / 605xxx → ±10%
//   - 创业板：30xxxx / 301xxx → ±20%
//   - 科创板：688xxx / 689xxx → ±20%
//   - 北交所：43xxxx / 83xxxx / 87xxxx / 88xxxx / 920xxx → ±30%
//   - ST 股（name 含 'ST'）：覆盖板别为 ±5%
//
// 涨停判定：close = 涨停价 AND close = high，
// 涨停价采用 A 股交易所规则：四舍五入到分（round-half-up），
// 用 floor(x*100+0.5)/100 实现，避免 ClickHouse round() 的银行家舍入误判。
func addMarketCmd(queryCmd *cobra.Command) {
	marketCmd := &cobra.Command{
		Use:   "market [date]",
		Short: "市场全景快照（涨跌家数/涨停数/跌停数/板别成交额）",
		Long: `市场全景快照——按日 1 行的市场情绪派生指标。

date 可选，格式 YYYYMMDD；省略则取 kline_daily 中最新交易日。

示例：
  astock query market 20260612
  astock query market               # 最近交易日
  astock query market --exclude-st  # 排除 ST 股
  astock query market --json        # JSON 输出供 AI/脚本消费`,
		Args: cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			excludeST, _ := cmd.Flags().GetBool("exclude-st")
			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			// 解析日期：未指定则取 kline_daily 最新交易日
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

			snap, err := queryMarketSnapshot(ctx, ch, date, excludeST)
			if err != nil {
				return err
			}
			if snap.TotalStocks == 0 {
				fmt.Printf("日期 %s 无 daily 数据（可能非交易日或未同步）\n", date)
				return nil
			}

			if isJSON(cmd) {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(snap)
			}
			printMarketTable(snap)
			return nil
		},
	}
	marketCmd.Flags().Bool("exclude-st", false, "排除 ST/*ST 股")
	queryCmd.AddCommand(marketCmd)
}

// MarketSnapshot 市场全景快照（一日一行）。
type MarketSnapshot struct {
	Date          string  `json:"date"`
	TotalStocks   uint64  `json:"total_stocks"`        // 当日有 daily 数据的股票数
	UpCount       uint64  `json:"up_count"`            // 涨家数
	DownCount     uint64  `json:"down_count"`          // 跌家数
	FlatCount     uint64  `json:"flat_count"`          // 平家数
	LimitUpCount  uint64  `json:"limit_up_count"`      // 涨停数
	LimitDownCnt  uint64  `json:"limit_down_count"`    // 跌停数
	TotalAmount   float64 `json:"total_amount"`        // 全市场成交额（元）
	MainAmount    float64 `json:"main_board_amount"`   // 主板（沪深主板，含中小板）
	GrowthAmount  float64 `json:"growth_board_amount"` // 创业板
	StarAmount    float64 `json:"star_board_amount"`   // 科创板
	BeijingAmount float64 `json:"beijing_amount"`      // 北交所
}

// queryMarketSnapshot 从 ClickHouse 派生市场全景快照。
//
// 涨跌停规则按板别 + ST 状态分桶；查询时一次扫描 kline_daily JOIN securities。
// 涨/跌停价采用 round-half-up（floor(x*100+0.5)/100），避免 ClickHouse 银行家舍入。
func queryMarketSnapshot(ctx context.Context, ch *dwh.Client, date string, excludeST bool) (*MarketSnapshot, error) {
	stFilter := ""
	if excludeST {
		// stFilter 作为 %s 占位符传入 fmt.Sprintf，不会二次格式化，用单 %
		stFilter = "AND s.name NOT LIKE '%ST%' AND s.name NOT LIKE 'S%ST%'"
	}
	// 通过日期过滤 + 板别 CASE 表达式一次性聚合。
	// 涨幅上限 limit = CASE 板别（兼顾 ST 覆写）；涨停判定 round(pre_close * (1+limit), 2) = close。
	sql := fmt.Sprintf(`
WITH joined AS (
  SELECT
    k.code AS code,
    k.close AS close,
    k.pre_close AS pre_close,
    k.high AS high,
    k.low AS low,
    k.amount AS amount,
    s.name AS name,
    -- 板别分桶：返回字符串便于后续 group/统计
    multiIf(
      s.name LIKE '%%ST%%' OR s.name LIKE 'S%%ST%%', 'st',
      k.code LIKE '688%%' OR k.code LIKE '689%%', 'star',
      k.code LIKE '300%%' OR k.code LIKE '301%%', 'growth',
      k.code LIKE '43%%' OR k.code LIKE '83%%' OR k.code LIKE '87%%' OR k.code LIKE '88%%' OR k.code LIKE '920%%', 'beijing',
      'main'
    ) AS board,
    -- 涨幅上限（小数）
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
SELECT
  count() AS total,
  countIf(close > pre_close) AS up,
  countIf(close < pre_close) AS down,
  countIf(close = pre_close) AS flat,
  countIf(close = floor(pre_close * (1 + pct_limit) * 100 + 0.5) / 100 AND close = high AND pre_close > 0) AS lu,
  countIf(close = floor(pre_close * (1 - pct_limit) * 100 + 0.5) / 100 AND close = low  AND pre_close > 0) AS ld,
  sum(amount) AS amt_all,
  sumIf(amount, board='main')    AS amt_main,
  sumIf(amount, board='growth')  AS amt_growth,
  sumIf(amount, board='star')    AS amt_star,
  sumIf(amount, board='beijing') AS amt_beijing
FROM joined`, ch.DB(), ch.DB(), formatDate(date), stFilter)

	var snap MarketSnapshot
	snap.Date = formatDate(date)
	row := ch.Conn().QueryRow(ctx, sql)
	if err := row.Scan(
		&snap.TotalStocks, &snap.UpCount, &snap.DownCount, &snap.FlatCount,
		&snap.LimitUpCount, &snap.LimitDownCnt,
		&snap.TotalAmount, &snap.MainAmount, &snap.GrowthAmount, &snap.StarAmount, &snap.BeijingAmount,
	); err != nil {
		return nil, fmt.Errorf("query market snapshot: %w", err)
	}
	return &snap, nil
}

// printMarketTable 中文双列表格输出（指标 / 数值）。
func printMarketTable(s *MarketSnapshot) {
	t := newTable("日期", 12, "指标", 14, "数值", 16)
	t.Row(s.Date, "全市场只数", fmt.Sprintf("%d", s.TotalStocks))
	t.Row(s.Date, "涨家数", fmt.Sprintf("%d", s.UpCount))
	t.Row(s.Date, "跌家数", fmt.Sprintf("%d", s.DownCount))
	t.Row(s.Date, "平家数", fmt.Sprintf("%d", s.FlatCount))
	t.Row(s.Date, "涨停数", fmt.Sprintf("%d", s.LimitUpCount))
	t.Row(s.Date, "跌停数", fmt.Sprintf("%d", s.LimitDownCnt))
	t.Row(s.Date, "全市场成交额", formatAmount(s.TotalAmount))
	t.Row(s.Date, "主板成交额", formatAmount(s.MainAmount))
	t.Row(s.Date, "创业板成交额", formatAmount(s.GrowthAmount))
	t.Row(s.Date, "科创板成交额", formatAmount(s.StarAmount))
	t.Row(s.Date, "北交所成交额", formatAmount(s.BeijingAmount))
	t.Print()
}

// formatDate 把 YYYYMMDD 格式化为 YYYY-MM-DD（CH 表达式用）。
func formatDate(yyyymmdd string) string {
	if len(yyyymmdd) == 8 {
		return yyyymmdd[0:4] + "-" + yyyymmdd[4:6] + "-" + yyyymmdd[6:8]
	}
	return yyyymmdd
}

// formatAmount 把成交额（元）格式化为人类可读字符串。
//   - ≥ 1 万亿：x.xx万亿
//   - ≥ 1 亿：x.xx亿
//   - ≥ 1 万：x.xx万
//   - 否则：原值
func formatAmount(v float64) string {
	abs := v
	if abs < 0 {
		abs = -abs
	}
	switch {
	case abs >= 1e12:
		return fmt.Sprintf("%.2f万亿", v/1e12)
	case abs >= 1e8:
		return fmt.Sprintf("%.2f亿", v/1e8)
	case abs >= 1e4:
		return fmt.Sprintf("%.2f万", v/1e4)
	default:
		return fmt.Sprintf("%.0f", v)
	}
}
