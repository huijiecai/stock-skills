#!/bin/bash
# op_sector_rank_live.sh — 板块实时强度（真实看盘快扫②）
# 结构化输出：concept方向TOP10 + style方向TOP5 + 涨停方向
# 设计目的：直接回答"哪个方向靠前？涨停是什么方向？"，不需要AI从50行原始数据中提取
#
# 用法: op_sector_rank_live.sh [limit]
# 示例: op_sector_rank_live.sh        # 默认100（足够覆盖concept+style）
#        op_sector_rank_live.sh 200

set -euo pipefail

# 查找 astock 二进制：优先 ASTOCK_BIN，其次脚本相对路径
ASTOCK="${ASTOCK_BIN:-}"
if [ -z "$ASTOCK" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
    ASTOCK="$PROJECT_ROOT/astock/astock"
fi

LIMIT="${1:-100}"

NOW=$(date "+%H:%M:%S")

# 获取全板块实时排名JSON（type=all 包含 concept+style）
JSON=$("$ASTOCK" live block rank --type all --limit "$LIMIT" --json 2>/dev/null) || {
    echo "=== $NOW 板块数据获取失败（非交易日？） ==="
    exit 1
}

# 检查JSON有效性
if ! echo "$JSON" | jq -e 'type == "array"' >/dev/null 2>&1; then
    echo "=== $NOW 板块数据解析失败 ==="
    exit 1
fi

printf "=== %s 板块强度（实时·②判断） ===\n" "$NOW"

# --- concept TOP10（涨幅前10，标注涨停数）---
echo "--- concept TOP10 ---"
echo "$JSON" | jq -r '
    [.[] | select(.block_type == "concept")] |
    sort_by(-.change_pct) |
    .[0:10] |
    .[] |
    "  \(.name)\t\(.change_pct)\t\(.limit_up_count)"
' | awk -F'\t' '{
    pct = $2
    sign = (pct >= 0) ? "+" : ""
    printf "  %-16s %s%6.2f%%  涨停:%d\n", $1, sign, pct, $3
}'

# --- style TOP5 ---
echo ""
echo "--- style TOP5 ---"
echo "$JSON" | jq -r '
    [.[] | select(.block_type == "style")] |
    sort_by(-.change_pct) |
    .[0:5] |
    .[] |
    "  \(.name)\t\(.change_pct)"
' | awk -F'\t' '{
    pct = $2
    sign = (pct >= 0) ? "+" : ""
    printf "  %-16s %s%6.2f%%\n", $1, sign, pct
}'

# --- 涨停方向（limit_up_count > 0 的板块，按涨停数排序）---
echo ""
echo "--- 涨停方向 ---"
LIMIT_UP=$(echo "$JSON" | jq -r '
    [.[] | select(.limit_up_count > 0)] |
    sort_by(-.limit_up_count) |
    .[] |
    "  \(.name)(\(.limit_up_count)涨停·\(.block_type))"
' 2>/dev/null)

if [ -n "$LIMIT_UP" ]; then
    echo "$LIMIT_UP"
else
    echo "  无涨停"
fi

echo ""
echo "→ ②判断：concept方向靠前？涨停方向？→ 信号"
