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

// addReplayBlockCmd 注册 replay block 子命令树。
func addReplayBlockCmd(replayCmd *cobra.Command) {
	blockCmd := &cobra.Command{
		Use:   "block",
		Short: "板块历史回放",
	}
	blockCmd.AddCommand(buildReplayBlockRankCmd())
	blockCmd.AddCommand(buildReplayBlockMembersCmd())
	replayCmd.AddCommand(blockCmd)
}

// buildReplayBlockRankCmd 构建 `astock replay block rank <date> [time]` 命令。
//
// 无 time：和 query block rank 一样，返回日线终值排名。
// 有 time：从板块分钟线重建指定时间点的排名。
//
// 分钟级排名的 SQL 改动：
//   - block_quote CTE 从 kline_minute 取 argMax(close, dt) 作为指定时间点的 close
//   - sum(amount) 累计到指定时间
//   - pre_close 仍从 kline_daily 取
//   - 成分股涨跌家数/涨停数仍用 kline_daily（日线终值，全市场分钟线数据量太大）
func buildReplayBlockRankCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "rank <date> [time]",
		Short: "板块涨幅排名（支持分钟级）",
		Long: `板块涨幅排名——支持按分钟重建。

无 time 参数返回日线终值排名（同 query block rank）。
有 time 参数（如 10:30）从板块分钟线重建该时间点的排名。

注意：成分股涨跌家数/涨停数始终是日线终值（全市场分钟线数据量太大）。

示例：
  astock replay block rank 20260730              # 收盘排名
  astock replay block rank 20260730 10:30         # 10:30 时排名
  astock replay block rank 20260730 10:30 --type concept --limit 50
  astock replay block rank 20260730 --json`,
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
			typeStr, _ := cmd.Flags().GetString("type")
			if typeStr != "all" && typeStr != "concept" && typeStr != "style" {
				return fmt.Errorf("--type 必须是 all/concept/style")
			}
			asc, _ := cmd.Flags().GetBool("asc")
			limit, _ := cmd.Flags().GetInt("limit")

			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			list, err := queryReplayBlockRank(ctx, ch, date, hhmmss, typeStr, asc, limit)
			if err != nil {
				return err
			}
			if len(list) == 0 {
				fmt.Fprintf(os.Stderr, "日期 %s 无板块数据（请先 replay prepare）\n", formatDate(date))
				return nil
			}

			if isJSON(cmd) {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(list)
			}

			label := "涨幅"
			if asc {
				label = "跌幅"
			}
			timeLabel := "收盘"
			if hhmmss != "" {
				timeLabel = timeStr
			}
			fmt.Fprintf(os.Stderr, "=== %s %s 板块%s榜 ===\n", formatDate(date), timeLabel, label)
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
			return nil
		},
	}
	cmd.Flags().String("type", "all", "板块类型: concept/style/all")
	cmd.Flags().Bool("asc", false, "升序（跌幅榜）")
	cmd.Flags().Int("limit", 50, "返回前 N（默认 50；0 表示不限制）")
	return cmd
}

