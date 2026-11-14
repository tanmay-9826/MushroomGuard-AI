# ThingSpeak + Camlora setup

## ThingSpeak

1. Create a private ThingSpeak channel and enable the fields defined in `THINGSPEAK_SETUP.md`.
2. Copy `.env.example` to `.env` and enter the Channel ID and newly generated Write/Read API keys.
3. Keep the upload interval at 20 seconds or higher for the free update cadence.
4. Restart Flask after editing `.env`.
5. Check the ThingSpeak Cloud panel on Environment and the channel's Private View.

Do not expose keys in HTML/JavaScript or commit `.env`.

## Camlora Android camera

1. Connect the phone to the PC using a USB data cable and enable USB tethering.
2. Start Camlora on Android, allow camera access, choose the rear camera, and start streaming.
3. Use the current address displayed by Camlora. Example only: `http://10.132.148.169:5959`.
4. From the PC, test `/video` and `/shot.jpg` in a browser.
5. Set `CAMLORA_BASE_URL` to the base address only, without a path, in `.env`.
6. Restart Flask and open Plant Health → Android Phone Camera → Start Live Preview.
7. Select a farmer-owned bag/tray and use Capture & Save Snapshot. The JPEG is saved in `uploads/` and linked to a health record.

The Camlora stream is local unencrypted HTTP. Do not expose it to public networks or port-forward its port. The PC and phone must have a working local route between them; USB tethering can provide that route even when college Wi-Fi blocks peer-to-peer connections.

## Troubleshooting

- If preview fails, verify Camlora is actively streaming and refresh the phone IP/port after reconnecting USB.
- Verify that the PC browser can open `http://PHONE_IP:PORT/video` before debugging Flask.
- If the snapshot fails, verify `/shot.jpg` returns a JPEG image.
- If Flask says Camlora is not configured, check `.env` is beside `app.py` and restart `run.bat`.
- Do not include username/password in the base URL; the current integration deliberately accepts only a private/local HTTP IP address and port.

## Scope

Live preview and manual snapshots are included. Automatic scheduled snapshots and AI disease classification are not included in this build.

## QR identification and stage review (v1.3)

1. Create a registered growing unit from Dashboard. The application assigns its `MUSH-xxxxx` or `MICRO-xxxxx` ID.
2. Open that unit's detail page and download/print its QR label. Attach the label to the physical unit.
3. In Plant Health, start the Camlora live preview and click **Read Bucket QR**.
4. The server fetches snapshots from Camlora, decodes the QR with OpenCV, and validates the ID against the signed-in farmer's active records.
5. A matched unit's variety and current database stage are displayed. Capture a photo.
6. Inspect the image. Select the stage you observe, and tick the confirmation checkbox only when you want the database stage updated. Saving writes the image observation and, if the selected stage differs, updates the current stage and adds a stage-history row in the same transaction.

The QR is an identifier, not a crop-stage classifier. Stage changes are farmer-confirmed. This version does not claim automatic visual growth-stage recognition.

## Video recording and YOLO stage workflow (v1.4)

Plant Health now has a separate **Record cultivation video** workflow. Select a registered bag/tray, start and stop recording, and MushroomGuard saves the MP4 locally under `uploads/videos/`. After stopping, choose **Extract frames** to sample the video (default every 5 seconds, maximum 120 frames). Label the sampled frames with the stage you actually observed. These labels build the crop-specific training dataset; they do not change the unit's current growth stage.

Methi is the first model target. The project includes `ml/export_classification_dataset.py`, `ml/train_yolo_growth.py`, and optional `install-ai.bat`, but **no trained model weights are included**. See `VIDEO_AI_WORKFLOW.md` for the complete training steps. YOLO classifies sampled still frames and averages their probabilities; it is not a temporal video model. Other crops and mushroom varieties need their own datasets and model weights. A prediction remains advisory until a farmer reviews the full video and confirms the stage.
