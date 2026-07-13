#!/bin/bash
# op_holdings_live.sh — 持仓实时快照（真实看盘快扫①）
# 只输出价格/涨跌幅/>2%标记，不输出五档盘口
# 设计目的：判断"涨跌幅>2%？是否触发§4.1评估？"，不是盯价格
#
# 用法: op_holdings_live.sh <code1>[,code2,...]
# 示例: op_holdings_live.sh 002185
#        op_holdings_live.sh 002185,002156

set -euo pipefail

# 查找 astock 二进制：优先 ASTOCK_BIN，其次脚本相对路径
ASTOCK="${ASTOCK_BIN:-}"
if [ -z "$ASTOCK" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
    ASTOCK="$PROJECT_ROOT/astock/astock"
fi

CODES="${1:?用法: op_holdings_live.sh <code1>[,code2,...>}"

NOW=$(date "+%H:%M:%S")
printf "=== %s 持仓快照（实时·①判断） ===\n" "$NOW"
printf "%-8s %10s %8s %6s\n" "代码" "现价" "涨跌%" ">2%?"

# 逗号分隔的代码拆分成数组
IFS=',' read -ra CODE_ARRAY <<< "$CODES"
for CODE in "${CODE_ARRAY[@]}"; do
    CODE=$(echo "$CODE" | xargs)

    JSON=$("$ASTOCK" live quote "$CODE" --json 2>/dev/null) || {
        printf "%-8s %10s %8s %6s\n" "$CODE" "无数据" "-" "-"
        continue
    }

    PRICE=$(echo "$JSON" | jq -r '.[0].price // 0' 2>/dev/null)
    PCT=$(echo "$JSON" | jq -r '.[0].change_pct // 0' 2>/dev/null)

    # 判断是否 |涨跌幅| > 2%
    FLAG=$(awk -v pct="$PCT" 'BEGIN {
        if (pct > 2 || pct < -2) print "⚠️是"
        else print "否"
    }')

    printf "%-8s %10.2f %+7.2f%% %6s\n" "$CODE" "$PRICE" "$PCT" "$FLAG"
done

echo ""
echo "→ ①判断：>2%→触发§4.1评估；≤2%→秒过"
