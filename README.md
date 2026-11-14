# MushroomGuard AI — Full Build v1.5 Dataset Integrated Candidate

This is a **complete Windows project folder**, not a patch. It includes the MushroomGuard AI Flask/SQLite farm-management application, Arduino/USB serial integration, ThingSpeak cloud bridge, Camlora Android camera integration, and QR-based growing-unit identification with farmer-confirmed stage updates.

## Included

- Flask application with farmer authentication, onboarding, farm/room setup and local SQLite database.
- Dashboard, Plant Health, Inventory, Environment, Tools & Diagnostics, Settings, mushroom-bag and microgreen-tray workflows.
- Arduino UNO serial reader and relay control protocol; DHT11 on D2, fan relay on D7, LED relay on D8, 9600 baud.
- ThingSpeak background upload and private-channel read support. Default upload interval: 20 seconds.
- Camlora phone-camera integration: authenticated live MJPEG preview, snapshot capture and photo history linked to growing units.
- QR labels generated for each registered growing unit and shown on the unit detail page for download/printing.
- Camlora-based QR scan: the phone camera reads a MushroomGuard QR label, the backend validates the ID against the logged-in farmer's registered, non-archived units, then loads the unit's current saved crop and growth stage.
- Stage review workflow: after inspecting the captured image, the farmer may explicitly confirm an observed stage. The server updates `cultivation_units.growth_stage` and inserts a row in `cultivation_stage_history` in the same database transaction as the photo observation.
- Windows install, run and test scripts.


## Video recording and YOLO growth-stage workflow (v1.4)

- Camlora video can be recorded as bounded MP4 sessions against registered mushroom bags or microgreen trays.
- Stopped MP4 files can be sampled into JPEG frames, labelled by the farmer, and exported into crop-specific YOLO classification datasets.
- Methi is the first training target. Separate models are scaffolded for registered mushroom varieties and other microgreens; no weights are bundled.
- YOLO classification runs on sampled frames and aggregates per-frame probabilities. It is not a temporal video model and does not analyse motion.
- Stage predictions are advisory. The farmer must review the full recording and explicitly confirm before the operational growth stage and stage history are changed.
- See `VIDEO_AI_WORKFLOW.md` for the full record → extract → label → export → train → validate → approve workflow.

Video storage defaults: maximum 10 minutes / 300 MB per recording, 8 fps MP4 target, frame extraction every 5 seconds (up to 120 sampled frames). These limits can be changed in `.env`.

## QR-to-stage workflow

1. Create a mushroom bag or microgreen tray. MushroomGuard assigns its ID (for example `MUSH-00001` or `MICRO-00001`).
2. Open that growing unit's detail page and download/print its QR label. The QR payload is `MUSHROOMGUARD:<UNIT-ID>`.
3. Open Plant Health and start the Camlora live preview.
4. Point the phone camera at the printed label and click **Read Bucket QR**.
5. The server decodes the QR from a Camlora JPEG snapshot and searches only the current farmer's active registered units. If it finds a match, Plant Health displays the unit ID, crop variety and stage currently stored in SQLite.
6. Capture a photo. Inspect it and choose the stage that you observe. Tick the explicit confirmation checkbox only when you want that stage written to the unit record.
7. On save, the image is stored in the user's uploads/health history. If the confirmed stage differs from the stored stage, the application updates `cultivation_units.growth_stage` and inserts a timestamped stage-history transition. The page's selected stage indicator is updated, and a link to the unit detail/history page is provided.

### Important AI limitation

The QR code identifies the growing unit; it does **not** identify biological growth stage. No trained or validated growth-stage weights are bundled. v1.4 includes a video-to-dataset exporter and optional YOLO training scripts, beginning with Methi. The camera image/video is stored for visual review, and the farmer explicitly confirms the observed stage before the database changes. The system does not silently advance a stage based only on crop age or an unvalidated image heuristic. A future automatic stage classifier needs crop-specific labelled images, training, validation and a confidence/review policy.

## Windows installation

1. Extract the entire folder to a normal local path such as `C:\MushroomGuardAI_Full_Build_v1.4`.
2. Install 64-bit Python 3.10 or newer and select **Add Python to PATH**.
3. Double-click `install.bat`; this creates `.venv` and installs dependencies.
4. Copy `.env.example` to `.env` in the same directory as `app.py`.
5. Edit `.env` locally. Do not send it to anyone or commit it to source control.
6. Double-click `run.bat` and open `http://127.0.0.1:5000`.

## Configure `.env`

Example settings (replace placeholders locally):

```dotenv
MUSHROOMGUARD_COM=COM4
MUSHROOMGUARD_BAUD=9600
MUSHROOMGUARD_CAMERA=0
MUSHROOMGUARD_SECRET=replace-with-a-long-random-local-secret

THINGSPEAK_CHANNEL_ID=YOUR_CHANNEL_ID
THINGSPEAK_WRITE_API_KEY=YOUR_NEW_WRITE_API_KEY
THINGSPEAK_READ_API_KEY=YOUR_NEW_READ_API_KEY
THINGSPEAK_UPDATE_INTERVAL=20
THINGSPEAK_TIMEOUT=8

CAMLORA_BASE_URL=http://PHONE_IP:PORT
CAMLORA_MAX_RECORDING_SECONDS=600
CAMLORA_MAX_RECORDING_MB=300
CAMLORA_RECORDING_FPS=8
VIDEO_FRAME_INTERVAL_SECONDS=5
VIDEO_MAX_EXTRACTED_FRAMES=120
```