// buildReplayBlockMembersCmd 构建 `astock replay block members <block_code> <date> [time]` 命令。
//
// 无 time：和 query block members 一样，返回日线终值成分股涨幅榜。
// 有 time：从个股分钟线重建指定时间点的成分股涨幅榜。
//
// 支持逗号分隔的多个板块代码，例如：
//
//	astock replay block members 880904,880952 20260730 10:30
//
// 分钟级成员股的 SQL 改动：
//   - member_minute CTE 从 kline_minute 取 argMax(close, dt) 作为指定时间点的 close
//   - member_daily CTE 从 kline_daily 取 pre_close/name/industry/pct_limit
//   - LEFT JOIN：有分钟数据的个股用分钟价，无分钟数据的回退到日线收盘价
//   - data_source 字段标明数据来源（"minute" 或 "daily"）
//
// 注意：replay prepare 仅同步涨停股分钟线，非涨停股无分钟数据，将回退到日线收盘价。
func buildReplayBlockMembersCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "members <block_code> <date> [time]",
		Short: "板块成分股（支持分钟级）",
		Long: `板块成分股清单 + 行情——支持按分钟重建。

无 time 参数返回日线终值（同 query block members）。
有 time 参数（如 10:30）从个股分钟线重建指定时间点的成分股涨幅榜。
支持逗号分隔的多个板块代码。

注意：replay prepare 仅同步涨停股分钟线，非涨停股将回退到日线收盘价（data_source 字段标明）。

示例：
  astock replay block members 880904 20260730              # 收盘成分股涨幅榜
  astock replay block members 880904 20260730 10:30         # 10:30 成分股涨幅榜
  astock replay block members 880904,880952 20260730 10:30  # 多板块
  astock replay block members 880904 20260730 10:30 --asc   # 跌幅排序
  astock replay block members 880904 20260730 --json`,
		Args: cobra.MinimumNArgs(2),
		RunE: func(cmd *cobra.Command, args []string) error {
			blockCodes := parseCodes(args[0])
			date, err := parseReplayDate(args[1])
			if err != nil {
				return err
			}
			timeStr := ""
			if len(args) >= 3 {
				timeStr = args[2]
			}
			hhmmss, err := parseReplayTime(timeStr)
			if err != nil {
				return err
			}
			asc, _ := cmd.Flags().GetBool("asc")

			ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			if isJSON(cmd) {
				// JSON 模式：合并所有板块的成分股
				var all []*BlockMemberRow
				for _, bc := range blockCodes {
					list, err := queryReplayBlockMembers(ctx, ch, bc, date, hhmmss, asc)
					if err != nil {
						fmt.Fprintf(os.Stderr, "  ✗ %s: %v\n", bc, err)
						continue
					}
					all = append(all, list...)
				}
				if len(all) == 0 {
					fmt.Fprintf(os.Stderr, "无成分股或板块代码不存在\n")
					return nil
				}
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(all)
			}

			// 文本模式：逐板块输出
			for _, bc := range blockCodes {
				list, err := queryReplayBlockMembers(ctx, ch, bc, date, hhmmss, asc)
				if err != nil {
					fmt.Fprintf(os.Stderr, "  ✗ %s: %v\n", bc, err)
					continue
				}
				if len(list) == 0 {
					fmt.Printf("%s: 无成分股或板块代码不存在\n", bc)
					continue
				}
				var blockName string
				_ = ch.Conn().QueryRow(ctx,
					fmt.Sprintf("SELECT name FROM %s.blocks FINAL WHERE code = '%s'", ch.DB(), bc)).Scan(&blockName)
				printBlockMembers(list, bc, blockName, formatDate(date), asc)
				fmt.Println()
			}
			return nil
		},
	}
	cmd.Flags().Bool("asc", false, "升序（跌幅榜）")
	return cmd
}

