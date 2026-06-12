package tdx

import (
	"fmt"
	"time"

	itdx "github.com/injoyai/tdx"
	"github.com/injoyai/tdx/protocol"

	"github.com/huijiecai/stock/astock/internal/model"
)

// GetKlineDayAll 拉取一只股票/ETF 全部日 K（自动分页，最早 1990 至今）。
// code: 不带前缀的 6 位代码。type 用于标记返回 Bar.Type。
func (c *Client) GetKlineDayAll(code string, dataType model.DataType) ([]*model.Bar, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, err
	}

	var resp *protocol.KlineResp
	if dataType == model.TypeIndex {
		resp, err = cli.GetIndexDayAll(IndexCode(code))
	} else {
		resp, err = cli.GetKlineDayAll(code)
	}
	if err != nil {
		return nil, fmt.Errorf("get kline day all %s: %w", code, err)
	}
	return klineToBars(code, dataType, model.FreqDay, resp), nil
}

// GetKlineDay 拉取最近 N 根日 K（含部分历史，用于 sync all --days N 的增量场景）。
// 实际 injoyai/tdx 通过 start/count 倒序拉取，count<=800。
func (c *Client) GetKlineDay(code string, dataType model.DataType, count uint16) ([]*model.Bar, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, err
	}

	var resp *protocol.KlineResp
	if dataType == model.TypeIndex {
		resp, err = cli.GetIndexDay(IndexCode(code), 0, count)
	} else {
		resp, err = cli.GetKlineDay(code, 0, count)
	}
	if err != nil {
		return nil, fmt.Errorf("get kline day %s: %w", code, err)
	}
	return klineToBars(code, dataType, model.FreqDay, resp), nil
}

// GetKlineMinute 拉取一只标的指定频率的分钟 K（最近 count 根，count<=800）。
// freq 支持: 1m / 5m / 15m / 30m / 60m。
func (c *Client) GetKlineMinute(code string, dataType model.DataType, freq model.Freq, count uint16) ([]*model.Bar, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, err
	}

	var (
		fn   func(string, uint16, uint16) (*protocol.KlineResp, error)
		fnIx func(string, uint16, uint16) (*protocol.KlineResp, error)
	)
	switch freq {
	case model.Freq1m:
		fn = cli.GetKlineMinute
		fnIx = cli.GetIndexMinute
	case model.Freq5m:
		fn = cli.GetKline5Minute
		fnIx = cli.GetIndex5Minute
	case model.Freq15m:
		fn = cli.GetKline15Minute
		fnIx = cli.GetIndex15Minute
	case model.Freq30m:
		fn = cli.GetKline30Minute
		fnIx = cli.GetIndex30Minute
	case model.Freq60m:
		fn = cli.GetKline60Minute
		fnIx = cli.GetIndex60Minute
	default:
		return nil, fmt.Errorf("unsupported freq: %s", freq)
	}

	// 分页拉取，TDX 单次上限 800 根
	const maxPerReq uint16 = 800
	var all []*model.Bar
	remaining := count
	offset := uint16(0)

	for remaining > 0 {
		batch := remaining
		if batch > maxPerReq {
			batch = maxPerReq
		}

		var resp *protocol.KlineResp
		if dataType == model.TypeIndex {
			resp, err = fnIx(IndexCode(code), offset, batch)
		} else {
			resp, err = fn(code, offset, batch)
		}
		if err != nil {
			return nil, fmt.Errorf("get kline %s minute %s (offset=%d): %w", freq, code, offset, err)
		}
		bars := klineToBars(code, dataType, freq, resp)
		if len(bars) == 0 {
			break // 没有更多数据
		}
		all = append(all, bars...)
		offset += uint16(len(bars))
		remaining -= uint16(len(bars))
		if uint16(len(bars)) < batch {
			break // 返回不足请求数，说明到底了
		}
	}
	return all, nil
}

// klineToBars 把 injoyai 的 KlineResp 转为 model.Bar 切片。
func klineToBars(code string, dataType model.DataType, freq model.Freq, resp *protocol.KlineResp) []*model.Bar {
	if resp == nil {
		return nil
	}
	out := make([]*model.Bar, 0, len(resp.List))
	for _, k := range resp.List {
		bar := &model.Bar{
			Code:     code,
			Type:     dataType,
			Freq:     freq,
			Time:     k.Time,
			Open:     k.Open.Float64(),
			High:     k.High.Float64(),
			Low:      k.Low.Float64(),
			Close:    k.Close.Float64(),
			PreClose: k.Last.Float64(),
			Volume:   k.Volume,
			Amount:   k.Amount.Float64(),
		}
		if freq == model.FreqDay {
			bar.TradeDate = k.Time.Format("2006-01-02")
		}
		out = append(out, bar)
	}
	return out
}

// 静默引用，确保 itdx 包被 go.sum 锁定（避免 unused 报错）。
var _ = itdx.DialDefault

// 占位避免 time 包未使用（实际下面 GetMinute 等会用到）
var _ = time.Time{}
