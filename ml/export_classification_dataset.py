"""Export farmer-labelled video frames into an Ultralytics YOLO classify dataset.

Splits by growing-unit ID (not by individual frame) to reduce train/validation
leakage from near-identical frames of the same tray.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
from collections import defaultdict, Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.unit_qr import stage_name


def safe_slug(text: str) -> str:
    value = ''.join(ch.lower() if ch.isalnum() else '_' for ch in (text or '').strip())
    return '_'.join(part for part in value.split('_') if part)


def class_folder(crop_type: str, stage: int) -> str:
    label = safe_slug(stage_name(crop_type, stage))
    return f'stage_{stage}_{label}'


def build_unit_splits(unit_stages, seed: int = 42):
    """Assign whole growing units to splits while trying to cover every class."""
    ratios = {'train': 0.70, 'val': 0.15, 'test': 0.15}
    assignment = {}
    global_counts = {name: 0 for name in ratios}
    stage_counts = {stage: {name: 0 for name in ratios} for stage in range(1, 5)}
    stages = sorted(range(1, 5), key=lambda stage: len([u for u, labels in unit_stages.items() if stage in labels]))
    for stage in stages:
        units = [unit for unit, labels in unit_stages.items() if stage in labels]
        units.sort(key=lambda unit: hashlib.sha256(f'{seed}:{unit}'.encode()).hexdigest())
        for unit in units:
            if unit in assignment:
                continue
            candidates = sorted(ratios, key=lambda split: (
                stage_counts[stage][split] / ratios[split],
                global_counts[split] / ratios[split],
                hashlib.sha256(f'{seed}:{unit}:{split}'.encode()).hexdigest(),
            ))
            chosen = candidates[0]
            assignment[unit] = chosen
            global_counts[chosen] += 1
            for label in unit_stages[unit]:
                stage_counts[label][chosen] += 1
    uncovered = {stage: [split for split in ratios if stage_counts[stage][split] == 0]
                 for stage in range(1, 5)}
    uncovered = {stage: splits for stage, splits in uncovered.items() if splits}
    if uncovered:
        raise ValueError('The labelled dataset cannot populate every class in train/validation/test without splitting a tray across sets. ' +
                         '; '.join(f'Stage {stage} missing {", ".join(splits)}' for stage, splits in uncovered.items()) +
                         '. Record more distinct trays at those stages.')
    return assignment


def export_dataset(database: Path, uploads: Path, output: Path, crop: str, seed: int = 42, user_id: int | None = None):
    aliases = {
        'methi': ('microgreen', ('methi', 'fenugreek')),
        'oyster': ('mushroom', ('oyster',)),
        'button': ('mushroom', ('button',)),
        'milky': ('mushroom', ('milky',)),
        'shiitake': ('mushroom', ('shiitake',)),
        'palak': ('microgreen', ('palak', 'spinach')),
        'radish': ('microgreen', ('radish',)),
        'mustard': ('microgreen', ('mustard',)),
        'broccoli': ('microgreen', ('broccoli',)),
    }
    if crop not in aliases:
        raise ValueError(f'Unsupported crop slug {crop!r}. Choose one of: {", ".join(aliases)}')
    crop_type, crop_terms = aliases[crop]
    db = sqlite3.connect(database)
    db.row_factory = sqlite3.Row
    rows = db.execute('''SELECT f.id AS frame_id,f.recording_id,f.unit_id,f.user_id,f.filename,f.stage_label,
        u.crop_type,u.crop_name FROM video_frames f
        JOIN cultivation_units u ON u.id=f.unit_id
        WHERE f.stage_label BETWEEN 1 AND 4
        ORDER BY f.id''').fetchall()
    db.close()
    selected = [r for r in rows if r['crop_type'] == crop_type and
                any(term in (r['crop_name'] or '').lower() for term in crop_terms)]
    if user_id is not None:
        selected = [r for r in selected if int(r['user_id']) == int(user_id)]
    else:
        owners = {int(r['user_id']) for r in selected}
        if len(owners) > 1:
            raise ValueError('Labelled frames belong to multiple farmer accounts. Re-run with --user-id to select one account; do not mix farms without consent.')
    if not selected:
        raise ValueError(f'No farmer-labelled frames found for crop {crop!r}. Record videos, extract frames, and label them first.')

    # Split at unit level, preventing frames from the same tray appearing in
    # both training and evaluation sets.
    units_by_stage = defaultdict(set)
    stages_by_unit = defaultdict(set)
    for row in selected:
        stage = int(row['stage_label'])
        unit_id = int(row['unit_id'])
        units_by_stage[stage].add(unit_id)
        stages_by_unit[unit_id].add(stage)
    missing = {stage: len(units_by_stage.get(stage, set())) for stage in range(1, 5)
               if len(units_by_stage.get(stage, set())) < 3}
    if missing:
        details = '; '.join(f'Stage {stage}: {count} distinct tray(s)' for stage, count in missing.items())
        raise ValueError('Need at least 3 distinct growing units per stage to create train/validation/test splits without tray leakage. ' + details)
    split_by_unit = build_unit_splits(stages_by_unit, seed)

    output.parent.mkdir(parents=True, exist_ok=True)
    build_dir = output.with_name(output.name + '.building')
    if build_dir.exists():
        shutil.rmtree(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    counts = Counter()
    groups = defaultdict(set)
    for row in selected:
        stage = int(row['stage_label'])
        split = split_by_unit[int(row['unit_id'])]
        src = uploads / 'video_frames' / row['filename']
        if not src.is_file():
            continue
        target_dir = build_dir / split / class_folder(crop_type, stage)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_name = f"u{row['unit_id']}_r{row['recording_id']}_f{row['frame_id']}.jpg"
        shutil.copy2(src, target_dir / target_name)
        counts[(split, stage)] += 1
        groups[(split, stage)].add(int(row['unit_id']))

    empty = [f'{split}/stage_{stage}' for split in ('train','val','test') for stage in range(1,5)
             if counts[(split, stage)] == 0]
    if empty:
        shutil.rmtree(build_dir, ignore_errors=True)
        raise ValueError('Could not populate every dataset split/class: ' + ', '.join(empty) +
                         '. Check that extracted frame files exist under uploads/video_frames.')
    report = {
        'crop': crop, 'crop_type': crop_type,
        'user_id': (int(user_id) if user_id is not None else (int(selected[0]['user_id']) if selected else None)),
        'seed': seed,
        'split_strategy': 'unit_id_grouped_deterministic',
        'classes': {str(stage): stage_name(crop_type, stage) for stage in range(1, 5)},
        'counts': {f'{split}/stage_{stage}': count for (split, stage), count in sorted(counts.items())},
        'distinct_units': {f'{split}/stage_{stage}': len(units) for (split, stage), units in sorted(groups.items())},
        'total_images': sum(counts.values()),
        'warning': 'Frames from the same growing unit are kept in one split. Keep test units unseen during training and tuning.'
    }
    (build_dir / 'dataset_report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    backup = output.with_name(output.name + '.previous')
    if backup.exists():
        shutil.rmtree(backup)
    if output.exists():
        output.rename(backup)
    build_dir.rename(output)
    if backup.exists():
        shutil.rmtree(backup)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--crop', default='methi', choices=['methi','oyster','button','milky','shiitake','palak','radish','mustard','broccoli'])
    parser.add_argument('--database', type=Path, default=Path('database/mushroomguard.db'))
    parser.add_argument('--uploads', type=Path, default=Path('uploads'))
    parser.add_argument('--output', type=Path, default=None)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--user-id', type=int, default=None, help='Limit training images to this farmer account ID.')
    args = parser.parse_args()
    output = args.output or (Path('ml/datasets') / args.crop / 'yolo_classify')
    report = export_dataset(args.database, args.uploads, output, args.crop, args.seed, args.user_id)
    print(json.dumps(report, indent=2))
    print(f'\nDataset exported to: {output.resolve()}')


if __name__ == '__main__':
    main()
