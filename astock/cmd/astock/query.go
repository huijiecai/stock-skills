package main

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"strconv"
	"strings"
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

// canAutoSync 判断给定查询场景是否值得触发 TDX sync。返回 (允许, 拒绝原因)。
//
// TDX 协议本质是"近端语义"——只能拉最近 N 根，无法按日期回溯。
// 因此当查询历史日期落到 TDX 拉取窗口之外时，sync 必然无效，应直接拒绝以免浪费请求。
func canAutoSync(kind, freq, date, from string) (bool, string) {
	today := time.Now()
	parse := func(s string) (time.Time, bool) {
		if s == "" {
			return time.Time{}, false
		}
		t, err := time.Parse("20060102", s)
		return t, err == nil
	}
	isWeekend := func(t time.Time) bool {
		wd := t.Weekday()
		return wd == time.Saturday || wd == time.Sunday
	}

	switch kind {
	case "minute":
		d, ok := parse(date)
		if !ok {
			return true, ""
		}
		if isWeekend(d) {
			return false, fmt.Sprintf("%s 是非交易日（周末）", d.Format("2006-01-02"))
		}
		// 800 根分钟线对应交易日数 = 800 / (240/freq分钟数)
		barsPerDay := 240
		switch freq {
		case "5m":
			barsPerDay = 48
		case "15m":
			barsPerDay = 16
		case "30m":
			barsPerDay = 8
		case "60m":
			barsPerDay = 4
		}
		coverDays := 800 / barsPerDay
		// 日历日 ≈ 交易日 * 1.5（含周末粗略估算）
		window := today.AddDate(0, 0, -int(float64(coverDays)*1.5))
		if d.Before(window) {
			return false, fmt.Sprintf(
				"%s 在 %s 频率窗口外（TDX 仅支持最近 ~%d 个交易日，可改用更大频率扩大覆盖）",
				d.Format("2006-01-02"), freq, coverDays)
		}
	case "daily":
		d, ok := parse(from)
		if !ok {
			return true, ""
		}
		// 日 K 800 根 ≈ 3.3 年；早于 4 年前几乎拉不到
		window := today.AddDate(-4, 0, 0)
		if d.Before(window) {
			return false, fmt.Sprintf(
				"from=%s 早于 TDX 可拉取窗口（约 %s 起，最近 ~800 个交易日）",
				d.Format("2006-01-02"), window.Format("2006-01-02"))
		}
	}
	return true, ""
}

