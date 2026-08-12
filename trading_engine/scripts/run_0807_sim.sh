#!/usr/bin/env bash
# 0807 全天逐5分钟模拟看盘 - DeepSeek LLM 作为 brain
# 用法: TRADER_LLM_API_KEY=xxx ./run_0807_sim.sh
set -uo pipefail   # no -e: we handle errors per-step
cd "$(dirname "$0")/../.."   # repo root (where `trader` lives)

DATE=20260807
LOG=trading_engine/data/sim_0807_log.txt
SUMMARY=trading_engine/data/sim_0807_summary.txt

# 上午 09:31-11:30, 下午 13:01-15:00, 每5分钟
TIMES=(
  09:31 09:36 09:41 09:46 09:51 09:56
  10:01 10:06 10:11 10:16 10:21 10:26 10:31 10:36 10:41 10:46 10:51 10:56
  11:01 11:06 11:11 11:16 11:21 11:26
  13:01 13:06 13:11 13:16 13:21 13:26 13:31 13:36 13:41 13:46 13:51 13:56
  14:01 14:06 14:11 14:16 14:21 14:26 14:31 14:36 14:41 14:46 14:51 14:56
  15:00
)

export TRADER_LLM_API_KEY="${TRADER_LLM_API_KEY:?TRADER_LLM_API_KEY required}"
export TRADER_LLM_PROVIDER=deepseek

echo "=== 0807 模拟看盘启动 $(date '+%Y-%m-%d %H:%M:%S') ===" | tee "$LOG"
echo "总轮数: ${#TIMES[@]}" | tee -a "$LOG"
echo "" | tee -a "$LOG"

echo "时间|指数摘要|LLM判断|执行结果" > "$SUMMARY"

round=0
for t in "${TIMES[@]}"; do
  round=$((round + 1))
  echo "--- R$round $t ---" | tee -a "$LOG"

  # 1. Build context (replay)
  ctx_output=$(./trader context replay --date "$DATE" --until "$t" 2>&1)
  if [ $? -ne 0 ]; then
    echo "  [CONTEXT ERROR]" | tee -a "$LOG"
    echo "$ctx_output" | tail -3 | tee -a "$LOG"
    echo "$t|CONTEXT_FAIL|-|-" >> "$SUMMARY"
    continue
  fi

  idx_line=$(echo "$ctx_output" | grep -E '^(上证|深证)' | head -1 || true)

  # 2. Analyze (deepseek)
  judge_output=$(./trader analyze latest --provider deepseek 2>&1)
  if [ $? -ne 0 ]; then
    echo "  [ANALYZE ERROR]" | tee -a "$LOG"
    echo "$judge_output" | tail -3 | tee -a "$LOG"
    echo "$t|$idx_line|ANALYZE_FAIL|-" >> "$SUMMARY"
    continue
  fi

  # Extract non-WAIT or high-confidence judgments
  judge_summary=$(echo "$judge_output" | grep -E 'BUY|SELL|RESEARCH' | head -5 | tr '\n' ';' || true)
  [ -z "$judge_summary" ] && judge_summary="ALL_WAIT"

  # 3. Execute
  exec_output=$(./trader paper execute 2>&1 || true)
  exec_summary=$(echo "$exec_output" | grep -E 'filled|rejected' | head -5 | tr '\n' ';' || true)
  [ -z "$exec_summary" ] && exec_summary="no_trades"

  echo "  指数: $idx_line" | tee -a "$LOG"
  echo "  判断: $judge_summary" | tee -a "$LOG"
  echo "  执行: $exec_summary" | tee -a "$LOG"
  echo "" | tee -a "$LOG"

  echo "$t|$idx_line|$judge_summary|$exec_summary" >> "$SUMMARY"
done

echo "" | tee -a "$LOG"
echo "=== 模拟看盘结束 $(date '+%Y-%m-%d %H:%M:%S') ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"

# Final portfolio
echo "=== 最终持仓 ===" | tee -a "$LOG"
./trader brief >> "$LOG" 2>&1 || true

# Trade summary
echo "" | tee -a "$LOG"
echo "=== 成交记录 ===" | tee -a "$LOG"
./trader paper fills >> "$LOG" 2>&1 || true

echo "" | tee -a "$LOG"
echo "Summary: trading_engine/data/sim_0807_summary.txt"
echo "Log: trading_engine/data/sim_0807_log.txt"
