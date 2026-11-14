"""Train/evaluate a crop-specific YOLO26 classification model for stages 1-4.

Use one crop dataset at a time. The Methi model is the first target; mushroom
varieties and other microgreens can be trained independently after collecting
and labelling their own videos.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from ml.export_classification_dataset import class_folder
from services.yolo_growth import CROP_REGISTRY


def count_images(root: Path, split: str, class_name: str) -> int:
    folder = root / split / class_name
    if not folder.is_dir():
        return 0
    return sum(1 for p in folder.iterdir() if p.suffix.lower() in {'.jpg','.jpeg','.png','.webp'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--crop', default='methi', choices=sorted(CROP_REGISTRY))
    parser.add_argument('--data', type=Path, default=None)
    parser.add_argument('--epochs', type=int, default=100)
    parser.add_argument('--imgsz', type=int, default=256)
    parser.add_argument('--batch', type=int, default=16)
    parser.add_argument('--device', default='')
    parser.add_argument('--weights', default='yolo26n-cls.pt', help='Pretrained Ultralytics classification checkpoint path or model name.')
    args = parser.parse_args()
    data = args.data or (Path('ml/datasets') / args.crop / 'yolo_classify')
    crop_type = CROP_REGISTRY[args.crop][0]
    class_names = [class_folder(crop_type, stage) for stage in range(1, 5)]

    if not data.is_dir():
        raise SystemExit(f'Dataset folder not found: {data}. Run ml/export_classification_dataset.py --crop {args.crop} first.')
    counts = {split: {cls: count_images(data, split, cls) for cls in class_names}
              for split in ('train','val','test')}
    missing = [f'{split}/{cls}' for split, items in counts.items() for cls, n in items.items() if n == 0]
    if missing:
        raise SystemExit('Dataset is incomplete. Missing images for: ' + ', '.join(missing) +
                         '. Add farmer-labelled videos from more distinct trays; keep one tray in only one split.')
    if any(n < 5 for n in counts['train'].values()):
        raise SystemExit('At least 5 training frames per class are required to start this script. This is only a technical minimum, not enough to claim model quality.')
    if any(n < 1 for n in counts['val'].values()) or any(n < 1 for n in counts['test'].values()):
        raise SystemExit('Every class must have separate validation and held-out test images. Re-export after recording more distinct growing units.')

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        raise SystemExit('Ultralytics is not installed. Run install-ai.bat, then try again.') from exc

    weights = Path(args.weights)
    model = YOLO(str(weights) if weights.is_file() else args.weights)
    result = model.train(
        data=str(data.resolve()), epochs=max(1, args.epochs), imgsz=args.imgsz,
        batch=args.batch, device=args.device or None, patience=20,
        project='runs/classify', name=f'{args.crop}_growth_stage', exist_ok=True,
        verbose=True,
    )
    best = Path(getattr(result, 'save_dir', f'runs/classify/{args.crop}_growth_stage')) / 'weights' / 'best.pt'
    if not best.is_file():
        candidate = Path(f'runs/classify/{args.crop}_growth_stage/weights/best.pt')
        if candidate.is_file():
            best = candidate
        else:
            raise SystemExit('Training finished but best.pt was not found. Inspect the Ultralytics run directory.')

    trained = YOLO(str(best))
    metrics = trained.val(data=str(data.resolve()), split='test', imgsz=args.imgsz, verbose=False)
    top1 = float(getattr(metrics, 'top1', 0.0) or 0.0)
    top5 = float(getattr(metrics, 'top5', 0.0) or 0.0)
    target = Path('ml/models')
    target.mkdir(parents=True, exist_ok=True)
    model_dest = target / f'{args.crop}_growth_stage.pt'
    shutil.copy2(best, model_dest)
    manifest = {
        'crop': args.crop, 'crop_type': crop_type, 'task': 'classify',
        'model_name': f'YOLO26n-cls fine-tuned for {args.crop} growth stages',
        'model_version': datetime.now(timezone.utc).strftime(f'{args.crop}-%Y%m%dT%H%M%SZ'),
        'weights': model_dest.name, 'image_size': args.imgsz,
        'classes': class_names, 'dataset': str(data.resolve()),
        'image_counts': counts, 'held_out_test_top1': top1, 'held_out_test_top5': top5,
        'trained_at_utc': datetime.now(timezone.utc).isoformat(),
        'approved_for_inference': False,
        'approval_note': 'Set true only after a human reviews independent held-out test results across unseen trays and confirms acceptable performance. Model output remains advisory.',
    }
    (target / f'{args.crop}_growth_stage_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print(json.dumps(manifest, indent=2))
    print('\nWeights saved. Inference remains DISABLED until you review independent test results and explicitly approve the manifest.')


if __name__ == '__main__':
    main()
