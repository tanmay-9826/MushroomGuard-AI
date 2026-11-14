# MushroomGuard AI — Arduino UNO Hardware Setup

This guide matches the hardware described for this project:

- Arduino UNO
- DHT11 temperature / relative-humidity sensor
- Two-channel relay module
- 12 V DC fan
- LED light with a separately rated power supply
- USB cable from the UNO to the Windows PC
- USB CCTV camera connected directly to the Windows PC

The included firmware uses the pin assignments and active-LOW relay logic from the supplied sketch. Verify the actual relay board before connecting either load.

## 1. Low-voltage signal wiring

| Component | Module terminal | Arduino UNO |
|---|---|---|
| DHT11 | DATA / OUT / S | D2 |
| DHT11 | VCC / + | 5V, if the sensor module is rated for 5V |
| DHT11 | GND / - | GND |
| Fan relay channel 1 | IN1 | D7 |
| LED relay channel 2 | IN2 | D8 |
| Relay module | Logic VCC | According to the relay board's specification |
| Relay module | Logic GND | UNO GND |
| UNO to PC | USB | Windows PC USB port |

Use the labels and pinout printed on your specific DHT11 module. A bare four-pin DHT11 and a three-pin breakout do not have the same physical pin arrangement. Do not guess the sensor pin order.

## 2. Load power wiring

The fan and LED must use their own correctly rated external power supply. The UNO GPIO pins and UNO 5V pin are only for low-voltage signal / sensor / relay-module logic within the board's ratings. **Do not power the 12 V fan or a high-power LED from the Arduino.**

For each low-voltage DC load, use the relay contact terminals marked COM and NO so the load is normally disconnected while the relay is off. Follow the contact diagram printed on the relay module. Verify that the relay contacts are rated for the load's DC voltage and startup current, not just its steady current. Use suitable wire gauge, strain relief and over-current protection.

Keep the relay contact/load wiring separate from the low-voltage signal wiring. Never connect mains voltage to a breadboard or exposed project wiring. Mains-powered lighting or supplies must be installed by a qualified person in a properly enclosed, protected assembly.

## 3. Confirm relay polarity before connecting loads

The supplied firmware assumes **active-LOW** relay inputs, matching the user's sketch:

- Arduino output HIGH = relay channel OFF
- Arduino output LOW = relay channel ON

Before connecting the fan or LED load, upload the sketch and check both relay channels with the load wiring disconnected. If the relay board has a different trigger polarity, stop and confirm its specification; do not experiment while the loads are connected. The polarity constant is `RELAY_ACTIVE_LOW` in `hardware/arduino/mushroomguard.ino`.

## 4. Upload the firmware

1. Install Arduino IDE.
2. In Library Manager, install **DHT sensor library by Adafruit** and any dependency Arduino IDE requests.
3. Open `hardware/arduino/mushroomguard.ino`.
4. Select the correct Arduino UNO board and COM port.
5. Upload the sketch.
6. Open Serial Monitor at 9600 baud only to check startup and telemetry. Close Serial Monitor before connecting from MushroomGuard AI; the COM port cannot normally be owned by both programs at once.

The application expects the new sketch's structured telemetry and command acknowledgements. The original sketch supplied earlier does not accept PC commands, so upload the included updated sketch before using the Environment controls.

## 5. Expected control behavior

| Condition / command | Expected result |
|---|---|
| Arduino starts | Fan relay OFF, LED relay OFF, automatic fan mode enabled |
| Temperature >= 25.0 °C in AUTO | Fan ON |
| Temperature between 23.0 and 25.0 °C in AUTO | Retain the previous fan state (hysteresis) |
| Temperature <= 23.0 °C in AUTO | Fan OFF |
| DHT11 read fails | Fan forced ON; firmware reports `DHT_ERROR` |
| PC sends FAN_OFF during DHT11 fault | Request rejected; fan remains ON |
| PC sends FAN_MODE_MANUAL | Automatic temperature switching disabled until AUTO selected again; sensor-fault fan fail-safe remains active |
| PC sends LED_ON / LED_OFF | LED relay channel 2 switched manually |

The 25 °C / 23 °C fan thresholds are fixed in the supplied firmware. Editing room target ranges in the web app changes alerts only; it does not reprogram these thresholds.

## 6. Connect the application

1. Start MushroomGuard AI on the same Windows PC.
2. Open **Settings → Device Setup**.
3. Set the Arduino COM port shown in Windows Device Manager (for example `COM3`) and baud rate `9600`.
4. Set the USB camera index. Start with `0`; if another camera is selected by Windows, try `1` or the next index from Settings.
5. Open **Environment**, select the room where the DHT11 is installed, and connect the Arduino.
6. Wait for a recent temperature and humidity reading.
7. Open **Tools & Diagnostics** and test the camera, controller and sensor.
8. With the high-voltage / load side isolated and wiring checked, test each relay output. Then connect the properly powered fan and LED and confirm that each physical load actually operates.

A serial `ACK` proves only that the firmware accepted a command. It does not prove that the relay contacts, external supply, fan or light are physically working. Confirm the relay indicator and the actual load separately.

## 7. What this hardware does not provide

The described assembly does not include a CO2 sensor, a heater, a humidifier or additional room controllers. The application can store an optional CO2 reading entered from a separate instrument, but it cannot measure CO2 automatically. Humidity readings generate alerts; this assembly does not automatically operate a humidifier. The LED is manually controlled. The USB camera is controlled by the PC application, not by the UNO.


## ThingSpeak connection (PC gateway)

The standard UNO in this assembly has no built-in Wi-Fi. Keep the UNO connected to the Windows PC by USB. The Flask/Python process on that PC forwards the newest valid sensor reading to ThingSpeak over the PC's internet connection. No ThingSpeak Arduino library or extra Wi-Fi module is needed for this PC-gateway architecture.

- Field 1: temperature °C
- Field 2: relative humidity %
- Field 3: fan state (1 ON, 0 OFF)
- Field 4: LED state (1 ON, 0 OFF)
- Field 5: fan mode (0 AUTO, 1 MANUAL)
- Field 6: sensor-valid flag (1 for a valid DHT11 reading)
- Field 7: local room database ID

The UNO still samples every 2 seconds and runs its fan safety logic locally. The free ThingSpeak service only accepts one channel update every 15 seconds, so the PC publisher uses a default 20-second interval. Copy `.env.example` to `.env`, set the channel ID and both API keys, then restart Flask. Never expose the Write API Key in browser JavaScript or commit `.env` to source control.
