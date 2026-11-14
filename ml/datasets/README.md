# Dataset governance

MushroomGuard keeps crop growth-stage classification and disease classification as separate tasks and separate datasets.

- `methi/incoming_review/`: user-submitted Methi growth-stage candidate images. These are not yet a training-ready split.
- `methi_disease/`: disease dataset collection is not yet populated; see its README and source register.
- `mushrooms/` and `other_microgreens/`: crop-specific dataset workflows are documented separately.

Do not train from `incoming_review` directly. First perform image review, confirm class labels, group by independent tray/session, build leakage-safe train/validation/test splits, and inspect class balance.
