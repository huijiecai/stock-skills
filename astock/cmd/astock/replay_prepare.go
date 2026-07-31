package main

import (
	"context"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/dwh"
	"github.com/huijiecai/stock/astock/internal/model"
	ssync "github.com/huijiecai/stock/astock/internal/sync"
)

// buildReplayPrepareCmd 构建 `astock replay prepare <date>` 命令。
//
// 统一同步一天 replay 所需的全部数据：
//  1. 6 个指数的 daily + 1m
//  2. 428 个板块的 daily + 1m
//  3. 全市场股票 daily（涨停判定 + 涨跌家数依赖）
//  4. 活跃股分钟线（最近3天涨停/跌停/炸板/大成交额 → 逐只 sync 1m）
//  5. 写 sync_log: task='replay_prepare', target=date
func buildReplayPrepareCmd() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "prepare <date>",
		Short: "同步一天 replay 所需的全部数据",
		Long: `统一同步一天 replay 所需的全部数据：

  1. 6 个指数（000001 等）的 daily + 1m
  2. 428 个板块（concept+style）的 daily + 1m
  3. 全市场股票 daily（涨停判定 + 涨跌家数）
  4. 活跃股分钟线（最近3天涨停/跌停/炸板/成交额>50亿 → 逐只 sync 1m）

TDX 分钟线窗口仅支持最近 ~3 个交易日；超出窗口的历史日期会跳过分钟同步。

示例：
  astock replay prepare 20260730`,
		Args: cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			date, err := parseReplayDate(args[0])
			if err != nil {
				return err
			}
			force, _ := cmd.Flags().GetBool("force")

			ctx, cancel := context.WithTimeout(context.Background(), 2*time.Hour)
			defer cancel()
			ch, tc, closeFn, err := openBoth(ctx)
			if err != nil {
				return err
			}
			defer closeFn()

			jsonOut := isJSON(cmd)
			progress := func(format string, args ...any) {
				if !jsonOut {
					fmt.Fprintf(os.Stderr, format+"\n", args...)
				}
			}

			// 判断日期是否在 TDX 1m 窗口内
			d, _ := time.Parse("20060102", date)
			canSync1m := true
			if d.Before(time.Now().AddDate(0, 0, -6)) {
				progress("⚠ %s 超出 TDX 1m 窗口（最近 ~3 交易日），跳过分钟线同步", formatDate(date))
				canSync1m = false
			}

			var summary []string

			// ---- 1. 指数 daily + 1m ----
			progress("━━ 1/4 指数 daily + 1m ━━")
			var idxDailyExist, idxMinuteExist uint64
			ch.Conn().QueryRow(ctx, fmt.Sprintf(
				"SELECT count() FROM %s.kline_daily WHERE type='index' AND trade_date=toDate('%s')",
				ch.DB(), formatDate(date))).Scan(&idxDailyExist)
			if canSync1m {
				ch.Conn().QueryRow(ctx, fmt.Sprintf(
					"SELECT count(DISTINCT code) FROM %s.kline_minute WHERE type='index' AND freq='1m' AND toDate(dt)=toDate('%s')",
					ch.DB(), formatDate(date))).Scan(&idxMinuteExist)
			}
			if !force && idxDailyExist > 0 && (idxMinuteExist > 0 || !canSync1m) {
				progress("  ✓ 指数 daily %d 行, 1m %d 只（已存在，跳过）", idxDailyExist, idxMinuteExist)
				summary = append(summary, fmt.Sprintf("指数: daily=%d 1m=%d只(跳过)", idxDailyExist, idxMinuteExist))
			} else {
				idxDaily, idxMinute := 0, 0
				for _, idx := range marketIndexCodes {
					n, err := ssync.Daily(ctx, ch, tc, idx.code, model.TypeIndex, false, 5, nil)
					if err != nil {
						progress("  ✗ %s daily: %v", idx.code, err)
					} else {
						idxDaily += n
					}
					if canSync1m {
						n, err = ssync.Minute(ctx, ch, tc, idx.code, model.TypeIndex, model.Freq1m, 800)
						if err != nil {
							progress("  ✗ %s 1m: %v", idx.code, err)
						} else {
							idxMinute += n
						}
					}
				}
				summary = append(summary, fmt.Sprintf("指数: daily=%d 1m=%d", idxDaily, idxMinute))
				progress("  ✓ 指数 daily %d 行, 1m %d 行", idxDaily, idxMinute)
			}

			// ---- 2. 板块 daily + 1m ----
			progress("━━ 2/4 板块 daily + 1m ━━")
			var blkDailyExist, blkMinuteExist uint64
			ch.Conn().QueryRow(ctx, fmt.Sprintf(
				"SELECT count() FROM %s.kline_daily WHERE type='block' AND trade_date=toDate('%s')",
				ch.DB(), formatDate(date))).Scan(&blkDailyExist)
			if canSync1m {
				ch.Conn().QueryRow(ctx, fmt.Sprintf(
					"SELECT count(DISTINCT code) FROM %s.kline_minute WHERE type='block' AND freq='1m' AND toDate(dt)=toDate('%s')",
					ch.DB(), formatDate(date))).Scan(&blkMinuteExist)
			}
			if !force && blkDailyExist > 0 && (blkMinuteExist > 0 || !canSync1m) {
				progress("  ✓ 板块 daily %d 行, 1m %d 只（已存在，跳过）", blkDailyExist, blkMinuteExist)
				summary = append(summary, fmt.Sprintf("板块: daily=%d 1m=%d只(跳过)", blkDailyExist, blkMinuteExist))
			} else {
				blockCodes, err := loadBlockCodes(ctx, ch)
				if err != nil {
					return fmt.Errorf("加载板块代码失败: %w", err)
				}
				blkDaily, blkMinute := 0, 0
				for i, code := range blockCodes {
					n, err := ssync.Daily(ctx, ch, tc, code, model.TypeBlock, false, 5, nil)
					if err != nil {
						if i < 3 {
							progress("  ✗ %s daily: %v", code, err)
						}
					} else {
						blkDaily += n
					}
					if canSync1m {
						n, err = ssync.Minute(ctx, ch, tc, code, model.TypeBlock, model.Freq1m, 800)
						if err != nil {
							if i < 3 {
								progress("  ✗ %s 1m: %v", code, err)
							}
						} else {
							blkMinute += n
						}
					}
					if !jsonOut && (i+1)%100 == 0 {
						progress("  [%d/%d] 板块同步中...", i+1, len(blockCodes))
					}
				}
				summary = append(summary, fmt.Sprintf("板块(%d只): daily=%d 1m=%d", len(blockCodes), blkDaily, blkMinute))
				progress("  ✓ 板块 %d 只: daily %d 行, 1m %d 行", len(blockCodes), blkDaily, blkMinute)
			}

			// ---- 3. 全市场股票 daily ----
			progress("━━ 3/4 全市场股票 daily ━━")
			var stockExist uint64
			ch.Conn().QueryRow(ctx,
				fmt.Sprintf("SELECT count() FROM %s.kline_daily WHERE type='stock' AND trade_date=toDate('%s')", ch.DB(), formatDate(date))).Scan(&stockExist)
			if !force && stockExist > 1000 {
				progress("  ✓ 股票 daily 已有 %d 行，跳过同步", stockExist)
				summary = append(summary, fmt.Sprintf("股票daily: 已有%d行(跳过)", stockExist))
			} else {
				progress("  → 同步全市场股票 daily...")
				n, err := ssync.Daily(ctx, ch, tc, "", model.TypeStock, true, 5, syncProgress)
				if err != nil {
					progress("  ✗ 股票 daily: %v", err)
				}
				summary = append(summary, fmt.Sprintf("股票daily: %d行", n))
				progress("  ✓ 股票 daily %d 行", n)
			}

			// ---- 4. 活跃股分钟线（涨停/跌停/炸板/大成交额，最近3天） ----
			progress("━━ 4/4 活跃股分钟线 ━━")
			minuteCodes, err := identifyReplayMinuteStocks(ctx, ch, date)
			if err != nil {
				progress("  ✗ 识别活跃股失败: %v", err)
				summary = append(summary, "活跃股1m: 识别失败")
			} else if len(minuteCodes) == 0 {
				progress("  ✓ 无活跃股")
				summary = append(summary, "活跃股1m: 无活跃股")
			} else {
				// 检查活跃股中已有多少只 1m 数据（精确匹配活跃股代码，不只比总数）
				var syncedCount uint64
				if canSync1m {
					quoted := make([]string, len(minuteCodes))
					for i, c := range minuteCodes {
						quoted[i] = fmt.Sprintf("'%s'", c)
					}
					ch.Conn().QueryRow(ctx, fmt.Sprintf(
						"SELECT count(DISTINCT code) FROM %s.kline_minute WHERE type='stock' AND freq='1m' AND toDate(dt)=toDate('%s') AND code IN (%s)",
						ch.DB(), formatDate(date), strings.Join(quoted, ","))).Scan(&syncedCount)
				}
				if !force && canSync1m && int(syncedCount) >= len(minuteCodes) {
					progress("  ✓ 活跃股 %d 只: 1m 已有 %d 只（已存在，跳过）", len(minuteCodes), syncedCount)
					summary = append(summary, fmt.Sprintf("活跃股(%d只)1m: 已有%d只(跳过)", len(minuteCodes), syncedCount))
				} else {
					progress("  活跃股 %d 只，同步 1m...", len(minuteCodes))
					stockMinute := 0
					for i, code := range minuteCodes {
						n, err := ssync.Minute(ctx, ch, tc, code, model.TypeStock, model.Freq1m, 800)
						if err != nil {
							progress("  ✗ %s 1m: %v", code, err)
						} else {
							stockMinute += n
						}
						if !jsonOut && (i+1)%50 == 0 {
							progress("  [%d/%d] 活跃股同步中...", i+1, len(minuteCodes))
						}
					}
					summary = append(summary, fmt.Sprintf("活跃股(%d只)1m=%d", len(minuteCodes), stockMinute))
					progress("  ✓ 活跃股 %d 只: 1m %d 行", len(minuteCodes), stockMinute)
				}
			}

			// ---- 5. 写 sync_log ----
			_ = ssync.WriteLog(ctx, ch, &ssync.LogEntry{
				Task:    "replay_prepare",
				Target:  date,
				StartAt: time.Now(),
				Rows:    0,
				Status:  "ok",
			})

			if jsonOut {
				fmt.Printf(`{"status":"ok","date":"%s","summary":["%s"]}`+"\n",
					date, strings.Join(summary, `","`))
			} else {
				progress("\n━━ replay prepare %s 完成 ━━", formatDate(date))
				for _, s := range summary {
					progress("  %s", s)
				}
			}
			return nil
		},
	}
	cmd.Flags().Bool("force", false, "强制重新同步（忽略已有数据）")
	return cmd
}