// autoSyncOnEmpty 本地查不到数据时按 kind 自动触发 TDX 同步。
// 返回 true 表示调用方可重查；false 表示场景不适合 sync（已给出提示）。
//
// dataType 仅对 daily/minute 生效，决定走股票 K 还是指数 K；该参数从 CLI --type 透传。
// freq/date/from 仅用于历史日期窗口判定（见 canAutoSync）。
func autoSyncOnEmpty(ctx context.Context, ch *dwh.Client, kind, code string, dataType model.DataType, freq, date, from string) bool {
	if ok, reason := canAutoSync(kind, freq, date, from); !ok {
		fmt.Printf("无数据（%s）\n", reason)
		return false
	}
	fmt.Printf("⚠ 本地无 %s 数据，自动 sync %s %s...\n", kind, kind, code)
	tc := tdx.New()
	defer tc.Close()
	var err error
	switch kind {
	case "daily":
		_, err = ssync.Daily(ctx, ch, tc, code, dataType, false, 800, nil)
	case "minute":
		_, err = ssync.Minute(ctx, ch, tc, code, dataType, model.Freq(freq), 800)
	case "info":
		_, err = ssync.Info(ctx, ch, tc, code, false, nil)
	case "finance":
		_, err = ssync.Finance(ctx, ch, tc, code, false, nil)
	case "xdxr":
		_, err = ssync.XDXR(ctx, ch, tc, code, false, nil)
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

// parseType 将 --type 参数（stock/index/block）转换为 model.DataType，默认 stock。
func parseType(s string) model.DataType {
	switch s {
	case "index":
		return model.TypeIndex
	case "block":
		return model.TypeBlock
	}
	return model.TypeStock
}

// ensureSecurityExists 在 securities 表预检代码是否存在（指定 type）。
// 返回（存在，错误）。不存在时调用方负责提示“不存在”。
func ensureSecurityExists(ctx context.Context, ch *dwh.Client, code string, typ model.DataType) (bool, error) {
	q := fmt.Sprintf(`SELECT count() FROM %s.securities FINAL WHERE code = '%s' AND type = '%s'`,
		ch.DB(), code, string(typ))
	var n uint64
	if err := ch.Conn().QueryRow(ctx, q).Scan(&n); err != nil {
		return false, err
	}
	return n > 0, nil
}

func newQueryCmd() *cobra.Command {
	queryCmd := &cobra.Command{
		Use:   "query",
		Short: "从 ClickHouse 仓库查询数据",
	}

	// --- query kline ---
	// 单一 K 线命令，按 --freq 分发：daily(默认) 走 kline_daily，1m/5m/.../60m 走 kline_minute
	runKlineDaily := func(cmd *cobra.Command, args []string) error {
		code := args[0]
		from, _ := cmd.Flags().GetString("from")
		to, _ := cmd.Flags().GetString("to")
		adjust, _ := cmd.Flags().GetString("adjust")
		limit, _ := cmd.Flags().GetInt("limit")
		noSync, _ := cmd.Flags().GetBool("no-sync")
		typeStr, _ := cmd.Flags().GetString("type")
		maStr, _ := cmd.Flags().GetString("ma")
		dataType := parseType(typeStr)
		jsonOut := isJSON(cmd)

		// 解析 --ma 均线参数：逗号分隔的正整数列表（如 "5,10,20"）
		var maWindows []int
		maxW := 0
		if strings.TrimSpace(maStr) != "" {
			for _, p := range strings.Split(maStr, ",") {
				w, err := strconv.Atoi(strings.TrimSpace(p))
				if err != nil || w < 2 {
					return fmt.Errorf("--ma 参数无效: %q（需要逗号分隔的≥ 2 整数）", maStr)
				}
				maWindows = append(maWindows, w)
				if w > maxW {
					maxW = w
				}
			}
		}
		// 为计算均线热身，多拉 maxW-1 根（仅供计算，不展示）
		fetchLimit := limit
		if maxW > 0 {
			fetchLimit = limit + maxW - 1
		}

		ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer cancel()
		ch, err := dwh.New(ctx, cfg)
		if err != nil {
			return err
		}
		defer ch.Close()

		bars, err := queryDaily(ctx, ch, code, dataType, from, to, fetchLimit)
		if err != nil {
			return err
		}
		if len(bars) == 0 {
			if noSync || !autoSyncOnEmpty(ctx, ch, "daily", code, dataType, "", "", from) {
				fmt.Println("无数据")
				return nil
			}
			bars, err = queryDaily(ctx, ch, code, dataType, from, to, fetchLimit)
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

		// 换手率：volume(手) * 100 / float_share * 100% = volume * 10000 / float_share
		// finance 表无数据时 floatShare=0，turnover 留 0，表格显示 "-"
		floatShare, _ := queryFloatShare(ctx, ch, code)
		if floatShare > 0 {
			for _, b := range bars {
				b.Turnover = float64(b.Volume) * 10000 / float64(floatShare)
			}
		}

		// 计算均线（queryDaily 末尾已翻转为时间 ASC：bars[0]=最旧，bars[len-1]=最新）
		// 在复权后计算，避免除权日均线虚假跳变
		if len(maWindows) > 0 {
			for _, b := range bars {
				b.MA = make(map[string]float64)
			}
			for _, w := range maWindows {
				for i := w - 1; i < len(bars); i++ {
					var sum float64
					for j := i - w + 1; j <= i; j++ {
						sum += bars[j].Close
					}
					bars[i].MA[fmt.Sprintf("MA%d", w)] = sum / float64(w)
				}
			}
			// 裁掉热身多拉的头部，仅保留最新 limit 行
			if len(bars) > limit {
				bars = bars[len(bars)-limit:]
			}
		}

		if jsonOut {
			enc := json.NewEncoder(os.Stdout)
			enc.SetIndent("", "  ")
			return enc.Encode(bars)
		}

		// 表格输出
		headers := []interface{}{"日期", 12, "开盘", 8, "最高", 8, "最低", 8, "收盘", 8, "涨跌%", 8, "成交量", 10, "成交额", 10, "换手%", 8}
		for _, w := range maWindows {
			headers = append(headers, fmt.Sprintf("MA%d", w), 8)
		}
		t := newTable(headers...)
		for _, b := range bars {
			pct := 0.0
			if b.PreClose > 0 {
				pct = (b.Close - b.PreClose) / b.PreClose * 100
			}
			turnoverStr := "-"
			if b.Turnover > 0 {
				turnoverStr = fmt.Sprintf("%.2f%%", b.Turnover)
			}
			row := []string{
				b.TradeDate,
				fmt.Sprintf("%.2f", b.Open),
				fmt.Sprintf("%.2f", b.High),
				fmt.Sprintf("%.2f", b.Low),
				fmt.Sprintf("%.2f", b.Close),
				fmt.Sprintf("%+.2f%%", pct),
				fmt.Sprintf("%d", b.Volume),
				formatAmount(b.Amount),
				turnoverStr,
			}
			for _, w := range maWindows {
				k := fmt.Sprintf("MA%d", w)
				if v, ok := b.MA[k]; ok {
					row = append(row, fmt.Sprintf("%.2f", v))
				} else {
					row = append(row, "-")
				}
			}
			t.Row(row...)
		}
		t.Print()
		return nil
	}

	runKlineMinute := func(cmd *cobra.Command, args []string, freq string) error {
		code := args[0]
		date, _ := cmd.Flags().GetString("date")
		limit, _ := cmd.Flags().GetInt("limit")
		noSync, _ := cmd.Flags().GetBool("no-sync")
		typeStr, _ := cmd.Flags().GetString("type")
		dataType := parseType(typeStr)
		jsonOut := isJSON(cmd)

		// 分钟 K 行数默认更大；用户未显式 --limit 时回退 240
		if !cmd.Flags().Changed("limit") {
			limit = 240
		}

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
			where := fmt.Sprintf("code = '%s' AND type = '%s' AND freq = '%s'", code, string(dataType), freq)
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
			if noSync || !autoSyncOnEmpty(ctx, ch, "minute", code, dataType, freq, date, "") {
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
	}

	klineCmd := &cobra.Command{
		Use:   "kline <code>",
		Short: "查询 K 线（--freq daily(默认) | 1m | 5m | 15m | 30m | 60m）",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			freq, _ := cmd.Flags().GetString("freq")
			switch freq {
			case "daily", "1d", "":
				return runKlineDaily(cmd, args)
			case "1m", "5m", "15m", "30m", "60m":
				return runKlineMinute(cmd, args, freq)
			default:
				return fmt.Errorf("--freq 取值无效: %q（允许: daily | 1m | 5m | 15m | 30m | 60m）", freq)
			}
		},
	}
	klineCmd.Flags().String("freq", "daily", "频率: daily(日K，默认) / 1m / 5m / 15m / 30m / 60m")
	klineCmd.Flags().Int("limit", 30, "返回行数（daily 默认 30；分钟 K 未指定时回退 240）")
	klineCmd.Flags().Bool("no-sync", false, "本地无数据时不自动触发 sync")
	klineCmd.Flags().String("type", "stock", "标的类型: stock(默认)/index/block")
	// freq=daily 专属
	klineCmd.Flags().String("from", "", "[freq=daily] 起始日期 YYYYMMDD")
	klineCmd.Flags().String("to", "", "[freq=daily] 结束日期 YYYYMMDD")
	klineCmd.Flags().String("adjust", "qfq", "[freq=daily] 复权: qfq(前复权)/none(不复权)")
	klineCmd.Flags().String("ma", "", "[freq=daily] 均线窗口，逗号分隔（如 5,10,20）；热身不足的行显示 -")
	// freq=分钟 专属
	klineCmd.Flags().String("date", "", "[freq=分钟] 指定日期 YYYYMMDD（默认取最新）")
	queryCmd.AddCommand(klineCmd)

	// --- query stock ---
	stockCmd := &cobra.Command{
		Use:   "stock",
		Short: "查询标的列表（股票/指数）；--sort-by amount|pct 按指定日行情排序",
		RunE: func(cmd *cobra.Command, args []string) error {
			typ, _ := cmd.Flags().GetString("type")
			market, _ := cmd.Flags().GetString("market")
			industry, _ := cmd.Flags().GetString("industry")
			keyword, _ := cmd.Flags().GetString("keyword")
			limit, _ := cmd.Flags().GetInt("limit")
			sortBy, _ := cmd.Flags().GetString("sort-by")
			date, _ := cmd.Flags().GetString("date")
			asc, _ := cmd.Flags().GetBool("asc")
			jsonOut := isJSON(cmd)

			ctx, cancel := context.WithTimeout(context.Background(), 15*time.Second)
			defer cancel()
			ch, err := dwh.New(ctx, cfg)
			if err != nil {
				return err
			}
			defer ch.Close()

			// 走 JOIN 分支：按当日成交额/涨幅排序
			if sortBy == "amount" || sortBy == "pct" {
				where := "s.type = 'stock'"
				if typ != "" {
					where = fmt.Sprintf("s.type = '%s'", typ)
				}
				if market != "" {
					where += fmt.Sprintf(" AND s.market = '%s'", market)
				}
				if industry != "" {
					where += fmt.Sprintf(" AND s.industry LIKE '%%%s%%'", industry)
				}
				if keyword != "" {
					where += fmt.Sprintf(" AND (s.name LIKE '%%%s%%' OR s.code LIKE '%%%s%%')", keyword, keyword)
				}

				dateExpr := fmt.Sprintf(`(SELECT max(trade_date) FROM %s.kline_daily WHERE type = '%s')`, ch.DB(), func() string {
					if typ != "" {
						return typ
					}
					return "stock"
				}())
				if date != "" {
					d, err := time.Parse("20060102", date)
					if err != nil {
						return fmt.Errorf("--date 参数无效: %q（需 YYYYMMDD）", date)
					}
					dateExpr = fmt.Sprintf("'%s'", d.Format("2006-01-02"))
				}

				sortField := "k.amount"
				if sortBy == "pct" {
					sortField = "if(k.pre_close > 0, (k.close - k.pre_close) / k.pre_close, -1e9)"
				}
				order := "DESC"
				if asc {
					order = "ASC"
				}

				joinType := "stock"
				if typ != "" {
					joinType = typ
				}
				q := fmt.Sprintf(`SELECT s.code, s.name, s.market, s.type, s.industry, k.close, k.pre_close, k.amount, k.trade_date
					FROM %[1]s.securities s FINAL
					INNER JOIN (
						SELECT code, close, pre_close, amount, trade_date
						FROM %[1]s.kline_daily FINAL
						WHERE type = '%[2]s' AND trade_date = %[3]s
					) AS k ON k.code = s.code
					WHERE %[4]s
					ORDER BY %[5]s %[6]s, s.code
					LIMIT %[7]d`, ch.DB(), joinType, dateExpr, where, sortField, order, limit)

				rows, err := ch.Conn().Query(ctx, q)
				if err != nil {
					return err
				}
				defer rows.Close()

				type rankedRow struct {
					Code      string  `json:"code"`
					Name      string  `json:"name"`
					Market    string  `json:"market"`
					Type      string  `json:"type"`
					Industry  string  `json:"industry"`
					Close     float64 `json:"close"`
					Pct       float64 `json:"pct"`
					Amount    float64 `json:"amount"`
					TradeDate string  `json:"trade_date"`
				}
				var list []*rankedRow
				for rows.Next() {
					var r rankedRow
					var pre float64
					var td time.Time
					if err := rows.Scan(&r.Code, &r.Name, &r.Market, &r.Type, &r.Industry, &r.Close, &pre, &r.Amount, &td); err != nil {
						return err
					}
					if pre > 0 {
						r.Pct = (r.Close - pre) / pre * 100
					}
					r.TradeDate = td.Format("2006-01-02")
					list = append(list, &r)
				}
				if len(list) == 0 {
					fmt.Println("无匹配结果（未 sync 当日 daily？试 astock sync all --all --skip-* --days 1）")
					return nil
				}

				if jsonOut {
					enc := json.NewEncoder(os.Stdout)
					enc.SetIndent("", "  ")
					return enc.Encode(list)
				}

				fmt.Printf("=== 按 %s %s排序（交易日：%s） ===\n", sortBy, order, list[0].TradeDate)
				t := newTable("代码", 8, "名称", 12, "市场", 4, "行业", 12, "收盘", 8, "涨幅%", 8, "成交额", 10)
				for _, r := range list {
					t.Row(r.Code, r.Name, r.Market, r.Industry,
						fmt.Sprintf("%.2f", r.Close),
						fmt.Sprintf("%+.2f%%", r.Pct),
						formatAmount(r.Amount))
				}
				t.Print()
				fmt.Printf("\n共 %d 条\n", len(list))
				return nil
			}

			// 默认分支：按 code 排序的原语义
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
	stockCmd.Flags().String("type", "stock", "标的类型: stock/index")
	stockCmd.Flags().String("market", "", "市场: sh/sz/bj")
	stockCmd.Flags().String("industry", "", "行业关键字（模糊匹配）")
	stockCmd.Flags().String("keyword", "", "名称或代码关键字")
	stockCmd.Flags().Int("limit", 50, "返回条数")
	stockCmd.Flags().String("sort-by", "", "排序键: amount(成交额) / pct(涨幅)；为空按 code 排序")
	stockCmd.Flags().String("date", "", "仅 sort-by 启用时生效；指定交易日 YYYYMMDD，默认最新")
	stockCmd.Flags().Bool("asc", false, "仅 sort-by 启用时生效；默认 DESC，--asc 换升序")
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

	// rank / members 子命令由 query_block.go 提供（增强版 members 含当日行情，rank 为新增涨幅榜）
	addBlockRankCmd(blockCmd)
	addBlockMembersCmd(blockCmd)
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

			// 预检标的是否为已入库股票：finance 仅适用 type=stock。
			if ok, err := ensureSecurityExists(ctx, ch, code, model.TypeStock); err != nil {
				return err
			} else if !ok {
				fmt.Printf("代码 %s 不存在（securities 表无 type=stock 记录；如查指数/板块请用 query kline --type index 或 query block）\n", code)
				return nil
			}

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
				if noSync || !autoSyncOnEmpty(ctx, ch, "finance", code, "", "", "", "") {
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

			if ok, err := ensureSecurityExists(ctx, ch, code, model.TypeStock); err != nil {
				return err
			} else if !ok {
				fmt.Printf("代码 %s 不存在（securities 表无 type=stock 记录）\n", code)
				return nil
			}

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
				if noSync || !autoSyncOnEmpty(ctx, ch, "xdxr", code, "", "", "", "") {
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

			type blockOfStock struct {
				Code   string  `json:"code"`
				Name   string  `json:"name"`
				Type   string  `json:"type"`
				Pct    float64 `json:"pct"`     // 板块当日涨幅 %
				HasPct bool    `json:"has_pct"` // false 表示未同步过板块日K
			}
			type infoRow struct {
				Code      string          `json:"code"`
				Name      string          `json:"name"`
				Market    string          `json:"market"`
				Type      string          `json:"type"`
				ListDate  string          `json:"list_date"`
				Industry  string          `json:"industry"`
				Sector    string          `json:"sector"`
				Province  string          `json:"province"`
				Business  string          `json:"business"`
				UpdatedAt string          `json:"updated_at"`
				Blocks    []*blockOfStock `json:"blocks,omitempty"`
			}
			doQuery := func() (*infoRow, bool, bool, error) {
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
					return nil, false, false, nil // 未找到标的本身
				}
				r := &infoRow{
					Code: c, Name: name, Market: market, Type: typ,
					ListDate:  listDate.Format("2006-01-02"),
					Industry:  industry, Sector: sector, Province: province, Business: business,
					UpdatedAt: updatedAt.Format("2006-01-02 15:04"),
				}
				hasF10 := industry != "" || sector != "" || province != ""
				// 防抖：1 小时内已 sync 过（即使 F10 仍为空也不重复拉，避免死循环）
				recentSynced := !updatedAt.IsZero() && time.Since(updatedAt) < time.Hour
				return r, hasF10, recentSynced, nil
			}

			r, hasF10, recentSynced, err := doQuery()
			if err != nil {
				return err
			}
			if r == nil {
				fmt.Printf("代码 %s 不存在（securities 表无 type=stock 记录；如查指数请用 query stock --type index --keyword %s）\n", code, code)
				return nil
			}
			if !hasF10 && !recentSynced && !noSync {
				if autoSyncOnEmpty(ctx, ch, "info", code, "", "", "", "") {
					r, _, _, err = doQuery()
					if err != nil {
						return err
					}
				}
			}

			// 查询所属板块（带板块当日涨幅）——block_constituents JOIN blocks LEFT JOIN kline_daily(type=block)
			// 只要 block_constituents 不为空就有输出；未 sync block daily 时涨幅列显示 "-"
			queryBlocksOf := func() ([]*blockOfStock, error) {
				q := fmt.Sprintf(`SELECT b.code, b.name, b.type, k.close, k.pre_close
					FROM %[1]s.block_constituents bc FINAL
					INNER JOIN (SELECT code, name, type FROM %[1]s.blocks FINAL) AS b ON b.code = bc.block_code
					LEFT JOIN (
						SELECT code, close, pre_close FROM %[1]s.kline_daily FINAL
						WHERE type = 'block'
						  AND trade_date = (SELECT max(trade_date) FROM %[1]s.kline_daily WHERE type = 'block')
					) AS k ON k.code = b.code
					WHERE bc.stock_code = '%[2]s'
					ORDER BY if(k.pre_close > 0, (k.close - k.pre_close) / k.pre_close, -1e9) DESC, b.code`,
					ch.DB(), code)
				rows, err := ch.Conn().Query(ctx, q)
				if err != nil {
					return nil, err
				}
				defer rows.Close()
				var list []*blockOfStock
				for rows.Next() {
					var bc blockOfStock
					var cl, pc float64
					if err := rows.Scan(&bc.Code, &bc.Name, &bc.Type, &cl, &pc); err != nil {
						return nil, err
					}
					if pc > 0 {
						bc.Pct = (cl - pc) / pc * 100
						bc.HasPct = true
					}
					list = append(list, &bc)
				}
				return list, nil
			}
			if blks, err := queryBlocksOf(); err == nil {
				r.Blocks = blks
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

			// 所属板块段（按板块当日涨幅 DESC）
			if len(r.Blocks) > 0 {
				fmt.Println()
				fmt.Printf("所属板块（共 %d 个，按当日涨幅 DESC）:\n", len(r.Blocks))
				bt := newTable("代码", 8, "名称", 14, "类型", 8, "涨幅%", 8)
				for _, b := range r.Blocks {
					pctStr := "-"
					if b.HasPct {
						pctStr = fmt.Sprintf("%+.2f%%", b.Pct)
					}
					bt.Row(b.Code, b.Name, b.Type, pctStr)
				}
				bt.Print()
			}
			return nil
		},
	}
	infoCmd.Flags().Bool("no-sync", false, "F10 为空时不自动触发 sync info")
	queryCmd.AddCommand(infoCmd)

	// --- query market / query limit（派生命令，纯 ClickHouse SQL）---
	// query limit ladder 作为 query limit 的子命令在 addLimitCmd 内部挂载（命名宪法 v1：禁连字符复合命令名）
	addMarketCmd(queryCmd)
	addLimitCmd(queryCmd)

	return queryCmd
}

// --- 内部数据结构 ---

type dailyBar struct {
	TradeDate string             `json:"trade_date"`
	Open      float64            `json:"open"`
	High      float64            `json:"high"`
	Low       float64            `json:"low"`
	Close     float64            `json:"close"`
	PreClose  float64            `json:"pre_close"`
	Volume    uint64             `json:"volume"`
	Amount    float64            `json:"amount"`
	Turnover  float64            `json:"turnover"` // 换手率（%）。无 finance 数据时为 0
	MA        map[string]float64 `json:"ma,omitempty"` // 均线：键如 "MA5" / "MA10" / "MA20"，热身不足不入表
}

type xdxrRow struct {
	ExDate   time.Time
	Transfer float32 // 送转（每 10 股）
	Dividend float32 // 派息（每 10 股，元）
	Peigu    float32 // 配股比例
	Peigujia float32 // 配股价
}

func queryDaily(ctx context.Context, ch *dwh.Client, code string, dataType model.DataType, from, to string, limit int) ([]*dailyBar, error) {
	where := fmt.Sprintf("code = '%s' AND type = '%s'", code, string(dataType))
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

// queryFloatShare 取 finance 表中最近一期的流通股本（股）。
// finance 表无数据时返回 0，CLI 层按 "-" 展示。
func queryFloatShare(ctx context.Context, ch *dwh.Client, code string) (uint64, error) {
	q := fmt.Sprintf(`SELECT float_share FROM %s.finance FINAL WHERE code = '%s' ORDER BY report_date DESC LIMIT 1`, ch.DB(), code)
	rows, err := ch.Conn().Query(ctx, q)
	if err != nil {
		return 0, err
	}
	defer rows.Close()
	if rows.Next() {
		var fs uint64
		if err := rows.Scan(&fs); err != nil {
			return 0, err
		}
		return fs, nil
	}
	return 0, nil
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