Use the **current** address and port shown by Camlora on your phone. Enter the base URL only, without `/video` or `/shot.jpg`. The phone and PC must be connected through the same reachable local network; USB tethering can provide a direct local network path. If the phone's tether address changes, update `.env` and restart Flask.

**Credential warning:** ThingSpeak API keys were shared in a previous chat. Regenerate both the Write and Read API keys in ThingSpeak, then put the new keys in your local `.env`. Do not use previously exposed keys.

## ThingSpeak data path

Arduino UNO → USB serial → local Python hardware service → SQLite + ThingSpeak publisher → ThingSpeak cloud. The local PC needs internet for cloud updates. Local serial readings and Arduino fan automation do not depend on ThingSpeak availability.

## Camlora phone-camera setup

1. Connect the Android phone to the PC using USB data cable and enable USB tethering, or use a trusted reachable local Wi-Fi network.
2. Start Camlora on the phone and select the rear camera.
3. Note the current Camlora IP and port shown on the phone.
4. Confirm the PC can open `http://PHONE_IP:PORT/video` and `http://PHONE_IP:PORT/shot.jpg`.
5. Set `CAMLORA_BASE_URL=http://PHONE_IP:PORT` in `.env` and restart Flask.
6. Open Plant Health → Android Phone Camera → Start Live Preview.
7. Print the QR label from a growing unit's detail page. Hold it in the camera view and click **Read Bucket QR**.
8. Confirm that the right registered unit and current stage appear. Capture a photo and, if the image shows a later stage, select the observed stage and explicitly tick the confirmation checkbox before saving.

Camlora uses local, unencrypted HTTP. Keep it on a trusted USB-tether/private LAN connection; do not port-forward it or expose it to the public internet.

## Preserve existing data when moving from an earlier folder

- Stop Flask before copying anything.
- Back up the old `database/mushroomguard.db` and the entire `uploads/` directory.
- Copy those two items into the new project folder only if you intend to continue using those records and photos.
- Recreate `.env` locally and enter regenerated ThingSpeak keys. Never overwrite the database without a backup.

## Arduino hardware

Open `hardware/arduino/mushroomguard.ino` in Arduino IDE. Install **DHT sensor library by Adafruit** and its requested dependency. Select Arduino UNO and the correct COM port, upload the sketch, then close Arduino Serial Monitor/Plotter before connecting MushroomGuard AI to that COM port.

Pins: DHT11 DATA D2; fan relay D7; LED relay D8; serial 9600 baud. Verify relay active-LOW polarity with external loads disconnected. Do not power a 12V fan or high-power LED from Arduino pins.

## Tests

After `install.bat`, run `test.bat`, or execute:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The QR decoder tests include a generated MushroomGuard QR label. Flask route integration tests exercise owner-scoped QR lookup and the explicit stage-confirmation database update. Camera, Arduino, ThingSpeak and USB-tether hardware still require testing on the actual Windows PC.


## v1.5 dataset integration status (4 November 2026)

The Methi source images supplied in this conversation are bundled under `ml/datasets/methi/incoming_review/`. They are **not** installed as a model or treated as a validated train/validation/test set. Audit result: 15 Stage 1 candidate PNGs from one collage, 40 Stage 2 crops/augmentations from one reference image, 0 Stage 3 images, and 40 Stage 4 page images from one PDF/tray session. Therefore no four-stage model was trained and no `methi_growth_stage.pt` is included. See `DATASET_AUDIT_2026-11-04.md`.

The YOLO training CLI now accepts `--weights PATH` to select a local starting checkpoint. Example after a complete, grouped dataset is ready:

```cmd
.venv\Scripts\python.exe ml\train_yolo_growth.py --crop methi --data ml\datasets\methi\yolo_classify --weights ml\models\pretrained\yolo26n-cls-user-supplied.pt --epochs 100 --imgsz 256 --batch 16
```

Do not run this command on `incoming_review`; it is not a YOLO split dataset. Only use it after all four classes contain independent, correctly labelled source groups in train/val/test.


Pretrained checkpoint: `ml/models/pretrained/yolo26n-cls-user-supplied.pt` is the checkpoint supplied by the project owner. It has not been deserialized or run in the build environment; verify Ultralytics/PyTorch compatibility on the target PC. It is not a Methi-trained model.

---

## Public repository and dataset status

This source package is being prepared for the public `MushroomGuard-AI` GitHub repository. See `GITHUB_PUBLICATION.md` for the safe publication procedure, Git LFS setup, and current publication status.

**AI status:** no trained or validated Methi growth-stage model is included. The current candidate images are a review-only set with Stage 3 missing and only three original source groups. See `DATASET_AUDIT_2026-11-04.md` and `PROJECT_STATUS_PUBLIC.md`.

**Disease data:** no Methi disease image binaries are included yet. `ml/datasets/methi_disease/` contains only a source register and collection rules. Do not interpret this as a disease-recognition model or dataset.

**Licensing:** no project-wide software licence has been assigned. Public visibility does not itself grant permission to reuse the code. Image reuse rights must be checked per source before adding any third-party disease images.
