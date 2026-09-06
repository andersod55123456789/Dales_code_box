#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="/home/dell/Oil_Cool_Compute/Phase_2"
RUN_DIR="${BASE_DIR}/test_runs/12h_20260905"
mkdir -p "${RUN_DIR}"

for run_number in 1 2 3 4; do
  echo "$(date --iso-8601=seconds) starting 3-hour block ${run_number}"
  OIL_TEST_IDLE_SECONDS=0 \
  OIL_TEST_STRESS_SECONDS=10800 \
  OIL_TEST_INTERVAL_SECONDS=30 \
    python3 "${BASE_DIR}/run_staged_test.py" \
    "${RUN_DIR}/block_${run_number}.csv"
  echo "$(date --iso-8601=seconds) completed 3-hour block ${run_number}"
done

echo "$(date --iso-8601=seconds) 12-hour test complete"
