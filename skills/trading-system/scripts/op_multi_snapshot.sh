#!/bin/bash
# op_multi_snapshot.sh — 多股快照（模拟看盘）
# 从历史分钟K线提取指定时间点的多只股票数据
#
# 用法: op_multi_snapshot.sh <codes> <date YYYYMMDD> <time HH:MM>
# 示例: op_multi_snapshot.sh 002185,600584,002156 20260709 10:04
#
# 输出:
#   === 2026-07-09 10:04 多股快照 ===
#   代码    名称        前收    收盘    涨幅%    成交量
#   002185  华天科技    21.57   23.28   +7.92%   199208
#   600584  长电科技    94.11   96.24   +2.27%   45200
#   002156  通富微电    65.60   66.31   +1.08%   38900

set -euo pipefail

ASTOCK="${ASTOCK_BIN:-./astock/astock}"

CODES="${1:?用法: op_multi_snapshot.sh <codes> <date YYYYMMDD> <time HH:MM>}"
DATE="${2:?用法: op_multi_snapshot.sh <codes> <date YYYYMMDD> <time HH:MM>}"
TIME="${3:?用法: op_multi_snapshot.sh <codes> <date YYYYMMDD> <time HH:MM>}"

DATE_FMT="${DATE:0:4}-${DATE:4:2}-${DATE:6:2}"

printf "=== %s %s 多股快照 ===\n" "$DATE_FMT" "$TIME"
printf "%-8s %-12s %10s %10s %8s %12s\n" "代码" "名称" "前收" "收盘" "涨幅%" "成交量"

# 逗号分隔的代码拆分成数组
IFS=',' read -ra CODE_ARRAY <<< "$CODES"

for CODE in "${CODE_ARRAY[@]}"; do
    CODE=$(echo "$CODE" | xargs)  # 去空格

    # 获取股票名称
    NAME=$("$ASTOCK" query stock --keyword "$CODE" --json 2>/dev/null | jq -r '.[0].name // "?"' 2>/dev/null) || NAME="?"

    # 获取分钟K线，提取指定时间的close和volume
    MINUTE_JSON=$("$ASTOCK" query kline "$CODE" --freq 1m --date "$DATE" --json --no-sync 2>/dev/null) || {
        printf "%-8s %-12s %10s %10s %8s %12s\n" "$CODE" "$NAME" "-" "-" "无数据" "-"
        continue
    }

    # 检查是否是有效JSON
    if ! echo "$MINUTE_JSON" | jq -e 'type == "array"' >/dev/null 2>&1; then
        printf "%-8s %-12s %10s %10s %8s %12s\n" "$CODE" "$NAME" "-" "-" "无数据" "-"
        continue
    fi

    # 提取指定时间的close和volume
    CLOSE=$(echo "$MINUTE_JSON" | jq -r ".[] | select(.time | endswith(\" $TIME\")) | .close" 2>/dev/null)
    VOLUME=$(echo "$MINUTE_JSON" | jq -r ".[] | select(.time | endswith(\" $TIME\")) | .volume" 2>/dev/null)

    if [ -z "$CLOSE" ] || [ "$CLOSE" = "null" ]; then
        printf "%-8s %-12s %10s %10s %8s %12s\n" "$CODE" "$NAME" "-" "-" "无该时间" "-"
        continue
    fi

    # 获取日K线的pre_close
    DAILY_JSON=$("$ASTOCK" query kline "$CODE" --freq daily --from "$DATE" --to "$DATE" --json 2>/dev/null) || {
        printf "%-8s %-12s %10s %10.2f %8s %12s\n" "$CODE" "$NAME" "-" "$CLOSE" "-" "$VOLUME"
        continue
    }

    PRE_CLOSE=$(echo "$DAILY_JSON" | jq -r '.[0].pre_close // empty' 2>/dev/null)

    if [ -z "$PRE_CLOSE" ] || [ "$PRE_CLOSE" = "null" ]; then
        printf "%-8s %-12s %10s %10.2f %8s %12s\n" "$CODE" "$NAME" "-" "$CLOSE" "-" "$VOLUME"
        continue
    fi

    # 计算涨跌幅
    PCT=$(awk "BEGIN { printf \"%+.2f\", ($CLOSE - $PRE_CLOSE) / $PRE_CLOSE * 100 }")

    printf "%-8s %-12s %10.2f %10.2f %7s%% %12s\n" "$CODE" "$NAME" "$PRE_CLOSE" "$CLOSE" "$PCT" "$VOLUME"
done
