#!/usr/bin/env bash
# stress_test.sh - 24 hour CPU stress test with 3-hour ramp cycles
#
# Cycle shape (repeats every 3 hours, for 8 cycles = 24 hours):
#   Hour 1: ~25% of cores
#   Hour 2: ~65% of cores
#   Hour 3: 100% of cores  <-- max load
# Then it restarts back at ~25% for the next cycle.
#
# Also launches logger.py in the background to record sensors/turbostat
# data every 10 minutes to a CSV file for the full 24 hours.
#
# Run with: sudo ./stress_test.sh [output_csv]

set -e

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo ./stress_test.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_CSV="${1:-$SCRIPT_DIR/stress_test_log_$(date +%Y%m%d_%H%M%S).csv}"

TOTAL_HOURS=24
CYCLE_HOURS=3
NUM_CYCLES=$((TOTAL_HOURS / CYCLE_HOURS))   # 8 cycles

NPROC=$(nproc)
PHASE1_CORES=$(( NPROC / 4 ))
[ "$PHASE1_CORES" -lt 1 ] && PHASE1_CORES=1
PHASE2_CORES=$(( NPROC * 65 / 100 ))
[ "$PHASE2_CORES" -lt 1 ] && PHASE2_CORES=1
PHASE3_CORES=$NPROC

PHASE_SECONDS=$((60 * 60))  # 1 hour per phase

echo "Detected $NPROC logical CPUs."
echo "Ramp phases per 3-hour cycle: ${PHASE1_CORES} -> ${PHASE2_CORES} -> ${PHASE3_CORES} cores"
echo "Total run time: ${TOTAL_HOURS}h across ${NUM_CYCLES} cycles"
echo "Logging to: $OUTPUT_CSV"
echo

# --- Start the logger in the background ---
LOGGER_PID=""
cleanup() {
    echo
    echo "Stopping stress test..."
    if [ -n "$LOGGER_PID" ] && kill -0 "$LOGGER_PID" 2>/dev/null; then
        kill "$LOGGER_PID" 2>/dev/null || true
    fi
    # Kill any stress-ng still running that this script started
    pkill -P $$ stress-ng 2>/dev/null || true
    echo "Stopped. Log file: $OUTPUT_CSV"
}
trap cleanup EXIT INT TERM

python3 "$SCRIPT_DIR/logger.py" "$OUTPUT_CSV" "$TOTAL_HOURS" 10 &
LOGGER_PID=$!
echo "Logger started (PID $LOGGER_PID)"
echo

# --- Run the ramp cycles ---
for cycle in $(seq 1 "$NUM_CYCLES"); do
    echo "=== Cycle $cycle/$NUM_CYCLES ==="

    echo "[$(date)] Phase 1/3: $PHASE1_CORES cores for 1 hour"
    stress-ng --cpu "$PHASE1_CORES" --cpu-method matrixprod --timeout "${PHASE_SECONDS}s" --metrics-brief

    echo "[$(date)] Phase 2/3: $PHASE2_CORES cores for 1 hour"
    stress-ng --cpu "$PHASE2_CORES" --cpu-method matrixprod --timeout "${PHASE_SECONDS}s" --metrics-brief

    echo "[$(date)] Phase 3/3: $PHASE3_CORES cores (max) for 1 hour"
    stress-ng --cpu "$PHASE3_CORES" --cpu-method matrixprod --timeout "${PHASE_SECONDS}s" --metrics-brief
done

echo "All $NUM_CYCLES cycles complete."

# Let the logger finish its full 24h window / catch the last sample, then exit
wait "$LOGGER_PID" 2>/dev/null || true
