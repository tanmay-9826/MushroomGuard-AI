# MushroomGuard AI Full Build v1.5 — Verification report

## Checks run successfully in the build environment

- Python `compileall` across the project: passed.
- JavaScript syntax checks (`node --check`) for all `static/js/*.js`: passed.
- Jinja parsing for all 16 HTML templates: passed.
- Static route-reference audit: 56 route functions found; all 114 template `url_for` references resolve to a route function or Flask's `static` endpoint.
- SQLite schema DDL extracted from `models/database.py` and executed against an isolated in-memory database: passed; core, `video_recordings`, and `video_frames` tables were created.
- Non-Flask unit tests: **26 passed**. This group covers hardware protocol helpers, ThingSpeak helpers, QR decoding/validation, Camlora URL helpers, MJPEG JPEG frame parsing, crop model registry, dataset split behavior, account-isolated dataset export, Methi class folders, and rejection of missing/unapproved YOLO models.
- Both ML command-line tools start and display `--help` without importing Ultralytics or downloading weights.

## Checks not run here

- The full Flask test suite could not be collected because Flask and Werkzeug are not installed in this build environment. An attempted pip install failed because package-index DNS/network access is unavailable. The Windows `install.bat` installs the Flask dependencies; run `test.bat` locally after installation.
- Live Camlora MP4 recording, frame extraction using the user's actual phone stream, MP4 browser playback, and simultaneous live-preview + recording were not physically tested here.
- No YOLO weights are bundled. Ultralytics/PyTorch training was not run because there is no labelled Methi dataset in the build environment and the optional AI dependencies are not installed.
- Arduino UNO, DHT11, relays, fan, LED and ThingSpeak physical operation were not re-tested as part of v1.4.

## Implemented workflow and limits

- Full Camlora MJPEG sessions are recorded locally as bounded MP4 files and linked to a farmer-owned, registered growing unit.
- Stopped recordings can be sampled at the configured interval (default 5 seconds) into JPEG frames.
- Farmer labels are stored separately from the operational growth stage and can be exported to YOLO classification folders.
- Dataset splitting keeps all frames from a growing unit in a single split to reduce tray-level train/test leakage. The exporter requires at least three distinct units represented in each stage to populate train/validation/test. This is a technical minimum only; a larger independent dataset is strongly recommended.
- Methi is the first model target. Crop-specific paths are scaffolded for supported mushroom varieties and other microgreens; every crop requires its own labelled dataset and trained/validated model.
- YOLO inference is image classification on sampled frames, with frame probabilities averaged for a provisional recording-level estimate. It is **not** a temporal video model and does not learn motion.
- The training script writes `approved_for_inference: false`. A model is not used until a project owner reviews independent test performance and explicitly approves the manifest.
- Predictions are advisory. Only a signed-in farmer who reviews the full video and explicitly confirms can update the unit's growth stage and `cultivation_stage_history`.
- There is no disease/contamination classifier and no claim of automated diagnosis.

## Security and data handling

- `.env`, database files, uploaded photos/videos, exported datasets and model weights are excluded from the release archive.
- Video and sampled frames are local files; no video is uploaded to ThingSpeak.
- Video/frame downloads are owner-scoped in the Flask routes.
- Camlora uses local unencrypted HTTP. Keep it on USB tethering or a trusted private LAN; do not expose its port to the public internet.


## v1.5 work performed in this integration pass

- Python source compilation: passed.
- Hardware/ThingSpeak/QR/Camlora helper tests: 26 passed in the current environment.
- Full Flask app/integration tests: not run because Flask/Werkzeug are not installed in this build environment.
- Node.js is available; JavaScript syntax checks are performed at packaging time.
- Methi data audit: 95 candidate PNG files across three source groups; Stage 3 missing.
- YOLO training: intentionally NOT run because the dataset is incomplete and has no independent train/validation/test groups. Ultralytics is not installed in this environment; package-index access failed. No trained or approved model is included.
- Arduino, Camlora live stream, ThingSpeak and Windows install were not physically retested.
