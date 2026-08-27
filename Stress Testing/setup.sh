#!/usr/bin/env bash
# setup.sh - one-time setup for the Optiplex 990 stress test
# Run with: sudo ./setup.sh

set -e

if [ "$EUID" -ne 0 ]; then
    echo "Please run as root: sudo ./setup.sh"
    exit 1
fi

echo "== Updating package lists =="
apt-get update

echo "== Installing stress-ng, lm-sensors, python3, and turbostat (linux-tools) =="
apt-get install -y stress-ng lm-sensors python3 python3-pip \
    linux-tools-common linux-tools-generic "linux-tools-$(uname -r)" || \
    apt-get install -y linux-tools-generic

echo "== Detecting sensors (auto-answering yes to all prompts) =="
yes | sensors-detect --auto || true

echo "== Loading detected sensor kernel modules now (no reboot needed) =="
# sensors-detect appends modules to /etc/modules; load them immediately too
if [ -f /etc/modules ]; then
    while read -r mod; do
        case "$mod" in
            \#*|"") continue ;;
        esac
        modprobe "$mod" 2>/dev/null || true
    done < /etc/modules
fi

echo "== Quick sensor check =="
sensors || echo "WARNING: 'sensors' returned nothing yet - a reboot may be required for full detection."

echo "== Quick turbostat check (requires root) =="
turbostat --quiet --num_iterations 1 -- sleep 1 || echo "WARNING: turbostat did not run cleanly - check dmesg for RAPL/MSR errors."

echo
echo "Setup complete."
echo "If 'sensors' showed no output above, reboot once (sudo reboot) and re-run 'sensors' to confirm before starting the test."
