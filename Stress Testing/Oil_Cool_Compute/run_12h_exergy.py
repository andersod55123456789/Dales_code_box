#!/usr/bin/env python3
import csv
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

import run_staged_test as sensors

INTERVAL_SECONDS = 30
PHASE_SECONDS = 60 * 60
CYCLES = 4
PHASES = [(1, "25pct"), (2, "65pct"), (4, "100pct")]
TOTAL_SECONDS = CYCLES * len(PHASES) * PHASE_SECONDS
MAX_TEMP_C = 80.0
FLOW_LPS = 0.100 / 54.3
OIL_DENSITY_KG_L = 0.85
OIL_CP_J_KG_K = 1970.0
MASS_FLOW_KG_S = FLOW_LPS * OIL_DENSITY_KG_L


def stop_process(process):
    if process is None or process.poll() is not None:
        return
    process.send_signal(signal.SIGINT)
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else "exergy_12h.csv"
    uno = sensors.UnoReader()
    uno.start()
    pzem_fd = sensors.configure_serial(sensors.PZEM_PORT)
    previous_total, previous_idle = sensors.cpu_times()
    stress = None
    active_segment = -1
    safety_stopped = False
    start = time.monotonic()
    fields = [
        "timestamp_utc", "elapsed_s", "cycle", "phase", "stress_cores",
        "cpu_load_pct", "cpu_temp_c", *sensors.PROBES.values(),
        "radiator_delta_c", "radiator_heat_w", "carnot_factor",
        "thermal_exergy_w", "computer_bulk_delta_c", "bulk_ambient_delta_c",
        "voltage_v", "current_a", "power_w", "energy_wh", "frequency_hz",
        "power_factor", "safety_status",
    ]
    try:
        with open(output, "w", newline="", buffering=1) as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            next_sample = start
            while True:
                now = time.monotonic()
                elapsed = now - start
                if elapsed >= TOTAL_SECONDS:
                    break
                segment = int(elapsed // PHASE_SECONDS)
                cycle = segment // len(PHASES) + 1
                phase_index = segment % len(PHASES)
                cores, phase_name = PHASES[phase_index]
                if segment != active_segment:
                    stop_process(stress)
                    print(
                        f"PHASE START cycle={cycle}/{CYCLES} phase={phase_name} cores={cores}",
                        flush=True,
                    )
                    stress = subprocess.Popen([
                        "stress-ng", "--cpu", str(cores), "--cpu-method", "matrixprod",
                        "--timeout", f"{PHASE_SECONDS}s", "--metrics-brief",
                    ])
                    active_segment = segment

                total, idle = sensors.cpu_times()
                total_delta, idle_delta = total - previous_total, idle - previous_idle
                load = 100 * (1 - idle_delta / total_delta) if total_delta else 0
                previous_total, previous_idle = total, idle
                temps = uno.snapshot()
                try:
                    power = sensors.read_pzem(pzem_fd)
                except RuntimeError as error:
                    print(f"PZEM warning: {error}", file=sys.stderr, flush=True)
                    power = {key: "" for key in (
                        "voltage_v", "current_a", "power_w", "energy_wh",
                        "frequency_hz", "power_factor",
                    )}
                core_temp = sensors.cpu_temp()
                pink = temps.get("pink_pump_intake")
                orange = temps.get("orange_radiator_return")
                yellow = temps.get("yellow_computer_center")
                blue = temps.get("blue_bulk_oil")
                ambient = temps.get("black_ambient")
                delta = pink - orange if pink is not None and orange is not None else None
                heat_w = MASS_FLOW_KG_S * OIL_CP_J_KG_K * delta if delta is not None else None
                carnot = 1 - ((ambient + 273.15) / (pink + 273.15)) if ambient is not None and pink is not None else None
                exergy_w = heat_w * carnot if heat_w is not None and carnot is not None else None
                nonambient = [value for name, value in temps.items() if name != "black_ambient"]
                unsafe = ((core_temp is not None and core_temp >= MAX_TEMP_C) or
                          any(value >= MAX_TEMP_C for value in nonambient))
                row = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "elapsed_s": round(elapsed, 1),
                    "cycle": cycle,
                    "phase": phase_name,
                    "stress_cores": cores,
                    "cpu_load_pct": round(load, 1),
                    "cpu_temp_c": "" if core_temp is None else round(core_temp, 2),
                    **temps,
                    "radiator_delta_c": "" if delta is None else round(delta, 3),
                    "radiator_heat_w": "" if heat_w is None else round(heat_w, 3),
                    "carnot_factor": "" if carnot is None else round(carnot, 6),
                    "thermal_exergy_w": "" if exergy_w is None else round(exergy_w, 3),
                    "computer_bulk_delta_c": "" if yellow is None or blue is None else round(yellow - blue, 3),
                    "bulk_ambient_delta_c": "" if blue is None or ambient is None else round(blue - ambient, 3),
                    **power,
                    "safety_status": "STOP_80C" if unsafe else "OK",
                }
                writer.writerow(row)
                print(
                    f"cycle={cycle} phase={phase_name} t={elapsed:.0f}s "
                    f"load={load:.1f}% cpu={core_temp}C power={power['power_w']}W "
                    f"heat={heat_w}W exergy={exergy_w}W",
                    flush=True,
                )
                if unsafe:
                    print("SAFETY STOP: temperature reached 80 C", flush=True)
                    safety_stopped = True
                    break
                next_sample += INTERVAL_SECONDS
                time.sleep(max(0, next_sample - time.monotonic()))
    finally:
        stop_process(stress)
        os.close(pzem_fd)
    print(f"TEST COMPLETE: {output}", flush=True)
    return 2 if safety_stopped else 0


if __name__ == "__main__":
    sys.exit(main())
