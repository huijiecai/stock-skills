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
	"github.com/huijiecai/stock/astock/internal/model"
	ssync "github.com/huijiecai/stock/astock/internal/sync"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

func init() {
	rootCmd.AddCommand(newQueryCmd())
}

// autoSyncOnEmpty 本地查不到数据时自动触发 TDX 同步。
// kind: daily/minute/info/finance/xdxr。返回 true 表示调用方需重查。
func autoSyncOnEmpty(ctx context.Context, ch *dwh.Client, kind, code, freq string) bool {
	fmt.Printf("⚠ 本地无 %s 数据，自动 sync %s %s...\n", kind, kind, code)
	tc := tdx.New()
	defer tc.Close()
	var err error
	switch kind {
	case "daily":
		_, err = ssync.Daily(ctx, ch, tc, code, false, 800)
	case "minute":
		_, err = ssync.Minute(ctx, ch, tc, code, model.Freq(freq), 800)
	case "info":
		_, err = ssync.Info(ctx, ch, tc, code, false, nil)
	case "finance":
		_, err = ssync.Finance(ctx, ch, tc, code, false)
	case "xdxr":
		_, err = ssync.XDXR(ctx, ch, tc, code, false)
	default:
		return false
	}
	if err != nil {
		fmt.Printf("✗ sync 失败: %v\n", err)
		return false
	}
	fmt.Printf("✓ sync 完成，重新查询...\n\n")
	return true
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
			noSync, _ := cmd.Flags().GetBool("no-sync")
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
				if noSync || !autoSyncOnEmpty(ctx, ch, "daily", code, "") {
					fmt.Println("无数据")
					return nil
				}
				bars, err = queryDaily(ctx, ch, code, from, to, limit)
				if err != nil {
					return err
				}
				if len(bars) == 0 {
					fmt.Println("无数据")
					return nil
				}
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
	dailyCmd.Flags().Bool("no-sync", false, "本地无数据时不自动触发 sync")
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
			noSync, _ := cmd.Flags().GetBool("no-sync")
			jsonOut := isJSON(cmd)

			ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			type minuteBar struct {
				Time   string  `json:"time"`
				Open   float64 `json:"open"`
				High   float64 `json:"high"`
				Low    float64 `json:"low"`
				Close  float64 `json:"close"`
				Volume uint64  `json:"volume"`
				Amount float64 `json:"amount"`
			}
			doQuery := func() ([]*minuteBar, error) {
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
					return nil, err
				}
				defer rows.Close()
				var bars []*minuteBar
				for rows.Next() {
					var b minuteBar
					var dt time.Time
					if err := rows.Scan(&dt, &b.Open, &b.High, &b.Low, &b.Close, &b.Volume, &b.Amount); err != nil {
						return nil, err
					}
					b.Time = dt.Format("01-02 15:04")
					bars = append(bars, &b)
				}
				// 翻转为时间正序
				for i, j := 0, len(bars)-1; i < j; i, j = i+1, j-1 {
					bars[i], bars[j] = bars[j], bars[i]
				}
				return bars, nil
			}

			bars, err := doQuery()
			if err != nil {
				return err
			}
			if len(bars) == 0 {
				if noSync || !autoSyncOnEmpty(ctx, ch, "minute", code, freq) {
					fmt.Println("无数据")
					return nil
				}
				bars, err = doQuery()
				if err != nil {
					return err
				}
				if len(bars) == 0 {
					fmt.Println("无数据")
					return nil
				}
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
	minuteCmd.Flags().Bool("no-sync", false, "本地无数据时不自动触发 sync")
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

	// --- query stock ---
	stockCmd := &cobra.Command{
		Use:   "stock",
		Short: "查询标的列表（股票/指数/ETF）",
		RunE: func(cmd *cobra.Command, args []string) error {
			typ, _ := cmd.Flags().GetString("type")
			market, _ := cmd.Flags().GetString("market")
			industry, _ := cmd.Flags().GetString("industry")
			keyword, _ := cmd.Flags().GetString("keyword")
			limit, _ := cmd.Flags().GetInt("limit")
			jsonOut := isJSON(cmd)

			ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			where := "1=1"
			if typ != "" {
				where += fmt.Sprintf(" AND type = '%s'", typ)
			}
			if market != "" {
				where += fmt.Sprintf(" AND market = '%s'", market)
			}
			if industry != "" {
				where += fmt.Sprintf(" AND industry LIKE '%%%s%%'", industry)
			}
			if keyword != "" {
				where += fmt.Sprintf(" AND (name LIKE '%%%s%%' OR code LIKE '%%%s%%')", keyword, keyword)
			}

			q := fmt.Sprintf(`SELECT code, name, market, type, industry
				FROM %s.securities FINAL WHERE %s ORDER BY code LIMIT %d`, ch.DB(), where, limit)

			rows, err := ch.Conn().Query(ctx, q)
			if err != nil {
				return err
			}
			defer rows.Close()

			type secRow struct {
				Code     string `json:"code"`
				Name     string `json:"name"`
				Market   string `json:"market"`
				Type     string `json:"type"`
				Industry string `json:"industry"`
			}
			var list []*secRow
			for rows.Next() {
				var r secRow
				if err := rows.Scan(&r.Code, &r.Name, &r.Market, &r.Type, &r.Industry); err != nil {
					return err
				}
				list = append(list, &r)
			}
			if len(list) == 0 {
				fmt.Println("无匹配结果")
				return nil
			}

			if jsonOut {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(list)
			}

			t := newTable("代码", 8, "名称", 12, "市场", 4, "类型", 6, "行业", 12)
			for _, r := range list {
				t.Row(r.Code, r.Name, r.Market, r.Type, r.Industry)
			}
			t.Print()
			fmt.Printf("\n共 %d 条\n", len(list))
			return nil
		},
	}
	stockCmd.Flags().String("type", "stock", "标的类型: stock/index/etf")
	stockCmd.Flags().String("market", "", "市场: sh/sz/bj")
	stockCmd.Flags().String("industry", "", "行业关键字（模糊匹配）")
	stockCmd.Flags().String("keyword", "", "名称或代码关键字")
	stockCmd.Flags().Int("limit", 50, "返回条数")
	queryCmd.AddCommand(stockCmd)

	// --- query block ---
	blockCmd := &cobra.Command{
		Use:   "block",
		Short: "查询板块列表及成分股",
	}

	blockListCmd := &cobra.Command{
		Use:   "list",
		Short: "列出概念/行业板块",
		RunE: func(cmd *cobra.Command, args []string) error {
			keyword, _ := cmd.Flags().GetString("keyword")
			limit, _ := cmd.Flags().GetInt("limit")
			jsonOut := isJSON(cmd)

			ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			where := "1=1"
			if keyword != "" {
				where += fmt.Sprintf(" AND (name LIKE '%%%s%%' OR code LIKE '%%%s%%')", keyword, keyword)
			}

			q := fmt.Sprintf(`SELECT code, name, type, stock_count
				FROM %s.blocks FINAL WHERE %s ORDER BY stock_count DESC LIMIT %d`, ch.DB(), where, limit)

			rows, err := ch.Conn().Query(ctx, q)
			if err != nil {
				return err
			}
			defer rows.Close()

			type blockRow struct {
				Code       string `json:"code"`
				Name       string `json:"name"`
				Type       string `json:"type"`
				StockCount uint32 `json:"stock_count"`
			}
			var list []*blockRow
			for rows.Next() {
				var r blockRow
				if err := rows.Scan(&r.Code, &r.Name, &r.Type, &r.StockCount); err != nil {
					return err
				}
				list = append(list, &r)
			}
			if len(list) == 0 {
				fmt.Println("无匹配结果")
				return nil
			}

			if jsonOut {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(list)
			}

			t := newTable("代码", 8, "名称", 14, "类型", 8, "成分股数", 8)
			for _, r := range list {
				t.Row(r.Code, r.Name, r.Type, fmt.Sprintf("%d", r.StockCount))
			}
			t.Print()
			fmt.Printf("\n共 %d 个板块\n", len(list))
			return nil
		},
	}
	blockListCmd.Flags().String("keyword", "", "板块名称关键字")
	blockListCmd.Flags().Int("limit", 50, "返回条数")
	blockCmd.AddCommand(blockListCmd)

	blockMembersCmd := &cobra.Command{
		Use:   "members <block_code>",
		Short: "查询板块成分股",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			blockCode := args[0]
			jsonOut := isJSON(cmd)

			ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			q := fmt.Sprintf(`SELECT bc.stock_code, s.name, s.industry
				FROM %s.block_constituents AS bc
				LEFT JOIN %s.securities AS s ON bc.stock_code = s.code AND s.type = 'stock'
				WHERE bc.block_code = '%s'
				ORDER BY bc.stock_code`, ch.DB(), ch.DB(), blockCode)

			rows, err := ch.Conn().Query(ctx, q)
			if err != nil {
				return err
			}
			defer rows.Close()

			type memberRow struct {
				Code     string `json:"code"`
				Name     string `json:"name"`
				Industry string `json:"industry"`
			}
			var list []*memberRow
			for rows.Next() {
				var r memberRow
				if err := rows.Scan(&r.Code, &r.Name, &r.Industry); err != nil {
					return err
				}
				list = append(list, &r)
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

			t := newTable("代码", 8, "名称", 12, "行业", 14)
			for _, r := range list {
				t.Row(r.Code, r.Name, r.Industry)
			}
			t.Print()
			fmt.Printf("\n共 %d 只成分股\n", len(list))
			return nil
		},
	}
	blockCmd.AddCommand(blockMembersCmd)
	queryCmd.AddCommand(blockCmd)

	// --- query finance ---
	financeCmd := &cobra.Command{
		Use:   "finance <code>",
		Short: "查询财务数据",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			code := args[0]
			noSync, _ := cmd.Flags().GetBool("no-sync")
			jsonOut := isJSON(cmd)

			ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			type finRow struct {
				Code           string  `json:"code"`
				ReportDate     string  `json:"report_date"`
				Revenue        float64 `json:"revenue"`
				NetProfit      float64 `json:"net_profit"`
				EPS            float32 `json:"eps"`
				BPS            float32 `json:"bps"`
				ROE            float32 `json:"roe"`
				TotalShare     uint64  `json:"total_share"`
				FloatShare     uint64  `json:"float_share"`
				TotalAssets    float64 `json:"total_assets"`
				TotalLiability float64 `json:"total_liability"`
			}
			doQuery := func() ([]*finRow, error) {
				q := fmt.Sprintf(`SELECT code, report_date, revenue, net_profit, eps, bps, roe,
					total_share, float_share, total_assets, total_liability
					FROM %s.finance FINAL WHERE code = '%s' ORDER BY report_date DESC LIMIT 10`, ch.DB(), code)
				rows, err := ch.Conn().Query(ctx, q)
				if err != nil {
					return nil, err
				}
				defer rows.Close()
				var list []*finRow
				for rows.Next() {
					var r finRow
					var rd time.Time
					if err := rows.Scan(&r.Code, &rd, &r.Revenue, &r.NetProfit, &r.EPS, &r.BPS, &r.ROE,
						&r.TotalShare, &r.FloatShare, &r.TotalAssets, &r.TotalLiability); err != nil {
						return nil, err
					}
					r.ReportDate = rd.Format("2006-01-02")
					list = append(list, &r)
				}
				return list, nil
			}

			list, err := doQuery()
			if err != nil {
				return err
			}
			if len(list) == 0 {
				if noSync || !autoSyncOnEmpty(ctx, ch, "finance", code, "") {
					fmt.Println("无财务数据")
					return nil
				}
				list, err = doQuery()
				if err != nil {
					return err
				}
				if len(list) == 0 {
					fmt.Println("无财务数据")
					return nil
				}
			}

			if jsonOut {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(list)
			}

			t := newTable("报告期", 12, "营收(万)", 12, "净利润(万)", 12, "总股本(万)", 10, "流通股(万)", 10, "总资产(万)", 12)
			for _, r := range list {
				t.Row(r.ReportDate,
					fmt.Sprintf("%.0f", r.Revenue/10000),
					fmt.Sprintf("%.0f", r.NetProfit/10000),
					fmt.Sprintf("%d", r.TotalShare/10000),
					fmt.Sprintf("%d", r.FloatShare/10000),
					fmt.Sprintf("%.0f", r.TotalAssets/10000))
			}
			t.Print()
			return nil
		},
	}
	financeCmd.Flags().Bool("no-sync", false, "本地无数据时不自动触发 sync")
	queryCmd.AddCommand(financeCmd)

	// --- query xdxr ---
	xdxrCmd := &cobra.Command{
		Use:   "xdxr <code>",
		Short: "查询除权除息记录",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			code := args[0]
			noSync, _ := cmd.Flags().GetBool("no-sync")
			jsonOut := isJSON(cmd)

			ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			type xRow struct {
				Code        string  `json:"code"`
				ExDate      string  `json:"ex_date"`
				Type        string  `json:"type"`
				Bonus       float32 `json:"bonus"`
				Transfer    float32 `json:"transfer"`
				Dividend    float32 `json:"dividend"`
				RightsPrice float32 `json:"rights_price"`
				RightsRatio float32 `json:"rights_ratio"`
			}
			doQuery := func() ([]*xRow, error) {
				q := fmt.Sprintf(`SELECT code, ex_date, type, bonus, transfer, dividend, rights_price, rights_ratio
					FROM %s.xdxr FINAL WHERE code = '%s' ORDER BY ex_date DESC`, ch.DB(), code)
				rows, err := ch.Conn().Query(ctx, q)
				if err != nil {
					return nil, err
				}
				defer rows.Close()
				var list []*xRow
				for rows.Next() {
					var r xRow
					var ed time.Time
					if err := rows.Scan(&r.Code, &ed, &r.Type, &r.Bonus, &r.Transfer, &r.Dividend, &r.RightsPrice, &r.RightsRatio); err != nil {
						return nil, err
					}
					r.ExDate = ed.Format("2006-01-02")
					list = append(list, &r)
				}
				return list, nil
			}

			list, err := doQuery()
			if err != nil {
				return err
			}
			if len(list) == 0 {
				if noSync || !autoSyncOnEmpty(ctx, ch, "xdxr", code, "") {
					fmt.Println("无除权除息记录")
					return nil
				}
				list, err = doQuery()
				if err != nil {
					return err
				}
				if len(list) == 0 {
					fmt.Println("无除权除息记录")
					return nil
				}
			}

			if jsonOut {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(list)
			}

			t := newTable("除权日", 12, "类型", 10, "送股", 6, "转增", 6, "派息", 6, "配股价", 7, "配股比", 7)
			for _, r := range list {
				t.Row(r.ExDate, r.Type,
					fmt.Sprintf("%.1f", r.Bonus),
					fmt.Sprintf("%.1f", r.Transfer),
					fmt.Sprintf("%.2f", r.Dividend),
					fmt.Sprintf("%.2f", r.RightsPrice),
					fmt.Sprintf("%.2f", r.RightsRatio))
			}
			t.Print()
			return nil
		},
	}
	xdxrCmd.Flags().Bool("no-sync", false, "本地无数据时不自动触发 sync")
	queryCmd.AddCommand(xdxrCmd)

	// --- query info ---
	infoCmd := &cobra.Command{
		Use:   "info <code>",
		Short: "查询标的详情（F10 行业/省份/经营范围）",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			code := args[0]
			noSync, _ := cmd.Flags().GetBool("no-sync")
			jsonOut := isJSON(cmd)

			ctx, cancel := context.WithTimeout(context.Background(), 60*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			type infoRow struct {
				Code      string `json:"code"`
				Name      string `json:"name"`
				Market    string `json:"market"`
				Type      string `json:"type"`
				ListDate  string `json:"list_date"`
				Industry  string `json:"industry"`
				Sector    string `json:"sector"`
				Province  string `json:"province"`
				Business  string `json:"business"`
				UpdatedAt string `json:"updated_at"`
			}
			doQuery := func() (*infoRow, bool, error) {
				q := fmt.Sprintf(`SELECT code, name, market, type, list_date, delist_date,
					industry, sector, province, business, updated_at
					FROM %s.securities FINAL WHERE code = '%s' AND type = 'stock' LIMIT 1`, ch.DB(), code)
				row := ch.Conn().QueryRow(ctx, q)
				var (
					c, name, market, typ, industry, sector, province, business string
					listDate                                                    time.Time
					delistDate                                                  *time.Time
					updatedAt                                                   time.Time
				)
				if err := row.Scan(&c, &name, &market, &typ, &listDate, &delistDate,
					&industry, &sector, &province, &business, &updatedAt); err != nil {
					return nil, false, nil // 未找到标的本身
				}
				r := &infoRow{
					Code: c, Name: name, Market: market, Type: typ,
					ListDate:  listDate.Format("2006-01-02"),
					Industry:  industry, Sector: sector, Province: province, Business: business,
					UpdatedAt: updatedAt.Format("2006-01-02 15:04"),
				}
				hasF10 := industry != "" || sector != "" || province != ""
				return r, hasF10, nil
			}

			r, hasF10, err := doQuery()
			if err != nil {
				return err
			}
			if r == nil {
				fmt.Printf("未找到 %s（请先 sync meta）\n", code)
				return nil
			}
			if !hasF10 && !noSync {
				if autoSyncOnEmpty(ctx, ch, "info", code, "") {
					r, _, err = doQuery()
					if err != nil {
						return err
					}
				}
			}

			if jsonOut {
				enc := json.NewEncoder(os.Stdout)
				enc.SetIndent("", "  ")
				return enc.Encode(r)
			}

			fmt.Printf("代码     : %s\n", r.Code)
			fmt.Printf("名称     : %s\n", r.Name)
			fmt.Printf("市场     : %s / %s\n", r.Market, r.Type)
			fmt.Printf("上市日   : %s\n", r.ListDate)
			fmt.Printf("行业     : %s\n", r.Industry)
			fmt.Printf("板块     : %s\n", r.Sector)
			fmt.Printf("省份     : %s\n", r.Province)
			fmt.Printf("经营范围 : %s\n", r.Business)
			fmt.Printf("更新时间 : %s\n", r.UpdatedAt)
			return nil
		},
	}
	infoCmd.Flags().Bool("no-sync", false, "F10 为空时不自动触发 sync info")
	queryCmd.AddCommand(infoCmd)

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
