package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/spf13/cobra"

	"github.com/huijiecai/stock/astock/internal/model"
	"github.com/huijiecai/stock/astock/internal/tdx"
)

type liveBreadthSource struct {
	scope string
	name  string
	code  string
}

var liveBreadthLocation = time.FixedZone("Asia/Shanghai", 8*60*60)

var liveBreadthScopeNames = map[string]string{
	"sh": "上海",
	"sz": "深圳",
	"bj": "北交所",
}

type LiveBreadthSnapshot struct {
	AsOf      string                `json:"as_of"`
	UpCount   int                   `json:"up_count"`
	DownCount int                   `json:"down_count"`
	Markets   []*model.BreadthPoint `json:"markets"`
}

type LiveIndexSnapshot struct {
	FetchedAt string               `json:"fetched_at"`
	Source    string               `json:"source"`
	Requests  int                  `json:"requests"`
	ElapsedMS int64                `json:"elapsed_ms"`
	Indices   []*model.Quote       `json:"indices"`
	Breadth   *LiveBreadthSnapshot `json:"breadth"`
}

func runLiveIndex(cmd *cobra.Command, args []string) error {
	tc := tdx.New()
	defer tc.Close()

	startedAt := time.Now()
	quotes, err := tc.GetIndexQuotes(args)
	if err != nil {
		return err
	}
	if len(quotes) == 0 {
		return fmt.Errorf("TDX 未返回指数报价")
	}

	sources, err := liveBreadthSourcesForIndices(args)
	if err != nil {
		return err
	}
	points := make([]*model.BreadthPoint, 0, len(sources))
	for _, source := range sources {
		point, err := tc.GetIndexBreadth(source.scope, source.name, source.code)
		if err != nil {
			return err
		}
		points = append(points, point)
	}
	if err := validateLiveBreadth(points, time.Now().In(liveBreadthLocation)); err != nil {
		return err
	}

	breadth := &LiveBreadthSnapshot{
		AsOf:    latestBreadthAsOf(points),
		Markets: points,
	}
	breadth.UpCount, breadth.DownCount = sumValidBreadth(points)
	snapshot := LiveIndexSnapshot{
		FetchedAt: quotes[0].AsOf,
		Source:    "tdx",
		Requests:  1 + len(sources),
		ElapsedMS: time.Since(startedAt).Milliseconds(),
		Indices:   quotes,
		Breadth:   breadth,
	}

	if isJSON(cmd) {
		enc := json.NewEncoder(os.Stdout)
		enc.SetIndent("", "  ")
		return enc.Encode(snapshot)
	}

	fmt.Printf("=== 实时指数（数据时间 %s）===\n", breadth.AsOf)
	indexTable := newTable("代码", 10, "点位", 12, "涨跌%", 10, "成交额", 16)
	for _, quote := range quotes {
		indexTable.Row(quote.Code, fmt.Sprintf("%.2f", quote.Price),
			fmt.Sprintf("%+.2f%%", quote.ChangePct), fmt.Sprintf("%.0f", quote.Amount))
	}
	indexTable.Print()

	fmt.Println("\n=== 市场广度 ===")
	table := newTable("市场", 8, "上涨", 8, "下跌", 8)
	for _, point := range points {
		up, down := fmt.Sprintf("%d", point.UpCount), fmt.Sprintf("%d", point.DownCount)
		if !point.Valid {
			up, down = "无数据", "无数据"
		}
		table.Row(liveBreadthScopeNames[point.Scope], up, down)
	}
	table.Print()
	summaryName := "所选市场合计"
	if len(points) == 1 {
		summaryName = liveBreadthScopeNames[points[0].Scope]
	}
	fmt.Printf("\n%s：上涨 %d，下跌 %d；已统计 %d 只（平盘/无报价未返回）\n",
		summaryName, breadth.UpCount, breadth.DownCount, breadth.UpCount+breadth.DownCount)
	fmt.Printf("TDX：%d 次请求，耗时 %dms\n", snapshot.Requests, snapshot.ElapsedMS)
	return nil
}

func liveBreadthSourcesForIndices(codes []string) ([]liveBreadthSource, error) {
	sources := make([]liveBreadthSource, 0, 3)
	seen := make(map[string]bool, 3)
	for _, code := range codes {
		prefixed := strings.ToLower(tdx.IndexCode(code))
		scope := ""
		for _, candidate := range []string{"sh", "sz", "bj"} {
			if strings.HasPrefix(prefixed, candidate) {
				scope = candidate
				break
			}
		}
		if scope == "" {
			return nil, fmt.Errorf("无法判断指数 %s 所属市场", code)
		}
		if seen[scope] {
			continue
		}
		seen[scope] = true
		sources = append(sources, liveBreadthSource{scope: scope, name: code, code: code})
	}
	return sources, nil
}

func sumValidBreadth(points []*model.BreadthPoint) (up, down int) {
	for _, point := range points {
		if point == nil || !point.Valid {
			continue
		}
		up += point.UpCount
		down += point.DownCount
	}
	return up, down
}

func validateLiveBreadth(points []*model.BreadthPoint, now time.Time) error {
	valid := 0
	today := now.Format("2006-01-02")
	for _, point := range points {
		if point == nil || !point.Valid {
			continue
		}
		valid++
		if len(point.AsOf) < len(today) || point.AsOf[:len(today)] != today {
			return fmt.Errorf("拒绝：%s 返回的数据时间为 %s，不是今天 %s", point.Name, point.AsOf, today)
		}
	}
	if valid == 0 {
		return fmt.Errorf("TDX 指数 K 线未返回有效涨跌家数")
	}
	return nil
}

func latestBreadthAsOf(points []*model.BreadthPoint) string {
	latest := ""
	for _, point := range points {
		if point != nil && point.Valid && point.AsOf > latest {
			latest = point.AsOf
		}
	}
	return latest
}
