# Methi YOLO classification dataset

This folder keeps instructions only; the exporter writes the dataset to `yolo_classify/` so this README is preserved.

Record separate Methi trays at each of the four observed stages, extract frames, and apply farmer-reviewed labels in Plant Health. Then export using (replace account ID 1 with your local farmer ID):

```cmd
.venv\Scripts\python.exe ml\export_classification_dataset.py --crop methi --user-id 1
```

The exporter splits by growing-unit ID so frames from one tray cannot leak into more than one of train/validation/test. The technical minimum is 3 distinct trays per stage; aim for substantially more (10+ is a better pilot target) before training or making accuracy claims.

Train after exporting:

```cmd
install-ai.bat
.venv\Scripts\python.exe ml\train_yolo_growth.py --crop methi --epochs 100 --imgsz 256 --batch 16
```

The trained model is not enabled for app inference until its manifest has been reviewed and explicitly approved.
