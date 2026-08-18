package main

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/dwh"
	"github.com/huijiecai/stock/astock/internal/model"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

func init() {
	rootCmd.AddCommand(newLiveCmd())
}

func newLiveCmd() *cobra.Command {
	liveCmd := &cobra.Command{
		Use:   "live",
		Short: "直连 TDX 查实时数据（不落库）",
	}

	quoteCmd := &cobra.Command{
		Use:   "quote <code> [code2...]",
		Short: "实时报价 + 五档盘口",
		Args:  cobra.MinimumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			// 拒绝板块/纯指数代码：GetQuotes 是股票实时报价接口，传入会被 AddPrefix 误判为股票并拉到错误数据。
			for _, c := range args {
				if tdx.IsBlockOrPureIndex(c) {
					return fmt.Errorf("%s 是板块/指数代码，无实时报价（请用 query kline --type index/block 查 K 线）", c)
				}
			}
			jsonOut := isJSON(cmd)
			tc := tdx.New()
			defer tc.Close()
			if err := requireRealtime(tc); err != nil {
				return err
			}

			quotes, err := tc.GetQuotes(args)
			if err != nil {
				return err
			}

			// 尽力而为补 name:TDX 报价协议不含股票名,从 securities 表补;
			// CH 不可用或查不到则留空,不影响行情。
			fillNames(quotes)

			if jsonOut {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(quotes)
			}

			for _, q := range quotes {
				title := q.Code
				if q.Name != "" {
					title = q.Code + " " + q.Name
				}
				fmt.Printf("---- %s ----\n", title)
				fmt.Printf("最新: %.2f  涨跌: %+.2f%%  开: %.2f  高: %.2f  低: %.2f\n",
					q.Price, q.ChangePct, q.Open, q.High, q.Low)
				fmt.Printf("成交量: %d  成交额: %.0f\n\n", q.Volume, q.Amount)
				t := newTable("挡位", 4, "价格", 10, "数量", 10)
				for i := 4; i >= 0; i-- {
					t.Row(fmt.Sprintf("卖%d", i+1),
						fmt.Sprintf("%.2f", q.Asks[i].Price),
						fmt.Sprintf("%d", q.Asks[i].Volume))
				}
				t.Row("----", "--------", "--------")
				for i := 0; i < 5; i++ {
					t.Row(fmt.Sprintf("买%d", i+1),
						fmt.Sprintf("%.2f", q.Bids[i].Price),
						fmt.Sprintf("%d", q.Bids[i].Volume))
				}
				t.Print()
				fmt.Println()
			}
			return nil
		},
	}
	liveCmd.AddCommand(quoteCmd)

	indexCmd := &cobra.Command{
		Use:   "index <code> [code2...]",
		Short: "实时指数报价 + 全市场涨跌家数",
		Args:  cobra.MinimumNArgs(1),
		RunE:  runLiveIndex,
	}
	liveCmd.AddCommand(indexCmd)

	tickCmd := &cobra.Command{
		Use:   "tick <code>",
		Short: "当日分笔成交（实时拉取，不落库）",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			if tdx.IsBlockOrPureIndex(args[0]) {
				return fmt.Errorf("%s 是板块/指数代码，无分笔成交数据", args[0])
			}
			last, _ := cmd.Flags().GetInt("last")
			jsonOut := isJSON(cmd)
			tc := tdx.New()
			defer tc.Close()
			if err := requireRealtime(tc); err != nil {
				return err
			}

			ticks, err := tc.GetTradeAll(args[0])
			if err != nil {
				return err
			}
			if last > 0 && len(ticks) > last {
				ticks = ticks[len(ticks)-last:]
			}

			if jsonOut {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(ticks)
			}

			t := newTable("时间", 10, "价格", 10, "成交量(手)", 10, "方向", 6, "单数", 6, "金额", 12)
			for _, tk := range ticks {
				t.Row(tk.Time,
					fmt.Sprintf("%.2f", tk.Price),
					fmt.Sprintf("%d", tk.Volume),
					tk.Side,
					fmt.Sprintf("%d", tk.OrderCount),
					fmt.Sprintf("%.0f", tk.Amount))
			}
			t.Print()
			fmt.Printf("\n共 %d 笔\n", len(ticks))
			return nil
		},
	}
	tickCmd.Flags().Int("last", 20, "只显示最后 N 笔")
	liveCmd.AddCommand(tickCmd)

	minuteCmd := &cobra.Command{
		Use:   "minute <code>",
		Short: "当日实时分时",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			jsonOut := isJSON(cmd)
			tc := tdx.New()
			defer tc.Close()
			if err := requireRealtime(tc); err != nil {
				return err
			}

			dataType := model.TypeStock
			// --type 显式指定优先；否则自动判断纯指数/板块代码
			typeFlag, _ := cmd.Flags().GetString("type")
			if typeFlag == "index" || typeFlag == "block" {
				dataType = model.TypeIndex
			} else if tdx.IsBlockOrPureIndex(args[0]) {
				dataType = model.TypeIndex
			}
			ticks, err := tc.GetMinute(args[0], dataType)
			if err != nil {
				return err
			}

			if jsonOut {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(ticks)
			}

			t := newTable("时间", 8, "价格", 10, "成交量(手)", 10)
			for _, tk := range ticks {
				t.Row(tk.Time,
					fmt.Sprintf("%.2f", tk.Price),
					fmt.Sprintf("%d", tk.Volume))
			}
			t.Print()
			fmt.Printf("\n共 %d 个时间点\n", len(ticks))
			return nil
		},
	}
	minuteCmd.Flags().String("type", "", "标的类型: stock(默认)/index/block；解决000001等代码歧义")
	liveCmd.AddCommand(minuteCmd)

	// live block rank / live block stocks（直拉 TDX 板块/成分股实时报价，不落库）
	addLiveBlockCmd(liveCmd)
	liveCmd.AddCommand(buildLiveMarketCmd())
	liveCmd.AddCommand(buildLiveGlobalCmd())

	return liveCmd
}

