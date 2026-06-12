package tdx

import (
	"fmt"

	"github.com/injoyai/tdx/protocol"

	"github.com/huijiecai/stock/astock/internal/model"
)

// ListBlocks 拉取全市场板块（概念 GN + 风格/地域 FG + 指数板 ZS）+ 成分股。
// 返回 (blocks, constituents)。
//
// blocks.Type 用 model.BlockConcept/Region/Style/Index；通达信原始 fileType 没有"地域"独立分类，
// 这里用规则切分：FG 文件里 Name 含"地域"或常见省份名 → region，其余 → style。
func (c *Client) ListBlocks() ([]*model.Block, []*model.BlockConstituent, error) {
	cli, err := c.Raw()
	if err != nil {
		return nil, nil, err
	}

	files := []struct {
		File    string
		Default string
	}{
		{protocol.BlockFileGN, model.BlockConcept},
		{protocol.BlockFileFG, model.BlockStyle},
		{protocol.BlockFileZS, model.BlockIndex},
	}

	blocks := make([]*model.Block, 0, 600)
	cons := make([]*model.BlockConstituent, 0, 30000)

	for _, f := range files {
		bs, err := cli.GetBlockDataWithIndex(f.File)
		if err != nil {
			return nil, nil, fmt.Errorf("get block %s: %w", f.File, err)
		}
		for _, b := range bs {
			code := b.Index
			if code == "" {
				// 没有指数代码的板块跳过（通常是历史遗留分组）
				continue
			}
			blocks = append(blocks, &model.Block{
				Code:       code,
				Name:       b.Name,
				Type:       f.Default,
				StockCount: uint32(len(b.Codes)),
			})
			for _, sc := range b.Codes {
				if len(sc) >= 7 {
					sc = sc[1:] // 通达信成分代码首字符是市场标志（1=沪 0=深），去掉
				}
				cons = append(cons, &model.BlockConstituent{
					BlockCode: code,
					StockCode: sc,
				})
			}
		}
	}

	return blocks, cons, nil
}
