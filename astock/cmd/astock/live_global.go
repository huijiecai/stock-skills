package main

import (
	"encoding/json"
	"fmt"
	"os"
	"time"

	"github.com/injoyai/tdx"
	"github.com/spf13/cobra"
)

// globalInstruments 全球市场快照固定品种(TDX 扩展行情实测可用集;
// 道指/标普该免费源没有——盘前用纳指系+费半代表美股方向,搜索补道指标普)。
var globalInstruments = []struct {
	Market uint8
	Code   string
	Name   string
}{
	{12, "A_IXIC", "纳斯达克综合"},
	{12, "A_NDX", "纳斯达克100"},
	{12, "A_SOX", "费城半导体"},
	{12, "A_HXC", "纳指金龙中国"},
	{27, "HSI", "恒生指数"},
	{17, "CL00W", "NYMEX原油主连"},
	{16, "GC00W", "COMEX黄金主连"},
	{16, "HG00W", "COMEX铜主连"},
	{16, "SI00W", "COMEX白银主连"},
}

// GlobalQuote 全球市场单品种快照。
type GlobalQuote struct {
	Market     uint8   `json:"market"`
	Code       string  `json:"code"`
	Name       string  `json:"name"`
	PreClose   float64 `json:"pre_close"`
	Open       float64 `json:"open"`
	High       float64 `json:"high"`
	Low        float64 `json:"low"`
	Price      float64 `json:"price"`
	ChangePct  float64 `json:"change_pct"`
	Amount     uint32  `json:"volume"` // 扩展行情只有量(手),无额
	FetchedAt  string  `json:"fetched_at"`
}

func buildLiveGlobalCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "global",
		Short: "全球市场实时快照(美股指数/商品期货/港股,TDX 扩展行情)",
		RunE:  runLiveGlobal,
	}
}

func runLiveGlobal(cmd *cobra.Command, args []string) error {
	jsonOut := isJSON(cmd)
	cli, err := tdx.DialExHqDefault(tdx.WithDebug(false)) // WithDebug(false) 关库内日志,防污染 stdout/JSON
	if err != nil {
		return fmt.Errorf("扩展行情连接失败: %w", err)
	}
	defer cli.Close()
	cli.SetTimeout(8 * time.Second)
	time.Sleep(600 * time.Millisecond) // 心跳就绪

	now := time.Now().Format("2006-01-02 15:04:05")
	out := make([]GlobalQuote, 0, len(globalInstruments))
	for _, t := range globalInstruments {
		q, err := cli.ExQuote(t.Market, t.Code)
		if err != nil || q == nil {
			continue // 单品种失败不拖垮整张快照
		}
		g := GlobalQuote{
			Market: t.Market, Code: t.Code, Name: t.Name,
			PreClose: q.PreClose, Open: q.Open, High: q.High, Low: q.Low,
			Price: q.Price, Amount: q.ZongLiang, FetchedAt: now,
		}
		if q.PreClose > 0 {
			g.ChangePct = (q.Price - q.PreClose) / q.PreClose * 100
		}
		out = append(out, g)
	}
	if len(out) == 0 {
		return fmt.Errorf("全部品种取数失败(扩展行情服务器不可达?)")
	}
	if !jsonOut {
		for _, g := range out {
			fmt.Printf("%-10s %-12s 昨收 %10.2f  现价 %10.2f  %+6.2f%%\n",
				g.Code, g.Name, g.PreClose, g.Price, g.ChangePct)
		}
		fmt.Printf("取数时刻: %s\n", now)
		return nil
	}
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	return enc.Encode(out)
}
