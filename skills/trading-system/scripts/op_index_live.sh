#!/bin/bash
# op_index_live.sh — 指数概览（真实看盘）
# 从TDX实时分时获取4大指数最新价格
#
# 用法: op_index_live.sh
# 示例: op_index_live.sh
#
# 输出:
#   === 20:21:40 指数概览（实时） ===
#   指数        前收      当前      涨跌幅
#   上证指数    3970.88   3970.55   -0.01%
#   深证成指    ...       ...       ...
#   科创50      ...       ...       ...
#   创业板指    ...       ...       ...

set -euo pipefail

# 查找 astock 二进制：优先 ASTOCK_BIN，其次脚本相对路径
ASTOCK="${ASTOCK_BIN:-}"
if [ -z "$ASTOCK" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
    ASTOCK="$PROJECT_ROOT/astock/astock"
fi

# 指数代码:名称:type参数
# 000001/000688 需 --type index 解决代码歧义
# 399001/399006 自动识别为指数
INDICES=("000001:上证指数:index" "399001:深证成指:auto" "000688:科创50:index" "399006:创业板指:auto")

NOW=$(date "+%H:%M:%S")
printf "=== %s 指数概览（实时） ===\n" "$NOW"
printf "%-12s %12s %12s %8s\n" "指数" "前收" "当前" "涨跌幅"

for entry in "${INDICES[@]}"; do
    CODE="${entry%%:*}"
    REST="${entry#*:}"
    NAME="${REST%%:*}"
    TYPE_FLAG="${REST##*:}"

    # 获取实时分时数据
    if [ "$TYPE_FLAG" = "index" ]; then
        MINUTE_JSON=$("$ASTOCK" live minute "$CODE" --type index --json 2>/dev/null) || {
            printf "%-12s %12s %12s %8s\n" "$NAME" "-" "-" "无数据"
            continue
        }
    else
        MINUTE_JSON=$("$ASTOCK" live minute "$CODE" --json 2>/dev/null) || {
            printf "%-12s %12s %12s %8s\n" "$NAME" "-" "-" "无数据"
            continue
        }
    fi

    # 取最后一根分钟bar的price作为当前价
    CLOSE=$(echo "$MINUTE_JSON" | jq -r '.[-1].price // empty' 2>/dev/null)

    if [ -z "$CLOSE" ] || [ "$CLOSE" = "null" ]; then
        printf "%-12s %12s %12s %8s\n" "$NAME" "-" "-" "无数据"
        continue
    fi

    # 获取日K线的pre_close（取最新一条）
    DAILY_JSON=$("$ASTOCK" query kline "$CODE" --freq daily --limit 1 --type index --json 2>/dev/null) || {
        printf "%-12s %12s %12.2f %8s\n" "$NAME" "-" "$CLOSE" "-"
        continue
    }

    # 最新日K可能是今天（有pre_close）或昨天（close即今天的pre_close）
    TRADE_DATE=$(echo "$DAILY_JSON" | jq -r '.[0].trade_date // empty' 2>/dev/null)
    TODAY=$(date "+%Y-%m-%d")

    if [ "$TRADE_DATE" = "$TODAY" ]; then
        # 今天的日K，pre_close是昨收
        PRE_CLOSE=$(echo "$DAILY_JSON" | jq -r '.[0].pre_close // empty' 2>/dev/null)
    else
        # 昨天的日K，close是今天的pre_close
        PRE_CLOSE=$(echo "$DAILY_JSON" | jq -r '.[0].close // empty' 2>/dev/null)
    fi

    if [ -z "$PRE_CLOSE" ] || [ "$PRE_CLOSE" = "null" ]; then
        printf "%-12s %12s %12.2f %8s\n" "$NAME" "-" "$CLOSE" "-"
        continue
    fi

    # 计算涨跌幅
    PCT=$(awk "BEGIN { printf \"%+.2f\", ($CLOSE - $PRE_CLOSE) / $PRE_CLOSE * 100 }")

    printf "%-12s %12.2f %12.2f %7s%%\n" "$NAME" "$PRE_CLOSE" "$CLOSE" "$PCT"
done
