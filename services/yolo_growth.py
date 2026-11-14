"""Optional YOLO classification helpers for crop-specific growth-stage models.

The project ships without trained weights. Each crop has its own model file and
manifest. A model is used only after its manifest is explicitly approved.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

CROP_REGISTRY = {
    'methi': ('microgreen', ('methi', 'fenugreek')),
    'palak': ('microgreen', ('palak', 'spinach')),
    'radish': ('microgreen', ('radish',)),
    'mustard': ('microgreen', ('mustard',)),
    'broccoli': ('microgreen', ('broccoli',)),
    'oyster': ('mushroom', ('oyster',)),
    'button': ('mushroom', ('button',)),
    'milky': ('mushroom', ('milky',)),
    'shiitake': ('mushroom', ('shiitake',)),
}


class GrowthModelNotReady(RuntimeError):
    pass


def crop_model_slug(crop_type, crop_name):
    name = (crop_name or '').strip().lower()
    for slug, (registered_type, terms) in CROP_REGISTRY.items():
        if crop_type == registered_type and any(term in name for term in terms):
            return slug
    return None


def _stage_from_class_name(name):
    match = re.search(r"stage[_ -]?([1-4])", str(name).lower())
    return int(match.group(1)) if match else None


def predict_stage(image_paths, model_path, manifest_path, expected_crop):
    """Aggregate frame-level YOLO class probabilities into a provisional stage."""
    model_file = Path(model_path)
    manifest_file = Path(manifest_path)
    if not model_file.is_file() or not manifest_file.is_file():
        raise GrowthModelNotReady(f"No trained {expected_crop.title()} YOLO growth-stage model is installed yet. Collect and label videos for this crop, export the dataset, then train its model.")
    try:
        manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise GrowthModelNotReady('The model manifest is missing or invalid. Re-train or repair the model package.') from exc
    expected_type = CROP_REGISTRY.get(expected_crop, (None, ()))[0]
    if (manifest.get('crop') != expected_crop or manifest.get('crop_type') != expected_type
            or manifest.get('task') != 'classify'):
        crop_type_label = expected_type or 'crop'
        raise GrowthModelNotReady(
            f'The installed model is not registered as a {expected_crop} {crop_type_label} growth-stage classifier.'
        )
    if manifest.get('approved_for_inference') is not True:
        raise GrowthModelNotReady('This crop model has not been approved for inference. Review its independent test metrics and set approved_for_inference=true only after validation.')
    if not image_paths:
        raise GrowthModelNotReady('No extracted video frames are available for analysis.')
    try:
        import numpy as np
        from ultralytics import YOLO
    except ImportError as exc:
        raise GrowthModelNotReady('Ultralytics is not installed. Run install-ai.bat to install the optional YOLO dependencies.') from exc

    model = YOLO(str(model_file))
    probability_rows = []
    names = model.names
    for image_path in image_paths:
        results = model.predict(source=str(image_path), imgsz=int(manifest.get('image_size', 256)), verbose=False)
        if not results or results[0].probs is None:
            continue
        values = results[0].probs.data.detach().cpu().numpy().astype(float)
        probability_rows.append(values)
    if not probability_rows:
        raise GrowthModelNotReady('YOLO did not return classification probabilities for the extracted frames.')
    mean_scores = np.mean(np.stack(probability_rows), axis=0)
    best_index = int(np.argmax(mean_scores))
    class_name = names.get(best_index, str(best_index)) if isinstance(names, dict) else names[best_index]
    stage = _stage_from_class_name(class_name)
    if stage not in (1, 2, 3, 4):
        raise GrowthModelNotReady(f'Unexpected YOLO class name: {class_name}. Expected stage_1 through stage_4.')
    return {
        'stage': stage,
        'class_name': str(class_name),
        'confidence': float(mean_scores[best_index]),
        'frames_analysed': len(probability_rows),
        'model': manifest.get('model_name', model_file.name),
        'model_version': manifest.get('model_version', 'unversioned'),
        'scores': {str(names.get(i, i) if isinstance(names, dict) else names[i]): float(v)
                   for i, v in enumerate(mean_scores)},
        'note': 'Provisional crop-stage estimate aggregated across sampled frames. Review the full video and confirm before updating the growing-unit stage.',
    }
