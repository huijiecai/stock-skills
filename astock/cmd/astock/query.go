package main

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"time"

	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/dwh"
)

func init() {
	rootCmd.AddCommand(newQueryCmd())
}

func newQueryCmd() *cobra.Command {
	queryCmd := &cobra.Command{
		Use:   "query",
		Short: "从 ClickHouse 仓库查询数据",
	}

	// --- query daily ---
	dailyCmd := &cobra.Command{
		Use:   "daily <code>",
		Short: "查询日 K 线（支持前复权 --adjust qfq）",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			code := args[0]
			from, _ := cmd.Flags().GetString("from")
			to, _ := cmd.Flags().GetString("to")
			adjust, _ := cmd.Flags().GetString("adjust")
			limit, _ := cmd.Flags().GetInt("limit")
			jsonOut := isJSON(cmd)

			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			bars, err := queryDaily(ctx, ch, code, from, to, limit)
			if err != nil {
				return err
			}
			if len(bars) == 0 {
				fmt.Println("无数据")
				return nil
			}

			// 前复权
			if adjust == "qfq" {
				xdxrs, err := queryXDXR(ctx, ch, code)
				if err != nil {
					return fmt.Errorf("query xdxr: %w", err)
				}
				applyQFQ(bars, xdxrs)
			}

			if jsonOut {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(bars)
			}

			// 表格输出
			t := newTable("日期", 12, "开盘", 8, "最高", 8, "最低", 8, "收盘", 8, "涨跌%", 8, "成交量", 10)
			for _, b := range bars {
				pct := 0.0
				if b.PreClose > 0 {
					pct = (b.Close - b.PreClose) / b.PreClose * 100
				}
				t.Row(b.TradeDate,
					fmt.Sprintf("%.2f", b.Open),
					fmt.Sprintf("%.2f", b.High),
					fmt.Sprintf("%.2f", b.Low),
					fmt.Sprintf("%.2f", b.Close),
					fmt.Sprintf("%+.2f%%", pct),
					fmt.Sprintf("%d", b.Volume))
			}
			t.Print()
			return nil
		},
	}
	dailyCmd.Flags().String("from", "", "起始日期 YYYYMMDD")
	dailyCmd.Flags().String("to", "", "结束日期 YYYYMMDD")
	dailyCmd.Flags().String("adjust", "qfq", "复权: qfq(前复权)/none(不复权)")
	dailyCmd.Flags().Int("limit", 30, "返回行数")
	queryCmd.AddCommand(dailyCmd)

	// --- query minute ---
	minuteCmd := &cobra.Command{
		Use:   "minute <code>",
		Short: "查询分钟 K 线",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			code := args[0]
			freq, _ := cmd.Flags().GetString("freq")
			date, _ := cmd.Flags().GetString("date")
			limit, _ := cmd.Flags().GetInt("limit")
			jsonOut := isJSON(cmd)

			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			where := fmt.Sprintf("code = '%s' AND freq = '%s'", code, freq)
			if date != "" {
				d, _ := time.Parse("20060102", date)
				where += fmt.Sprintf(" AND dt >= '%s' AND dt < '%s'",
					d.Format("2006-01-02"), d.AddDate(0, 0, 1).Format("2006-01-02"))
			}

			q := fmt.Sprintf(`SELECT dt, open, high, low, close, volume, amount
				FROM %s.kline_minute FINAL WHERE %s ORDER BY dt DESC LIMIT %d`, ch.DB(), where, limit)

			rows, err := ch.Conn().Query(ctx, q)
			if err != nil {
				return err
			}
			defer rows.Close()

			type minuteBar struct {
				Time   string  `json:"time"`
				Open   float64 `json:"open"`
				High   float64 `json:"high"`
				Low    float64 `json:"low"`
				Close  float64 `json:"close"`
				Volume uint64  `json:"volume"`
				Amount float64 `json:"amount"`
			}
			var bars []*minuteBar
			for rows.Next() {
				var b minuteBar
				var dt time.Time
				if err := rows.Scan(&dt, &b.Open, &b.High, &b.Low, &b.Close, &b.Volume, &b.Amount); err != nil {
					return err
				}
				b.Time = dt.Format("01-02 15:04")
				bars = append(bars, &b)
			}
			// 翻转为时间正序
			for i, j := 0, len(bars)-1; i < j; i, j = i+1, j-1 {
				bars[i], bars[j] = bars[j], bars[i]
			}

			if len(bars) == 0 {
				fmt.Println("无数据")
				return nil
			}

			if jsonOut {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(bars)
			}

			t := newTable("时间", 12, "开盘", 8, "最高", 8, "最低", 8, "收盘", 8, "成交量", 9)
			for _, b := range bars {
				t.Row(b.Time,
					fmt.Sprintf("%.2f", b.Open),
					fmt.Sprintf("%.2f", b.High),
					fmt.Sprintf("%.2f", b.Low),
					fmt.Sprintf("%.2f", b.Close),
					fmt.Sprintf("%d", b.Volume))
			}
			t.Print()
			fmt.Printf("\n共 %d 条\n", len(bars))
			return nil
		},
	}
	minuteCmd.Flags().String("freq", "1m", "频率: 1m/5m/15m/30m/60m")
	minuteCmd.Flags().String("date", "", "指定日期 YYYYMMDD（默认取最新）")
	minuteCmd.Flags().Int("limit", 240, "返回行数")
	queryCmd.AddCommand(minuteCmd)

	// --- query count ---
	queryCmd.AddCommand(&cobra.Command{
		Use:   "count <table>",
		Short: "查询某张表行数",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			var n uint64
			q := fmt.Sprintf(`SELECT count() FROM %s.%s`, ch.DB(), args[0])
			row := ch.Conn().QueryRow(ctx, q)
			if err := row.Scan(&n); err != nil {
				return err
			}
			fmt.Printf("%s: %d 行\n", args[0], n)
			return nil
		},
	})

	return queryCmd
}