// queryReplayBlockMembers 查询板块成分股，支持分钟级。
// 复用 BlockMemberRow 结构（与 query block members 一致）。
// 当 hhmmss 非空时，从 kline_minute 取 argMax(close, dt) 重建指定时间点的价格。
// 当 hhmmss 为空时，委托给 queryBlockMembers（日线终值）。
func queryReplayBlockMembers(ctx context.Context, ch *dwh.Client, blockCode, date, hhmmss string, asc bool) ([]*BlockMemberRow, error) {
	if hhmmss == "" {
		// 无 time：委托给 query block members 的逻辑
		return queryBlockMembers(ctx, ch, blockCode, date, asc)
	}

	// 有 time：从分钟线重建
	order := "DESC"
	if asc {
		order = "ASC"
	}

	dateFormatted := formatDate(date)
	replayDT := replayDateTime(date, hhmmss)

	sql := fmt.Sprintf(`
WITH
  finance_latest AS (
    SELECT code, argMax(float_share, report_date) AS float_share
    FROM %[1]s.finance FINAL
    GROUP BY code
  ),
  member_minute AS (
    SELECT k.code AS code,
           argMax(k.close, k.dt) AS minute_close,
           sum(k.amount) AS minute_amount,
           sum(k.volume) AS minute_volume
    FROM %[1]s.kline_minute AS k
    WHERE k.type = 'stock' AND k.freq = '1m'
      AND toDate(k.dt) = toDate('%[2]s')
      AND k.dt <= toDateTime('%[3]s')
      AND k.code IN (SELECT stock_code FROM %[1]s.block_constituents FINAL WHERE block_code = '%[4]s')
    GROUP BY k.code
  ),
  member_daily AS (
    SELECT k.code AS code, k.close AS daily_close, k.pre_close AS pre_close,
           k.high AS high, k.low AS low, k.amount AS daily_amount, k.volume AS daily_volume,
           s.name AS name, s.industry AS industry,
           coalesce(f.float_share, 0) AS float_share,
           multiIf(
             s.name LIKE '%%ST%%' OR s.name LIKE 'S%%ST%%', 0.05,
             k.code LIKE '688%%' OR k.code LIKE '689%%', 0.20,
             k.code LIKE '300%%' OR k.code LIKE '301%%', 0.20,
             k.code LIKE '43%%' OR k.code LIKE '83%%' OR k.code LIKE '87%%' OR k.code LIKE '88%%' OR k.code LIKE '920%%', 0.30,
             0.10
           ) AS pct_limit
    FROM %[1]s.kline_daily AS k
    INNER JOIN %[1]s.securities AS s ON k.code = s.code AND s.type = 'stock'
    LEFT JOIN finance_latest AS f ON k.code = f.code
    WHERE k.type = 'stock' AND k.trade_date = toDate('%[2]s')
      AND k.code IN (SELECT stock_code FROM %[1]s.block_constituents FINAL WHERE block_code = '%[4]s')
  )
-- 无分钟数据的股票：close/amount/turnover 返回 0，change_pct 返回 0（不是 -100%%），
-- data_source 标为 'daily'，打印时显示为空。
SELECT md.code, md.name, md.industry,
       mm.minute_close AS close,
       md.pre_close,
       if(mm.code != '' AND md.pre_close > 0, (mm.minute_close - md.pre_close) / md.pre_close * 100, 0) AS change_pct,
       mm.minute_amount AS amount,
       if(md.float_share > 0 AND mm.code != '', mm.minute_volume * 10000.0 / md.float_share, 0) AS turnover_pct,
       multiIf(
         mm.code != '' AND mm.minute_close = floor(md.pre_close * (1 + md.pct_limit) * 100 + 0.5) / 100 AND md.pre_close > 0, '涨停',
         mm.code != '' AND mm.minute_close = floor(md.pre_close * (1 - md.pct_limit) * 100 + 0.5) / 100 AND md.pre_close > 0, '跌停',
         '-'
       ) AS limit_status,
       if(mm.code = '', 'daily', 'minute') AS data_source
FROM member_daily AS md
LEFT JOIN member_minute AS mm ON md.code = mm.code
ORDER BY if(mm.code = '', 1, 0) ASC, change_pct %[5]s`,
		ch.DB(), dateFormatted, replayDT, blockCode, order)

	rows, err := ch.Conn().Query(ctx, sql)
	if err != nil {
		return nil, fmt.Errorf("query replay block members: %w", err)
	}
	defer rows.Close()

	var list []*BlockMemberRow
	for rows.Next() {
		var r BlockMemberRow
		if err := rows.Scan(&r.Code, &r.Name, &r.Industry, &r.Close, &r.PreClose,
			&r.ChangePct, &r.Amount, &r.Turnover, &r.LimitStatus, &r.DataSource); err != nil {
			return nil, err
		}
		list = append(list, &r)
	}
	return list, nil
}

