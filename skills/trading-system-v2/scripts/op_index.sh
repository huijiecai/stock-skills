#!/bin/bash
# op_index.sh — 指数概览（模拟看盘）
# 从历史分钟K线提取指定时间点的指数数据
#
# 用法: op_index.sh <date YYYYMMDD> <time HH:MM>
# 示例: op_index.sh 20260709 10:04
#
# 输出:
#   === 2026-07-09 10:04 指数概览 ===
#   指数        前收      当前      涨跌幅
#   上证指数    3970.88   4015.22   +1.12%
#   深证成指    ...       ...       ...
#   科创50      ...       ...       ...
#   创业板指    ...       ...       ...

set -euo pipefail

ASTOCK="${ASTOCK_BIN:-./astock/astock}"

DATE="${1:?用法: op_index.sh <date YYYYMMDD> <time HH:MM>}"
TIME="${2:?用法: op_index.sh <date YYYYMMDD> <time HH:MM>}"

# 格式化日期显示
DATE_FMT="${DATE:0:4}-${DATE:4:2}-${DATE:6:2}"

# 指数代码与名称
INDICES=("000001:上证指数" "399001:深证成指" "000688:科创50" "399006:创业板指")

printf "=== %s %s 指数概览 ===\n" "$DATE_FMT" "$TIME"
printf "%-12s %12s %12s %8s\n" "指数" "前收" "当前" "涨跌幅"

for entry in "${INDICES[@]}"; do
    CODE="${entry%%:*}"
    NAME="${entry##*:}"

    # 获取分钟K线，提取指定时间的close
    MINUTE_JSON=$("$ASTOCK" query kline "$CODE" --freq 1m --date "$DATE" --type index --json --no-sync 2>/dev/null) || {
        printf "%-12s %12s %12s %8s\n" "$NAME" "-" "-" "无数据"
        continue
    }

    # 检查是否是有效JSON
    if ! echo "$MINUTE_JSON" | jq -e 'type == "array"' >/dev/null 2>&1; then
        printf "%-12s %12s %12s %8s\n" "$NAME" "-" "-" "无数据"
        continue
    fi

    CLOSE=$(echo "$MINUTE_JSON" | jq -r ".[] | select(.time | endswith(\" $TIME\")) | .close" 2>/dev/null)

    if [ -z "$CLOSE" ] || [ "$CLOSE" = "null" ]; then
        printf "%-12s %12s %12s %8s\n" "$NAME" "-" "-" "无该时间"
        continue
    fi

    # 获取日K线的pre_close
    DAILY_JSON=$("$ASTOCK" query kline "$CODE" --freq daily --from "$DATE" --to "$DATE" --type index --json 2>/dev/null) || {
        printf "%-12s %12s %12.2f %8s\n" "$NAME" "-" "$CLOSE" "-"
        continue
    }

    PRE_CLOSE=$(echo "$DAILY_JSON" | jq -r '.[0].pre_close // empty' 2>/dev/null)

    if [ -z "$PRE_CLOSE" ] || [ "$PRE_CLOSE" = "null" ]; then
        printf "%-12s %12s %12.2f %8s\n" "$NAME" "-" "$CLOSE" "-"
        continue
    fi

    # 计算涨跌幅
    PCT=$(awk "BEGIN { printf \"%+.2f\", ($CLOSE - $PRE_CLOSE) / $PRE_CLOSE * 100 }")

    printf "%-12s %12.2f %12.2f %7s%%\n" "$NAME" "$PRE_CLOSE" "$CLOSE" "$PCT"
done
