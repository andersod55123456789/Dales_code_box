#!/usr/bin/env python3
import csv
import glob
import os
import re
import select
import signal
import struct
import subprocess
import sys
import termios
import threading
import time
from datetime import datetime, timezone

UNO_PORT = "/dev/ttyUSB0"
PZEM_PORT = "/dev/ttyUSB1"
INTERVAL_SECONDS = int(os.environ.get("OIL_TEST_INTERVAL_SECONDS", 5))
IDLE_SECONDS = int(os.environ.get("OIL_TEST_IDLE_SECONDS", 10 * 60))
STRESS_SECONDS = int(os.environ.get("OIL_TEST_STRESS_SECONDS", 15 * 60))
MAX_TEMP_C = 80.0

PROBES = {
    "283B142600000011": "pink_pump_intake",
    "28ABE4000000007F": "orange_radiator_return",
    "28C5E000000000B0": "yellow_computer_center",
    "282AE225000000CF": "blue_bulk_oil",
    "28EDCD2500000042": "black_ambient",
}


def configure_serial(path):
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    attrs = termios.tcgetattr(fd)
    attrs[0] = attrs[1] = attrs[3] = 0
    attrs[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
    attrs[4] = attrs[5] = termios.B9600
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 10
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    termios.tcflush(fd, termios.TCIOFLUSH)
    return fd


def crc16(data):
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def read_pzem(fd):
    request = bytes.fromhex("f8040000000a6464")
    termios.tcflush(fd, termios.TCIOFLUSH)
    os.write(fd, request)
    deadline = time.time() + 2.0
    data = b""
    while time.time() < deadline and len(data) < 25:
        ready, _, _ = select.select([fd], [], [], deadline - time.time())
        if not ready:
            break
        data += os.read(fd, 256)
    if len(data) != 25 or data[:3] != bytes.fromhex("f80414"):
        raise RuntimeError("invalid PZEM response")
    if crc16(data[:-2]) != int.from_bytes(data[-2:], "little"):
        raise RuntimeError("PZEM CRC failure")
    regs = struct.unpack(">10H", data[3:23])
    return {
        "voltage_v": regs[0] / 10,
        "current_a": ((regs[2] << 16) | regs[1]) / 1000,
        "power_w": ((regs[4] << 16) | regs[3]) / 10,
        "energy_wh": (regs[6] << 16) | regs[5],
        "frequency_hz": regs[7] / 10,
        "power_factor": regs[8] / 100,
    }


class UnoReader(threading.Thread):
    pattern = re.compile(r"address=([0-9A-F]{16}) temp_c=([-0-9.]+)")

    def __init__(self):
        super().__init__(daemon=True)
        self.values = {}
        self.lock = threading.Lock()
        self.fd = configure_serial(UNO_PORT)

    def run(self):
        buffer = b""
        while True:
            ready, _, _ = select.select([self.fd], [], [], 1.0)
            if not ready:
                continue
            buffer += os.read(self.fd, 1024)
            while b"\n" in buffer:
                raw, buffer = buffer.split(b"\n", 1)
                match = self.pattern.search(raw.decode(errors="replace"))
                if match and match.group(1) in PROBES:
                    with self.lock:
                        self.values[PROBES[match.group(1)]] = float(match.group(2))

    def snapshot(self):
        with self.lock:
            return dict(self.values)


def cpu_times():
    fields = [int(x) for x in open("/proc/stat").readline().split()[1:]]
    return sum(fields), fields[3] + fields[4]


def cpu_temp():
    values = []
    for path in glob.glob("/sys/class/hwmon/hwmon*/temp*_input"):
        try:
            value = float(open(path).read().strip()) / 1000
            if 0 < value < 150:
                values.append(value)
        except (OSError, ValueError):
            pass
    return max(values) if values else None


def main():
    output = sys.argv[1] if len(sys.argv) > 1 else "staged_test.csv"
    uno = UnoReader()
    uno.start()
    pzem_fd = configure_serial(PZEM_PORT)
    previous_total, previous_idle = cpu_times()
    stress = None
    safety_stopped = False
    start = time.monotonic()
    fieldnames = [
        "timestamp_utc", "phase", "elapsed_s", "cpu_load_pct", "cpu_temp_c",
        *PROBES.values(), "radiator_delta_c", "computer_bulk_delta_c",
        "bulk_ambient_delta_c", "voltage_v", "current_a", "power_w",
        "energy_wh", "frequency_hz", "power_factor", "safety_status",
    ]
    try:
        with open(output, "w", newline="", buffering=1) as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            while True:
                elapsed = time.monotonic() - start
                if elapsed >= IDLE_SECONDS and stress is None:
                    stress = subprocess.Popen([
                        "stress-ng", "--cpu", "4", "--timeout", f"{STRESS_SECONDS}s",
                        "--metrics-brief",
                    ])
                    print("PHASE CHANGE: full CPU stress started", flush=True)
                phase = "idle" if elapsed < IDLE_SECONDS else "stress"
                if elapsed >= IDLE_SECONDS + STRESS_SECONDS:
                    break

                total, idle = cpu_times()
                total_delta, idle_delta = total - previous_total, idle - previous_idle
                load = 100 * (1 - idle_delta / total_delta) if total_delta else 0
                previous_total, previous_idle = total, idle
                temps = uno.snapshot()
                try:
                    power = read_pzem(pzem_fd)
                except RuntimeError as error:
                    print(f"PZEM warning: {error}", file=sys.stderr, flush=True)
                    power = {key: "" for key in ("voltage_v", "current_a", "power_w", "energy_wh", "frequency_hz", "power_factor")}
                core = cpu_temp()
                measured = [value for name, value in temps.items() if name != "black_ambient"]
                unsafe = (core is not None and core >= MAX_TEMP_C) or any(value >= MAX_TEMP_C for value in measured)
                row = {
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "phase": phase,
                    "elapsed_s": round(elapsed, 1),
                    "cpu_load_pct": round(load, 1),
                    "cpu_temp_c": "" if core is None else round(core, 2),
                    **temps,
                    **power,
                    "radiator_delta_c": round(temps["pink_pump_intake"] - temps["orange_radiator_return"], 3) if "pink_pump_intake" in temps and "orange_radiator_return" in temps else "",
                    "computer_bulk_delta_c": round(temps["yellow_computer_center"] - temps["blue_bulk_oil"], 3) if "yellow_computer_center" in temps and "blue_bulk_oil" in temps else "",
                    "bulk_ambient_delta_c": round(temps["blue_bulk_oil"] - temps["black_ambient"], 3) if "blue_bulk_oil" in temps and "black_ambient" in temps else "",
                    "safety_status": "STOP_80C" if unsafe else "OK",
                }
                writer.writerow(row)
                print(f"{phase:6} t={elapsed:5.0f}s load={load:5.1f}% cpu={core}C power={power['power_w']}W temps={temps}", flush=True)
                if unsafe:
                    print("SAFETY STOP: temperature reached 80 C", flush=True)
                    safety_stopped = True
                    break
                time.sleep(INTERVAL_SECONDS)
    finally:
        if stress is not None and stress.poll() is None:
            stress.send_signal(signal.SIGINT)
            try:
                stress.wait(timeout=10)
            except subprocess.TimeoutExpired:
                stress.kill()
        os.close(pzem_fd)
    print(f"TEST COMPLETE: {output}", flush=True)
    return 2 if safety_stopped else 0


if __name__ == "__main__":
    sys.exit(main())
