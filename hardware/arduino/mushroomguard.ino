// MushroomGuard AI — Arduino UNO + DHT11 + 2-channel relay
// DHT11 DATA: D2 | Fan relay IN: D7 | LED relay IN: D8 | USB serial: 9600 baud
// Default relay polarity matches the user's supplied sketch (active LOW).
// Verify polarity with the loads disconnected before connecting the fan or light.
#include <DHT.h>

#define DHT_PIN 2
#define DHT_TYPE DHT11
#define FAN_RELAY_PIN 7
#define LED_RELAY_PIN 8

const bool RELAY_ACTIVE_LOW = true;
const float FAN_ON_TEMP = 25.0;   // Fan starts at or above this temperature.
const float FAN_OFF_TEMP = 23.0;  // Fan stops at or below this temperature.
const unsigned long SAMPLE_INTERVAL_MS = 2000;

DHT dht(DHT_PIN, DHT_TYPE);
unsigned long lastSample = 0;
float lastTemperature = NAN;
float lastHumidity = NAN;
bool fanState = false;
bool ledState = false;
bool automaticFanMode = true;
bool sensorFault = false;

void writeRelay(uint8_t pin, bool state) {
  if (RELAY_ACTIVE_LOW) {
    digitalWrite(pin, state ? LOW : HIGH);
  } else {
    digitalWrite(pin, state ? HIGH : LOW);
  }
}

void controlFan(bool state) {
  fanState = state;
  writeRelay(FAN_RELAY_PIN, state);
}

void controlLED(bool state) {
  ledState = state;
  writeRelay(LED_RELAY_PIN, state);
}

void printTelemetry() {
  if (sensorFault || isnan(lastTemperature) || isnan(lastHumidity)) return;
  Serial.print("TEMP:");
  Serial.print(lastTemperature, 1);
  Serial.print(",HUM:");
  Serial.print(lastHumidity, 1);
  Serial.print(",FAN:");
  Serial.print(fanState ? "ON" : "OFF");
  Serial.print(",LED:");
  Serial.print(ledState ? "ON" : "OFF");
  Serial.print(",MODE:");
  Serial.println(automaticFanMode ? "AUTO" : "MANUAL");
}

void acknowledge(const char *command) {
  Serial.print("ACK:");
  Serial.println(command);
}

void handleCommand(String command) {
  command.trim();
  command.toUpperCase();

  if (command == "FAN_MODE_AUTO") {
    automaticFanMode = true;
    // Automatic hysteresis is applied on the next valid DHT11 sample.
    acknowledge("FAN_MODE_AUTO");
  } else if (command == "FAN_MODE_MANUAL") {
    automaticFanMode = false;
    acknowledge("FAN_MODE_MANUAL");
  } else if (command == "FAN_ON") {
    automaticFanMode = false;
    controlFan(true);
    acknowledge("FAN_ON");
  } else if (command == "FAN_OFF") {
    automaticFanMode = false;
    // Never acknowledge FAN_OFF when the DHT11 fail-safe keeps ventilation ON.
    if (sensorFault) {
      controlFan(true);
      Serial.println("ERR:FAN_OFF");
    } else {
      controlFan(false);
      acknowledge("FAN_OFF");
    }
  } else if (command == "LED_ON") {
    controlLED(true);
    acknowledge("LED_ON");
  } else if (command == "LED_OFF") {
    controlLED(false);
    acknowledge("LED_OFF");
  } else if (command == "STATUS") {
    acknowledge("STATUS");
    printTelemetry();
  } else if (command.length() > 0) {
    Serial.print("ERR:");
    Serial.println(command);
  }
}

void setup() {
  Serial.begin(9600);
  Serial.setTimeout(100);
  pinMode(FAN_RELAY_PIN, OUTPUT);
  pinMode(LED_RELAY_PIN, OUTPUT);

  // Safe default: both relay outputs OFF. Automatic mode begins after first good reading.
  controlFan(false);
  controlLED(false);
  dht.begin();
  Serial.println("MUSHROOMGUARD_READY");
}

void loop() {
  // Process serial commands without blocking sensor sampling for long periods.
  while (Serial.available() > 0) {
    String command = Serial.readStringUntil('\n');
    handleCommand(command);
  }

  const unsigned long now = millis();
  if (now - lastSample < SAMPLE_INTERVAL_MS) return;
  lastSample = now;

  const float humidity = dht.readHumidity();
  const float temperature = dht.readTemperature();
  if (isnan(temperature) || isnan(humidity)) {
    sensorFault = true;
    // Fail-safe from the user's original code: turn ventilation ON on DHT error.
    controlFan(true);
    Serial.println("DHT_ERROR");
    return;
  }

  sensorFault = false;
  lastTemperature = temperature;
  lastHumidity = humidity;

  // Automatic fan hysteresis retained exactly: ON at >=25 C, OFF at <=23 C.
  if (automaticFanMode) {
    if (temperature >= FAN_ON_TEMP && !fanState) {
      controlFan(true);
    } else if (temperature <= FAN_OFF_TEMP && fanState) {
      controlFan(false);
    }
  }

  printTelemetry();
}
