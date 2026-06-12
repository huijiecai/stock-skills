package tdx

import (
	"fmt"
	"time"

	"github.com/injoyai/tdx/protocol"

	"github.com/huijiecai/stock/astock/internal/model"
)

// GetFinance 拉取一只股票的财务/F10 信息。
// 通达信 GetFinanceInfo 返回的是"全字段大杂烩"，本函数提取核心 9 个指标 + 上市日期 + 流通股本。
//
// 注意：通达信只提供单条最新财务快照（按更新日期），不是分季度报告序列。
// ReportDate 取 UpdatedDate（如 20240331 → 2024-03-31）。
func (c *Client) GetFinance(market, code string) (*model.Finance, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, err
	}

	ex := exchangeOf(market)
	info, err := cli.GetFinanceInfo(ex, code)
	if err != nil {
		return nil, fmt.Errorf("get finance %s: %w", code, err)
	}
	if info == nil {
		return nil, nil
	}

	return &model.Finance{
		Code:           code,
		ReportDate:     parseTdxDate(info.UpdatedDate),
		Revenue:        info.ZhuYingShouRu,
		NetProfit:      info.JingLiRun,
		EPS:            0, // 通达信 FinanceInfo 不直接给 EPS/BPS/ROE，需要从 净利润/总股本 等推算（暂留 0，后续 query 端算）
		BPS:            0,
		ROE:            0,
		TotalShare:     uint64(info.ZongGuBen),
		FloatShare:     uint64(info.LiuTongGuBen),
		TotalAssets:    info.ZongZiChan,
		TotalLiability: info.LiuDongFuZhai + info.ChangQiFuZhai,
	}, nil
}

// GetFinanceInfo 暴露原始 FinanceInfo，供 sync info 把 industry/sector/province 写入 securities。
func (c *Client) GetFinanceInfo(market, code string) (*protocol.FinanceInfo, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, err
	}
	ex := exchangeOf(market)
	return cli.GetFinanceInfo(ex, code)
}

// exchangeOf 把 market 字符串转为 protocol.Exchange。
func exchangeOf(market string) protocol.Exchange {
	switch market {
	case "sh":
		return protocol.ExchangeSH
	case "sz":
		return protocol.ExchangeSZ
	case "bj":
		return protocol.ExchangeBJ
	}
	return protocol.ExchangeSZ
}

// parseTdxDate 把 20240331 这种 uint32 转为 time.Time。零值返回 time.Time{}。
func parseTdxDate(d uint32) time.Time {
	if d == 0 {
		return time.Time{}
	}
	y := int(d / 10000)
	m := int((d / 100) % 100)
	day := int(d % 100)
	if y < 1990 || m < 1 || m > 12 || day < 1 || day > 31 {
		return time.Time{}
	}
	return time.Date(y, time.Month(m), day, 0, 0, 0, 0, time.Local)
}
