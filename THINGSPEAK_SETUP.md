# ThingSpeak setup for MushroomGuard AI

This is the PC-gateway design for the existing Arduino UNO assembly. Keep the UNO connected to the Windows PC by USB. The Flask/Python application uploads the serial readings to ThingSpeak over the PC's internet connection. **Do not install the ThingSpeak Arduino library for this design**, and do not add a Wi-Fi module just for the cloud upload.

## 1. Check the channel fields

Use one private channel with these fields:

| Field | Name | Stored value |
|---|---|---|
| 1 | Temperature C | Degrees Celsius |
| 2 | Humidity RH | Relative humidity percent |
| 3 | Fan State | 1 = ON, 0 = OFF |
| 4 | LED State | 1 = ON, 0 = OFF |
| 5 | Fan Mode | 0 = AUTO, 1 = MANUAL |
| 6 | Sensor OK | 1 = valid DHT11 sample |
| 7 | Room ID | Local room ID from MushroomGuard SQLite |

Field names are labels; the field numbers are what the integration uses. The channel should remain private.

## 2. Create the local `.env` file

1. Close MushroomGuard AI if it is running.
2. In Windows File Explorer, open the folder containing `app.py`.
3. Find `.env.example`. If Windows hides extensions, turn on **View > Show > File name extensions**.
4. If this is a new project folder and there is no `.env`, copy `.env.example` and rename the copy exactly to `.env` (one dot at the start, no `.txt` at the end). If you already have a working `.env`, do not overwrite it: keep your existing settings and add only the five ThingSpeak lines below.
5. Open `.env` in Notepad.
6. Fill these settings using the ThingSpeak channel's **API Keys** tab:

```dotenv
THINGSPEAK_CHANNEL_ID=YOUR_CHANNEL_ID
THINGSPEAK_WRITE_API_KEY=YOUR_WRITE_API_KEY
THINGSPEAK_READ_API_KEY=YOUR_READ_API_KEY
THINGSPEAK_UPDATE_INTERVAL=20
THINGSPEAK_TIMEOUT=8
```

Replace each placeholder with the real value. Do not include quotes or angle brackets. Keep the file private; do not upload it to GitHub, share it in screenshots, or paste the keys into chat. The `.env` file is excluded by `.gitignore`.

Keep the existing settings in `.env.example` too, especially `MUSHROOMGUARD_COM` and `MUSHROOMGUARD_BAUD`, if you configure the COM port through this file.

## 3. Start the system in this order

1. Upload `hardware/arduino/mushroomguard.ino` to the UNO if you have not already done so.
2. Close Arduino IDE Serial Monitor and Serial Plotter.
3. Start MushroomGuard AI using `run.bat`.
4. Log in, open **Environment**, select the room where DHT11 is installed and click **Connect Arduino**.
5. Wait up to 20 seconds for the first cloud upload.
6. In the Environment page, check the **ThingSpeak Cloud** card. It should show an upload status and the latest cloud temperature/humidity.
7. Open the ThingSpeak channel's **Private View**. New entries should appear at intervals of approximately 20 seconds.

## 4. What remains local and what goes to the cloud

- Arduino samples DHT11 every 2 seconds and maintains fan hysteresis locally (fan ON at 25°C or above; OFF at 23°C or below; sensor failure forces fan ON).
- The PC still saves local readings in SQLite as they arrive.
- The PC sends the newest available reading to ThingSpeak every 20 seconds. ThingSpeak's free plan has a 15-second minimum interval, so do not set the interval lower than 15 seconds.
- If internet is unavailable, local logging and Arduino automatic fan control continue. Cloud uploads retry with later sensor readings when internet access returns.
- The Environment page reads back the latest private channel entry through Flask. The Read API Key stays on the server and is not exposed in browser JavaScript.

## 5. Troubleshooting

- **Not configured:** check that `.env` is in the same folder as `app.py`, and the variable names are spelled exactly as shown. Restart the application after editing `.env`.
- **Upload rejected / entry_id empty or zero:** verify Channel ID, Write API Key and channel field settings. Check that the update interval is at least 15 seconds.
- **Upload succeeds but latest values do not show on the website:** verify the Read API Key and confirm the channel is private but the key belongs to that channel.
- **No sensor updates:** connect Arduino from Environment and verify COM port, 9600 baud and firmware telemetry. Cloud upload only starts after valid serial readings arrive.
- **Internet temporarily stops:** the local sensor display and fan control should continue. Check the cloud status again after internet returns.

## Security

Treat both API keys as passwords. Never put either key in HTML, JavaScript, a public Git repository or a screenshot. If a key is exposed, regenerate it in ThingSpeak's API Keys tab and update `.env`.
