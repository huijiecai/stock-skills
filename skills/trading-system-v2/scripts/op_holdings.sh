#!/bin/bash
# op_holdings.sh — 持仓快照（模拟看盘）
# 与 op_multi_snapshot.sh 逻辑相同，语义区分：持仓股专用
#
# 用法: op_holdings.sh <codes> <date YYYYMMDD> <time HH:MM>
# 示例: op_holdings.sh 002185,600584 20260709 10:04

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

exec "$SCRIPT_DIR/op_multi_snapshot.sh" "$@"
