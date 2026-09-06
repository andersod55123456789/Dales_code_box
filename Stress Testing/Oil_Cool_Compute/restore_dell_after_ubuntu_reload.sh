#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run with: sudo bash $0" >&2
  exit 1
fi

DELL_USER="dell"
DELL_HOME="/home/${DELL_USER}"
LIB_DIR="${DELL_HOME}/Arduino/libraries"

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  arduino arduino-core-avr gcc-avr avr-libc avrdude git stress-ng

# Ubuntu's brltty service can claim CH340 adapters and remove /dev/ttyUSB0.
systemctl stop brltty.service brltty-udev.service 2>/dev/null || true
systemctl disable brltty.service brltty-udev.service 2>/dev/null || true
systemctl mask brltty.service brltty-udev.service 2>/dev/null || true

usermod -aG dialout "${DELL_USER}"
install -d -o "${DELL_USER}" -g "${DELL_USER}" "${LIB_DIR}"

install_library() {
  local repo="$1"
  local destination="$2"
  if [[ -d "${destination}/.git" ]]; then
    sudo -u "${DELL_USER}" git -C "${destination}" pull --ff-only
  elif [[ -e "${destination}" ]]; then
    echo "Keeping existing non-git library: ${destination}"
  else
    sudo -u "${DELL_USER}" git clone --depth 1 "${repo}" "${destination}"
  fi
}

install_library https://github.com/PaulStoffregen/OneWire.git "${LIB_DIR}/OneWire"
install_library https://github.com/milesburton/Arduino-Temperature-Control-Library.git "${LIB_DIR}/DallasTemperature"
install_library https://github.com/adafruit/DHT-sensor-library.git "${LIB_DIR}/DHT_sensor_library"
install_library https://github.com/adafruit/Adafruit_Sensor.git "${LIB_DIR}/Adafruit_Unified_Sensor"

modprobe -r ch341 pl2303 2>/dev/null || true
modprobe ch341
modprobe pl2303
udevadm trigger --subsystem-match=tty
udevadm settle

echo
echo "Restoration complete. Sign out and back in to activate dialout membership."
echo "Serial devices currently present:"
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || true
