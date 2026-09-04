#!/usr/bin/env python3
"""
logger.py - samples every sensor lm-sensors and turbostat can find,
and appends one row every INTERVAL_SECONDS to a CSV file.

Must be run as root (sudo) because turbostat needs MSR/RAPL access.

Usage:
    sudo python3 logger.py [output_csv] [duration_hours] [interval_minutes]

Defaults:
    output_csv       = stress_test_log.csv
    duration_hours    = 24
    interval_minutes  = 10
"""

import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone

OUTPUT_CSV = sys.argv[1] if len(sys.argv) > 1 else "stress_test_log.csv"
DURATION_HOURS = float(sys.argv[2]) if len(sys.argv) > 2 else 24.0
INTERVAL_MINUTES = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0

INTERVAL_SECONDS = INTERVAL_MINUTES * 60
END_TIME = time.time() + DURATION_HOURS * 3600

TURBOSTAT_SAMPLE_SECONDS = 5  # how long turbostat watches to compute one sample


def get_sensors_data():
    """Run `sensors -j` and flatten into a dict of {label: value}."""
    flat = {}
    try:
        out = subprocess.run(
            ["sensors", "-j"], capture_output=True, text=True, timeout=15
        )
        data = json.loads(out.stdout)
    except Exception as e:
        flat["sensors_error"] = str(e)
        return flat

    for chip, chip_data in data.items():
        if not isinstance(chip_data, dict):
            continue
        for feature, feature_data in chip_data.items():
            if not isinstance(feature_data, dict):
                continue
            for subfeat, value in feature_data.items():
                key = f"{chip}:{feature}:{subfeat}"
                flat[key] = value
    return flat


def get_turbostat_data():
    """Run turbostat over a short sleep and parse the summary line."""
    flat = {}
    try:
        proc = subprocess.run(
            [
                "turbostat",
                "--quiet",
                "--Summary",
                "--",
                "sleep",
                str(TURBOSTAT_SAMPLE_SECONDS),
            ],
            capture_output=True,
            text=True,
            timeout=TURBOSTAT_SAMPLE_SECONDS + 15,
        )
        text = proc.stdout if proc.stdout.strip() else proc.stderr
        lines = [l for l in text.strip().splitlines() if l.strip()]
        if len(lines) >= 2:
            headers = lines[0].split("\t")
            values = lines[-1].split("\t")
            for h, v in zip(headers, values):
                flat[f"turbostat:{h.strip()}"] = v.strip()
        else:
            flat["turbostat_error"] = f"Unexpected output: {text[:200]}"
    except Exception as e:
        flat["turbostat_error"] = str(e)
    return flat


def sample():
    row = {"timestamp": datetime.now(timezone.utc).astimezone().isoformat()}
    row.update(get_sensors_data())
    row.update(get_turbostat_data())
    return row


def main():
    if os.geteuid() != 0:
        print("ERROR: this script must be run as root (sudo) so turbostat can read RAPL/MSR data.")
        sys.exit(1)

    print(f"Logging to {OUTPUT_CSV}")
    print(f"Duration: {DURATION_HOURS} hours, interval: {INTERVAL_MINUTES} minutes")

    # Establish a fixed set of fieldnames from a first probe sample so the
    # CSV header stays consistent for the whole run.
    first_row = sample()
    fieldnames = list(first_row.keys())

    file_exists = os.path.exists(OUTPUT_CSV)
    with open(OUTPUT_CSV, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if not file_exists:
            writer.writeheader()
        writer.writerow(first_row)
        f.flush()

        next_sample_time = time.time() + INTERVAL_SECONDS
        while time.time() < END_TIME:
            sleep_for = next_sample_time - time.time()
            if sleep_for > 0:
                time.sleep(sleep_for)
            if time.time() >= END_TIME:
                break

            row = sample()
            # Fill in any keys missing from this sample, drop any new ones
            # that weren't in the original header so the CSV stays aligned.
            writer.writerow(row)
            f.flush()
            print(f"[{row['timestamp']}] logged sample")

            next_sample_time += INTERVAL_SECONDS

    print("Logging complete.")


if __name__ == "__main__":
    main()
