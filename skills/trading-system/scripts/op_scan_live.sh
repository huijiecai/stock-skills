#!/bin/bash
# op_scan_live.sh — 一键4步快扫（真实看盘）
# 合并指数、持仓、无方向异动候选、板块强度为1次Bash调用
#
# 用法: op_scan_live.sh <holdings_codes>；空仓传 -
# 示例: op_scan_live.sh 002185
#        op_scan_live.sh 002185,002156

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CODES="${1:?用法: op_scan_live.sh <holdings_codes>；空仓传 ->}"

echo "========== 快扫 $(date +%H:%M:%S) =========="
echo ""

echo "--- ① 指数 ---"
bash "$SCRIPT_DIR/op_index_live.sh" 2>/dev/null || echo "指数数据获取失败"
echo ""

echo "--- ② 持仓 ---"
bash "$SCRIPT_DIR/op_holdings_live.sh" "$CODES" 2>/dev/null || echo "持仓数据获取失败"
echo ""

echo "--- ③ 无方向异动候选 ---"
bash "$SCRIPT_DIR/op_market_candidates_live.sh" 2>/dev/null || echo "全主板异动候选获取失败"
echo ""

echo "--- ④ 板块 ---"
bash "$SCRIPT_DIR/op_sector_rank_live.sh" 2>/dev/null || echo "板块数据获取失败"
echo ""

echo "========== 快扫结束 =========="
