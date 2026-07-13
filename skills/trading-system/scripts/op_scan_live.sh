#!/bin/bash
# op_scan_live.sh — 一键3步快扫（真实看盘）
# 合并 op_index_live + op_holdings_live + op_sector_rank_live 为1次Bash调用
# 设计目的：解决"超预算调用工具"——1次调用完成3步快扫
#
# 用法: op_scan_live.sh <holdings_codes>
# 示例: op_scan_live.sh 002185
#        op_scan_live.sh 002185,002156

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CODES="${1:?用法: op_scan_live.sh <holdings_codes>}"

echo "========== 快扫 $(date +%H:%M:%S) =========="
echo ""

echo "--- ① 指数 ---"
bash "$SCRIPT_DIR/op_index_live.sh" 2>/dev/null || echo "指数数据获取失败"
echo ""

echo "--- ② 持仓 ---"
bash "$SCRIPT_DIR/op_holdings_live.sh" "$CODES" 2>/dev/null || echo "持仓数据获取失败"
echo ""

echo "--- ③ 板块 ---"
bash "$SCRIPT_DIR/op_sector_rank_live.sh" 2>/dev/null || echo "板块数据获取失败"
echo ""

echo "========== 快扫结束 =========="
