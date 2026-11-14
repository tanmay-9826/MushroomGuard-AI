# QR Identification and Stage Update — User Guide

## What the feature does

- A unit gets a unique ID when it is created.
- Its detail page serves a QR label containing `MUSHROOMGUARD:<UNIT-ID>`.
- Plant Health uses the Camlora snapshot endpoint to read that label with OpenCV's QRCodeDetector.
- The backend searches only active growing units owned by the logged-in farmer.
- On a match, the current crop variety and recorded stage are loaded from SQLite and displayed in Plant Health.
- The user captures a photo and can explicitly confirm a visually observed stage. A confirmed change updates the current unit record and appends a stage-history row in the same transaction as the photo record.

## Step-by-step use

1. Create a mushroom bag or microgreen tray from Dashboard.
2. Open the new unit detail page.
3. Download or print the QR label and attach it to the physical bag/tray. Keep the QR clean, flat and visible.
4. Open Plant Health, then start the Android Phone Camera live preview.
5. Click **Read Bucket QR** and hold the QR label in the camera frame. The application checks the code against the current farmer's database records.
6. Verify the displayed unit ID, crop variety and current stage before capturing.
7. Capture & Save Snapshot. Review the image.
8. If the crop has genuinely moved to another stage, select the observed stage and tick the explicit confirmation checkbox. Otherwise leave the checkbox clear.
9. Save. The photo is added to the selected unit's health/image history. A confirmed stage transition updates the database and stage history.

## Safety and correctness rules

- QR recognition is identification, not biological image classification.
- The application does not automatically infer growth stage from a generic photograph. No trained, validated crop-specific stage model is included.
- Do not tick stage confirmation if the photo is unclear or does not support a stage change.
- An unknown, archived or other-farmer unit is not accepted as a registered unit.
- The current stage always comes from the database record, not from assumptions based only on elapsed days.
- Camlora is local unencrypted HTTP; do not expose the camera port to the public internet.

## Troubleshooting

- **No QR found:** move closer, improve lighting, keep the printed QR flat and reduce glare. Ensure the Camlora camera is streaming.
- **ID not registered:** download a fresh QR from that unit's detail page; verify the unit belongs to the currently logged-in farmer and is not archived.
- **Camlora error:** confirm USB tethering, the current Camlora IP/port and `CAMLORA_BASE_URL`; restart Flask after changing `.env`.
- **OpenCV unavailable:** run `install.bat` again or install the dependencies from `requirements.txt` inside the project's virtual environment.