// queryReplayBlockRank 查询板块排名，支持分钟级。
// 复用 BlockRankRow 结构（与 query block rank 一致）。
// 当 hhmmss 非空时，block_quote CTE 从 kline_minute 取 argMax(close, dt)。
func queryReplayBlockRank(ctx context.Context, ch *dwh.Client, date, hhmmss, typeStr string, asc bool, limit int) ([]*BlockRankRow, error) {
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
	if limit <= 0 {
		limit = 10000
	}

	dateFormatted := formatDate(date)

	// block_quote CTE：无 time 用 daily，有 time 用 minute
	var blockQuoteCTE string
	if hhmmss == "" {
		// 日线终值（和 query block rank 一致）
		blockQuoteCTE = fmt.Sprintf(`
  block_quote AS (
    SELECT b.code AS code, b.name AS name, b.type AS block_type,
           kd.close AS close, kd.pre_close AS pre_close, kd.amount AS amount,
           if(kd.pre_close > 0, (kd.close - kd.pre_close) / kd.pre_close * 100, 0) AS change_pct
    FROM %s.blocks AS b FINAL
    INNER JOIN %s.kline_daily AS kd ON b.code = kd.code
    WHERE kd.type = 'block' AND kd.trade_date = toDate('%s') %s
  )`, ch.DB(), ch.DB(), dateFormatted, typeFilter)
	} else {
		// 分钟级：argMax(close, dt) 取指定时间点最后一根 bar 的 close
		blockQuoteCTE = fmt.Sprintf(`
  block_quote AS (
    SELECT b.code AS code, b.name AS name, b.type AS block_type,
           argMax(km.close, km.dt) AS close,
           kd.pre_close AS pre_close,
           sum(km.amount) AS amount,
           if(kd.pre_close > 0, (argMax(km.close, km.dt) - kd.pre_close) / kd.pre_close * 100, 0) AS change_pct
    FROM %s.blocks AS b FINAL
    INNER JOIN %s.kline_daily AS kd ON b.code = kd.code
      AND kd.type = 'block' AND kd.trade_date = toDate('%s')
    INNER JOIN %s.kline_minute AS km ON b.code = km.code
      AND km.type = 'block' AND km.freq = '1m'
      AND toDate(km.dt) = toDate('%s')
      AND km.dt <= toDateTime('%s')
    WHERE 1=1 %s
    GROUP BY b.code, b.name, b.type, kd.pre_close
  )`, ch.DB(), ch.DB(), dateFormatted,
			ch.DB(), dateFormatted, replayDateTime(date, hhmmss),
			typeFilter)
	}

	// stock_daily CTE：始终用日线终值（全市场分钟线数据量太大）
	stockDailyCTE := fmt.Sprintf(`
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
  )`, ch.DB(), ch.DB(), dateFormatted)

	memberStatsCTE := fmt.Sprintf(`
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
  )`, ch.DB())

	sql := fmt.Sprintf(`WITH
%s,
%s,
%s
SELECT bq.code, bq.name, bq.block_type, bq.close, bq.pre_close, bq.change_pct, bq.amount,
       coalesce(ms.stock_total, 0) AS stock_total,
       coalesce(ms.up_cnt, 0) AS up_cnt,
       coalesce(ms.down_cnt, 0) AS down_cnt,
       coalesce(ms.limit_up_cnt, 0) AS limit_up_cnt
FROM block_quote AS bq
LEFT JOIN member_stats AS ms ON bq.code = ms.block_code
ORDER BY bq.change_pct %s
LIMIT %d`,
		blockQuoteCTE, stockDailyCTE, memberStatsCTE,
		order, limit)

	rows, err := ch.Conn().Query(ctx, sql)
	if err != nil {
		return nil, fmt.Errorf("query replay block rank: %w", err)
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
