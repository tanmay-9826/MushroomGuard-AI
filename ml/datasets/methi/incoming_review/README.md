# Methi image candidates - review only

These source images are included for inspection, not a ready-to-train YOLO dataset. They are deliberately NOT placed in train/val/test folders.

| Candidate class | PNG files | Independent source groups | Status |
|---|---:|---:|---|
| Stage 1 - Seed/tray preparation | 15 | 1 collage | review only |
| Stage 2 - Germination (late seedling reference) | 40 | 1 uploaded photo | review only; augmented/cropped variants |
| Stage 3 - Growth/development | 0 | 0 | missing |
| Stage 4 - Harvest-ready candidates | 40 | 1 PDF/tray session | review only |

The separately uploaded `stage_01.jpg`, `stage_02.jpg`, `stage_03.jpg`, and `stage_25.jpg` through `stage_41.jpg` were not added again because they visually match pages in the supplied 41-page PDF (tested resized grayscale correlations are 0.9977 or higher).

## Why training is blocked

1. Stage 3 has no labelled examples.
2. Each represented stage has only one source group. The images must not be randomly split at image level because neighbouring crops/frames from the same tray would leak into train and test.
3. Stage 2 is late cotyledon/seedling appearance; label boundaries with Stage 3 need a clear agreed definition.
4. Stage 4 pictures show a dense, apparently harvest-ready tray, but not the actual cutting action.

Do not report the 95 PNG files as 95 independent photos. They come from only three source groups.
