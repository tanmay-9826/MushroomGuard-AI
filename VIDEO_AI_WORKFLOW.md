# MushroomGuard AI v1.5 — Video recording and YOLO growth-stage workflow

## What is implemented

- The Android Camlora MJPEG stream can be recorded by the Windows Flask PC as a bounded MP4.
- Every recording is linked to one registered, owner-scoped mushroom bag or microgreen tray.
- The MP4 is saved in `uploads/videos/`; metadata is stored in SQLite `video_recordings`.
- After recording stops, OpenCV extracts still frames at `VIDEO_FRAME_INTERVAL_SECONDS` (default 5 seconds), up to `VIDEO_MAX_EXTRACTED_FRAMES` (default 120). Frames are saved in `uploads/video_frames/` and indexed in `video_frames`.
- A farmer labels each recording's sampled frames with the stage actually observed. Training labels do not change the unit's operational stage.
- A crop-specific YOLO classification model can analyse each sampled image. Per-frame class probability vectors are averaged into one provisional recording result.
- The operational growing-unit stage changes only after the farmer reviews the result and explicitly confirms it. The previous/new stage are written to `cultivation_stage_history`.
- Videos, frames and database rows are stored locally. Nothing is uploaded to ThingSpeak.

## Important model boundary

This uses **YOLO image classification on sampled frames**, not a temporal video model. The entire MP4 is retained, but the classifier receives selected JPEG frames rather than the encoded MP4 as one temporal sequence. It does not learn motion or time-dependent change within a clip. A future temporal model would be a separate model architecture and training project.

The project ships **without trained YOLO weights**. The Methi model is the first intended model. Mushroom and other microgreen recordings can be stored and labelled now, but each crop/variety needs its own appropriate dataset and trained model before inference is available for it. The app must never show a prediction when the model is absent, not approved, or incompatible with the crop.

## Suggested workflow on Windows

1. Start Camlora on Android and confirm the PC can open `http://PHONE_IP:PORT/video`.
2. Configure `CAMLORA_BASE_URL=http://PHONE_IP:PORT` in `.env`; restart Flask.
3. Create a registered Methi tray (or a mushroom bag).
4. In Plant Health → Record cultivation video, select that unit, add a date/lighting note, click **Start Recording**, then **Stop Recording** after a representative inspection.
5. Download/play the MP4 to verify it is usable. Keep recordings short and stable; the default maximum is 10 minutes and 300 MB.
6. Click **Extract frames**. The default interval is 5 seconds. Review the thumbnails and the full MP4.
7. Choose the growth stage you actually observed and click **Save training label**. This labels the sampled frames for dataset creation; it does not update the unit's current stage.
8. Repeat across **distinct growing trays** and all four Methi stages. Avoid making all images from one tray look like separate samples.

## Dataset split and minimum

Export splits by whole growing-unit ID so frames from one tray cannot be in both training and evaluation. The exporter has a technical minimum of 3 distinct units represented in each stage, allowing separate train/validation/test splits. This is only a technical floor and is **not enough evidence for a reliable model**. For a serious pilot, aim for 10+ separate trays per stage, captured on different days and under realistic variation in lighting, camera distance, tray density and background. Keep a final set of trays unseen until final testing.

The exporter refuses to silently combine multiple farmer accounts. If more than one account has labels for the same crop, select an account explicitly with `--user-id`.

### Find your farmer account ID

From the project folder:

```cmd
.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect('database/mushroomguard.db'); print(c.execute('SELECT id,name,email FROM users').fetchall())"
```

### Install optional AI dependencies

The Flask app and video recording do not need Ultralytics. When you have a labelled dataset and want to train, run:

```cmd
install-ai.bat
```

This installs the optional Ultralytics/PyTorch stack and may require a substantial download and free disk space. Training speed depends on the PC CPU/GPU and the installed PyTorch build.

### Export Methi dataset

Replace `1` with the account ID returned above:

```cmd
.venv\Scripts\python.exe ml\export_classification_dataset.py --crop methi --user-id 1
```

Output is created under:

```text
ml/datasets/methi/yolo_classify/
  train/stage_1_seed_tray_preparation/
  train/stage_2_germination/
  train/stage_3_growth_development/
  train/stage_4_harvesting/
  val/...
  test/...
  dataset_report.json
```

The directory structure follows Ultralytics classification datasets (`train`, `val`, optional `test`, each with one folder per class). See the current Ultralytics documentation: https://docs.ultralytics.com/datasets/classify and https://docs.ultralytics.com/tasks/classify.

### Train and evaluate Methi YOLO

```cmd
.venv\Scripts\python.exe ml\train_yolo_growth.py --crop methi --epochs 100 --imgsz 256 --batch 16
```

The script starts from `yolo26n-cls.pt`, fine-tunes the four growth-stage classes, then evaluates on the held-out `test` split. It saves:

- `ml/models/methi_growth_stage.pt`
- `ml/models/methi_growth_stage_manifest.json`

The manifest is deliberately written with `approved_for_inference: false`. Inspect per-class performance and held-out test results using trays that were not used in training or tuning. Only then may a qualified project owner set that flag to `true`. Do not approve a model merely because training completed or because its accuracy looks high on a small/leaky dataset.

### Mushroom and other crop models

The recorder and frame-label workflow supports all registered mushroom and microgreen units. After the Methi pipeline is working, collect separately labelled datasets for each variety and run the exporter/trainer with a matching crop slug, for example `--crop oyster`, `--crop palak` or `--crop radish`. The code creates a separate model path/manifest per crop; it does not apply Methi weights to mushroom images.

## Storage and privacy

- MP4 recordings: `uploads/videos/`
- Extracted frames: `uploads/video_frames/`
- SQLite metadata and labels: `video_recordings`, `video_frames`
- Dataset exports: `ml/datasets/<crop>/yolo_classify/`
- Model weights and manifests: `ml/models/`

These folders can become large. Back them up, limit recording length, and do not commit videos, frames, datasets, trained weights or `.env` to a public repository. Camlora uses local unencrypted HTTP; keep it on USB tethering or a trusted private network and do not expose its port to the public internet.

## Prediction and stage updates

The current YOLO result is a **provisional estimate** aggregated from sampled still frames. The app does not silently change `cultivation_units.growth_stage`. A signed-in farmer must inspect the original video, select the stage to apply, tick the review checkbox and confirm. Only then is the unit stage updated and a `cultivation_stage_history` row inserted.

No disease/contamination classifier is included. This model estimates the selected crop's four cultivation stages only, and its output is not a laboratory diagnosis or guarantee of harvest readiness.