func requireRealtime(tc *tdx.Client) error {
	ok, reason, err := tc.IsRealtimeNow()
	if err != nil {
		return err
	}
	if !ok {
		return fmt.Errorf("拒绝：%s（历史数据请用 query/replay）", reason)
	}
	return nil
}

// fillNames 尽力而为地从 ClickHouse securities 表补全股票名称。
// TDX 实时报价协议本身不含 name;这里查 sync meta 预填的 securities 表。
// CH 不可用或查不到 → name 留空,不报错(行情照常输出)。
func fillNames(quotes []*model.Quote) {
	codes := make([]string, 0, len(quotes))
	for _, q := range quotes {
		if q.Name == "" {
			codes = append(codes, q.Code)
		}
	}
	if len(codes) == 0 {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()
	ch, err := dwh.New(ctx, cfg)
	if err != nil {
		return // CH 不可用,静默跳过
	}
	defer ch.Close()
	names, err := queryNames(ctx, ch, codes)
	if err != nil {
		return // 查询失败,静默跳过
	}
	for _, q := range quotes {
		if q.Name == "" {
			q.Name = names[q.Code]
		}
	}
}

// queryNames 批量从 securities 表查 code→name(一次 SQL)。
func queryNames(ctx context.Context, ch *dwh.Client, codes []string) (map[string]string, error) {
	quoted := make([]string, len(codes))
	for i, c := range codes {
		quoted[i] = "'" + c + "'"
	}
	query := fmt.Sprintf(`
SELECT code, name FROM %s.securities FINAL
WHERE type = 'stock' AND code IN (%s)`,
		ch.DB(), strings.Join(quoted, ","))
	rows, err := ch.Conn().Query(ctx, query)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	out := make(map[string]string)
	for rows.Next() {
		var code, name string
		if err := rows.Scan(&code, &name); err != nil {
			continue
		}
		out[code] = name
	}
	return out, nil
}
