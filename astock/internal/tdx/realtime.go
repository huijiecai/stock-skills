package tdx

import (
	"fmt"

	"github.com/huijiecai/stock/astock/internal/model"
)

// IsRealtimeNow 判断当前 TDX 是否能拿到"今日"实时数据。
//
// 实现策略：拉 sh000001 上证综指当日分时（GetMinute）—— 分时为空 ⇒ 今日尚未开盘
// （非交易日 / 盘前 9:30 前）；非空 ⇒ 已开盘（盘中或盘后），可以拉实时报价。
//
// 用途：所有 live * 命令在拉数据前调用一次，非交易日直接拒绝，避免把上个交易日的快照
// 当作"今日实时"返回，混淆复盘与盘中决策。
//
// 返回：
//
//	ok=true  —— 当下可拉实时（盘中或盘后当日数据）
//	ok=false —— 拒绝；reason 给出可读原因（已传给 CLI 输出）
func (c *Client) IsRealtimeNow() (ok bool, reason string, err error) {
	ticks, err := c.GetMinute("000001", model.TypeIndex)
	if err != nil {
		return false, "", fmt.Errorf("守门员探测失败: %w", err)
	}
	if len(ticks) == 0 {
		return false, "今日无分时数据（非交易日或盘前 9:30 之前），live 拒绝返回历史快照", nil
	}
	return true, fmt.Sprintf("已收到 %d 个分时点", len(ticks)), nil
}
