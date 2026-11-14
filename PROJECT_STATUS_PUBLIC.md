# Public repository status

This public-ready source package is **not a trained/validated AI release**.

- The Flask/SQLite application, Arduino serial integration, ThingSpeak bridge, Camlora camera support, QR workflow, and video-to-dataset workflow are present in the source tree.
- v1.5 verification notes report Python compilation, JavaScript syntax, Jinja parsing, route-reference checks, SQLite DDL checks, and 26 non-Flask helper tests passing in the prior build environment.
- Full Flask integration tests, live camera recording, ThingSpeak physical operation, Arduino relay operation, and hardware tests have not been independently verified in this package-preparation session.
- Methi candidate data contains 95 PNG files but only three source groups: 15 preparation crops from one collage, 40 late-germination derivatives from one photo, and 40 harvest-ready candidates from one tray/PDF session. Stage 3 is missing.
- No Methi model was trained. No disease classifier or validated disease-image dataset is included.

Read `VERIFICATION.md` and `DATASET_AUDIT_2026-11-04.md` before presenting project capabilities.
