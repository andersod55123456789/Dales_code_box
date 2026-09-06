#include <OneWire.h>
#include <DallasTemperature.h>
#include <DHT.h>

constexpr uint8_t DHT_PIN = 2;
constexpr uint8_t ONE_WIRE_PIN = 4;

OneWire oneWire(ONE_WIRE_PIN);
DallasTemperature ds18b20(&oneWire);
DHT dht(DHT_PIN, DHT11);

void printAddress(const DeviceAddress address) {
  for (uint8_t i = 0; i < 8; ++i) {
    if (address[i] < 0x10) {
      Serial.print('0');
    }
    Serial.print(address[i], HEX);
  }
}

void setup() {
  Serial.begin(9600);
  delay(500);
  ds18b20.begin();
  ds18b20.setResolution(12);
  dht.begin();

  Serial.println(F("Oil Cool Compute sensor node"));
  Serial.print(F("DS18B20 devices found on D4: "));
  Serial.println(ds18b20.getDeviceCount());
  Serial.println(F("DHT11 on D2"));
}

void loop() {
  ds18b20.requestTemperatures();

  const uint8_t deviceCount = ds18b20.getDeviceCount();
  Serial.print(F("DS18B20 count="));
  Serial.println(deviceCount);

  for (uint8_t i = 0; i < deviceCount; ++i) {
    DeviceAddress address;
    Serial.print(F("DS18B20["));
    Serial.print(i);
    Serial.print(F("] address="));
    if (!ds18b20.getAddress(address, i)) {
      Serial.println(F("UNKNOWN read=address_error"));
      continue;
    }

    printAddress(address);
    Serial.print(F(" temp_c="));
    const float temperatureC = ds18b20.getTempC(address);
    if (temperatureC == DEVICE_DISCONNECTED_C) {
      Serial.println(F("DISCONNECTED"));
    } else {
      Serial.println(temperatureC, 2);
    }
  }

  const float humidityPct = dht.readHumidity();
  const float dhtTemperatureC = dht.readTemperature();
  Serial.print(F("DHT11 temp_c="));
  if (!isnan(dhtTemperatureC) && !isnan(humidityPct)) {
    Serial.print(dhtTemperatureC, 1);
    Serial.print(F(" humidity_pct="));
    Serial.println(humidityPct, 1);
  } else {
    Serial.println(F("READ_ERROR"));
  }

  Serial.println();
  delay(2000);
}