// --- 内部数据结构 ---

type dailyBar struct {
	TradeDate string  `json:"trade_date"`
	Open      float64 `json:"open"`
	High      float64 `json:"high"`
	Low       float64 `json:"low"`
	Close     float64 `json:"close"`
	PreClose  float64 `json:"pre_close"`
	Volume    uint64  `json:"volume"`
	Amount    float64 `json:"amount"`
}

type xdxrRow struct {
	ExDate   time.Time
	Transfer float32 // 送转（每 10 股）
	Dividend float32 // 派息（每 10 股，元）
	Peigu    float32 // 配股比例
	Peigujia float32 // 配股价
}

func queryDaily(ctx context.Context, ch *dwh.Client, code, from, to string, limit int) ([]*dailyBar, error) {
	where := fmt.Sprintf("code = '%s'", code)
	if from != "" {
		d, _ := time.Parse("20060102", from)
		where += fmt.Sprintf(" AND trade_date >= '%s'", d.Format("2006-01-02"))
	}
	if to != "" {
		d, _ := time.Parse("20060102", to)
		where += fmt.Sprintf(" AND trade_date <= '%s'", d.Format("2006-01-02"))
	}

	q := fmt.Sprintf(`SELECT trade_date, open, high, low, close, pre_close, volume, amount
		FROM %s.kline_daily FINAL WHERE %s ORDER BY trade_date DESC LIMIT %d`, ch.DB(), where, limit)

	rows, err := ch.Conn().Query(ctx, q)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []*dailyBar
	for rows.Next() {
		var b dailyBar
		var td time.Time
		if err := rows.Scan(&td, &b.Open, &b.High, &b.Low, &b.Close, &b.PreClose, &b.Volume, &b.Amount); err != nil {
			return nil, err
		}
		b.TradeDate = td.Format("2006-01-02")
		out = append(out, &b)
	}
	// 翻转为时间正序（利于复权计算）
	for i, j := 0, len(out)-1; i < j; i, j = i+1, j-1 {
		out[i], out[j] = out[j], out[i]
	}
	return out, nil
}

func queryXDXR(ctx context.Context, ch *dwh.Client, code string) ([]*xdxrRow, error) {
	q := fmt.Sprintf(`SELECT ex_date, transfer, dividend, rights_ratio, rights_price
		FROM %s.xdxr FINAL WHERE code = '%s' ORDER BY ex_date`, ch.DB(), code)
	rows, err := ch.Conn().Query(ctx, q)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var out []*xdxrRow
	for rows.Next() {
		var r xdxrRow
		if err := rows.Scan(&r.ExDate, &r.Transfer, &r.Dividend, &r.Peigu, &r.Peigujia); err != nil {
			return nil, err
		}
		out = append(out, &r)
	}
	return out, nil
}

// applyQFQ 前复权算法：从最新一天往前累乘因子。
// 因子 = (10 + 送转 + 配股) / 10 的倒数，扣减分红和配股注入。
func applyQFQ(bars []*dailyBar, xdxrs []*xdxrRow) {
	if len(xdxrs) == 0 || len(bars) == 0 {
		return
	}
	// 构建 map: date → xdxr
	xmap := make(map[string]*xdxrRow, len(xdxrs))
	for _, x := range xdxrs {
		xmap[x.ExDate.Format("2006-01-02")] = x
	}

	// 从最后一天开始，factor = 1.0（当天是真实价格）
	factor := 1.0
	// 从尾到头遍历（时间正序：bars[0] 最早，bars[len-1] 最新）
	// 我们从尾向头计算：碰到除权日则更新 factor
	for i := len(bars) - 1; i >= 0; i-- {
		bars[i].Open = round2(bars[i].Open * factor)
		bars[i].High = round2(bars[i].High * factor)
		bars[i].Low = round2(bars[i].Low * factor)
		bars[i].Close = round2(bars[i].Close * factor)
		bars[i].PreClose = round2(bars[i].PreClose * factor)

		// 检查当天是否是除权日（除权日的价格本身已经是除权后价格，所以在此之前的需要乘新因子）
		if x, ok := xmap[bars[i].TradeDate]; ok {
			// m = (10 + 送转 + 配股) / 10
			m := (10 + float64(x.Transfer) + float64(x.Peigu)) / 10
			// c = (分红 - 配股*配股价) / 10  — 每股现金流出
			c := (float64(x.Dividend) - float64(x.Peigu)*float64(x.Peigujia)) / 10
			if m > 0 {
				factor *= 1 / m
				// 如果有现金分红，还需要扣除
				if c != 0 && bars[i].Close > 0 {
					factor *= (bars[i].Close*m - c) / (bars[i].Close * m)
				}
			}
		}
	}
}

func round2(f float64) float64 {
	return math.Round(f*100) / 100
}
