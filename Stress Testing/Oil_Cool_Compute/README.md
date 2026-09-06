# Oil Cool Compute Test Tools

Instrumented stress testing for the submerged Dell OptiPlex 990.

## Files

- `run_staged_test.py`: synchronized short idle/full-load testing and CSV logging.
- `run_12h_exergy.py`: four repetitions of the original three-hour ramp (1, 2, then 4 CPU cores for one hour each), with 30-second telemetry and exergy calculations.
- `run_12h_test.sh`: legacy flat-load 12-hour launcher retained for reference; do not use for the exergy ramp.
- `restore_dell_after_ubuntu_reload.sh`: restores Ubuntu packages, serial permissions, sensor libraries, and USB-driver configuration.
- `OilCoolSensors.ino`: Arduino Uno firmware for five DS18B20 probes and the DHT11.

## Current measurement baseline

- Uno: `/dev/ttyUSB0`, 9600 baud.
- PZEM-004T: `/dev/ttyUSB1`, Modbus RTU at 9600 baud.
- Installed oil flow: 100 mL in 54.3 seconds = 6.63 L/h.
- Oil density used: 0.85 kg/L.
- Oil specific heat used: 1970 J/(kg K).
- Safety cutoff: 80 C.

Run the 12-hour exergy test from the Dell:

```bash
cd /home/dell/Oil_Cool_Compute/Phase_2
nohup python3 ./run_12h_exergy.py ./test_runs/exergy_ramp_12h.csv \
  > ./test_runs/exergy_ramp_12h.log 2>&1 < /dev/null &
```
