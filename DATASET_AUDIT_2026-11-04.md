# Methi dataset audit - 4 November 2026

## Result: four-class training is blocked

The uploaded files were reviewed and integrated into `ml/datasets/methi/incoming_review/`. This is a **candidate review set**, not an approved training dataset.

| Stage | Candidate PNGs | Source groups | Finding |
|---|---:|---:|---|
| 1 - Seed & tray preparation | 15 | 1 | Panels cropped from one instruction collage; sequential prep views |
| 2 - Germination | 40 | 1 | 40 crops/appearance variants from one uploaded reference image; late seedling/cotyledon stage |
| 3 - Growth & development | 0 | 0 | Missing |
| 4 - Harvesting | 40 | 1 | 40 sequential pages from one PDF showing one tray/session |

Total: 95 PNG candidate files, but only **three source groups**. The 20 separately uploaded JPEGs (`stage_01`-`stage_03`, `stage_25`-`stage_41`) were not counted again; tested pairs match PDF page images with resized grayscale correlation above 0.998.

## Training decision

No model was trained. In addition to the data blockers, Ultralytics is not installed in this build environment and package-index network access is unavailable. A four-class classifier cannot be meaningfully trained or independently evaluated with Stage 3 absent and only one source group in every represented class. An image-level random split would leak highly similar views/augmentations from the same tray into train and test and produce misleading metrics.

The included app continues to reject missing/unapproved YOLO weights and uses farmer confirmation for operational stage changes. It does not claim automated disease diagnosis.

## Next data required

- Collect Stage 3 Methi images from distinct trays and capture sessions.
- Collect more independent tray/session groups for all four stages; 3 groups per stage is only a technical floor, while 10+ per stage is a better pilot target.
- Keep all images from each tray/session together in one split.
- Review Stage 2 vs Stage 3 boundary and harvest-ready vs actual harvest labels before training.

See `ml/datasets/methi/incoming_review/README.md` and `metadata/dataset_audit.json`.
