#!/bin/bash
# op_market_candidates_live.sh — 全主板无方向异动候选（候选不是龙头）

set -euo pipefail

ASTOCK="${ASTOCK_BIN:-}"
if [ -z "$ASTOCK" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
    ASTOCK="$PROJECT_ROOT/astock/astock"
fi

JSON=$("$ASTOCK" live market --amount-limit 50 --json 2>/dev/null) || {
    echo "=== $(date +%H:%M:%S) 全主板异动扫描失败 ==="
    exit 1
}

if ! echo "$JSON" | jq -e '.coverage_mode == "all_main_board_snapshot"' >/dev/null 2>&1; then
    echo "=== $(date +%H:%M:%S) 全主板异动扫描数据无效 ==="
    exit 1
fi

echo "$JSON" | jq -r '
    "覆盖: \(.scanned)/\(.universe) 缺失报价:\(.missing_quotes) 失败批次:\(.failed_batches) 候选:\(.candidates|length)",
    (.candidates[0:40][] |
      "  CANDIDATE \(.code) \(.name) \(.change_pct|if . >= 0 then "+\(.)" else tostring end)% " +
      "成交额:\((.amount / 100000000 * 10 | round) / 10)亿 " +
      "低点反转:\((.rebound_pct * 100 | round) / 100)% " +
      "信号:\(.reasons|join("/")) 主营:\(.business // "unknown")")
'

echo "→ 候选仅触发搜索归因；找到具体预期并验证核心关联股成片上涨后，才能确认龙头和买入"
