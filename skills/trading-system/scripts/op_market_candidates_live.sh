#!/bin/bash
# op_market_candidates_live.sh — 全主板无方向异动候选（候选不是龙头）

set -euo pipefail

ASTOCK="${ASTOCK_BIN:-}"
if [ -z "$ASTOCK" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
    ASTOCK="$PROJECT_ROOT/astock/astock"
fi

JSON=$("$ASTOCK" live market --limit 50 --sort amount --market all --json 2>/dev/null) || {
    echo "=== $(date +%H:%M:%S) 全市场异动扫描失败 ==="
    exit 1
}

RETURNED=$(echo "$JSON" | jq -r '.returned // 0')
if [ "$RETURNED" -eq 0 ] 2>/dev/null; then
    echo "=== $(date +%H:%M:%S) 全市场异动扫描数据为空 ==="
    exit 1
fi

echo "$JSON" | jq -r '
    "扫描: \(.returned)只 by=\(.sort) 耗时:\(.elapsed_ms)ms",
    "--- 异动候选(非涨停·按成交额排序) ---",
    (.rows[] | select(.state != "limit-up" and .state != "limit-down") |
      "  \(.market) \(.code) \(.name) " +
      "\(.change_pct | if . >= 0 then "+\((. * 100 | round) / 100)" else "\((. * 100 | round) / 100)" end)% " +
      "成交:\((.amount / 100000000 * 10 | round) / 10)亿 " +
      "振幅:\((.amplitude_pct * 100 | round) / 100)% " +
      "涨速:\((.rise_speed * 100 | round) / 100) " +
      "\(.state)")
'

echo "→ 候选仅触发搜索归因；找到具体预期并验证核心关联股成片上涨后，才能确认龙头和买入"
