#!/bin/bash
# ⚠️ 已被 astock 取代：`watch -n 300 './astock live quote 002407 002463 ...'`
#    本脚本仅在 astock 不可用时作兜底。优先级详见 SKILL.md 「数据采集工具」章节。
TOOLS_DIR="/Users/huijiecai/Project/stock/skills/trading-system/tools"
LOG_FILE="/Users/huijiecai/Project/stock/skills/trading-system/data/realtime_monitor.log"
echo "=== 实时监控启动 $(date '+%Y-%m-%d %H:%M:%S') ===" > "$LOG_FILE"
while true; do
    echo "" >> "$LOG_FILE"
    echo "--- [$(date '+%H:%M:%S')] ---" >> "$LOG_FILE"
    cd "$TOOLS_DIR"
    python fetch_adata_data.py --realtime 002407 002463 605376 002916 600183 002456 >> "$LOG_FILE" 2>&1
    sleep 300
done