// loadBlockCodes 从 blocks 表拉取全部板块代码。
func loadBlockCodes(ctx context.Context, ch *dwh.Client) ([]string, error) {
	rows, err := ch.Conn().Query(ctx,
		fmt.Sprintf("SELECT code FROM %s.blocks FINAL ORDER BY code", ch.DB()))
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var codes []string
	for rows.Next() {
		var code string
		if err := rows.Scan(&code); err != nil {
			return nil, err
		}
		codes = append(codes, code)
	}
	return codes, nil
}

// identifyReplayMinuteStocks 筛选出最近3个交易日（含目标日）需要同步分钟线的活跃股票。
// 条件（满足任一即纳入）：
//   - 涨停：close = 涨停价 AND close = high
//   - 跌停：close = 跌停价 AND close = low
//   - 炸板：high = 涨停价 AND close < high（盘中触及涨停但未封住）
//   - 成交额 > 50亿
func identifyReplayMinuteStocks(ctx context.Context, ch *dwh.Client, date string) ([]string, error) {
	sql := fmt.Sprintf(`
WITH pct AS (
  SELECT k.code AS code, k.close AS close, k.pre_close AS pre_close,
         k.high AS high, k.low AS low, k.amount AS amount,
         multiIf(
           s.name LIKE '%%ST%%' OR s.name LIKE 'S%%ST%%', 0.05,
           k.code LIKE '688%%' OR k.code LIKE '689%%', 0.20,
           k.code LIKE '300%%' OR k.code LIKE '301%%', 0.20,
           k.code LIKE '43%%' OR k.code LIKE '83%%' OR k.code LIKE '87%%' OR k.code LIKE '88%%' OR k.code LIKE '920%%', 0.30,
           0.10
         ) AS pct_limit
  FROM %s.kline_daily AS k FINAL
  INNER JOIN %s.securities AS s FINAL ON k.code = s.code AND s.type = 'stock'
  WHERE k.type='stock'
    AND k.trade_date >= toDate('%s') - INTERVAL 5 DAY
    AND k.trade_date <= toDate('%s')
    AND k.pre_close > 0
)
SELECT DISTINCT code
FROM pct
WHERE
  -- 涨停
  (close = floor(pre_close * (1 + pct_limit) * 100 + 0.5) / 100 AND close = high)
  -- 跌停
  OR (close = floor(pre_close * (1 - pct_limit) * 100 + 0.5) / 100 AND close = low)
  -- 炸板（盘中触及涨停但收盘未封住）
  OR (high = floor(pre_close * (1 + pct_limit) * 100 + 0.5) / 100 AND close < high)
  -- 成交额 > 50亿（raw amount 单位为元）
  OR amount > 5000000000
ORDER BY code`, ch.DB(), ch.DB(), formatDate(date), formatDate(date))

	rows, err := ch.Conn().Query(ctx, sql)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var codes []string
	for rows.Next() {
		var code string
		if err := rows.Scan(&code); err != nil {
			return nil, err
		}
		codes = append(codes, code)
	}
	return codes, nil
}
