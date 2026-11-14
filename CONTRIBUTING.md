# Contributing

- Keep credentials, `.env`, local SQLite databases, private grower records, videos, and raw uploads out of commits.
- Add tests for backend changes and run `test.bat` on Windows after installing the project dependencies.
- Keep crop-specific datasets and weights separate. Do not reuse Methi labels or weights for mushroom species.
- For image contributions, record the original URL/source, creator, licence, retrieval date, crop/species, disease/stage label, tray/session group, and reviewer in a manifest.
- Keep images from the same tray or recording session in one split. Never distribute related frames/augmentations across train/validation/test.
- Never label a disease from appearance alone when the source is uncertain. Use `uncertain`/`needs_review` and obtain expert confirmation.
- Do not call a model validated unless metrics are computed on held-out independent trays/sessions.
