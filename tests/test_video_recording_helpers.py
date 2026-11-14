from pathlib import Path

import pytest

from services.video_recorder import extract_jpegs
from services.yolo_growth import GrowthModelNotReady, crop_model_slug, predict_stage
from ml.export_classification_dataset import class_folder, build_unit_splits


def test_extract_jpegs_handles_markers_split_across_chunks():
    one = b'header\xff\xd8\xffone\xff\xd9tail'
    two = b'\xff\xd8\xfftwo\xff\xd9'
    chunks = [one[:9], one[9:] + two[:4], two[4:]]
    assert list(extract_jpegs(chunks)) == [b'\xff\xd8\xffone\xff\xd9', b'\xff\xd8\xfftwo\xff\xd9']


def test_extract_jpegs_ignores_non_jpeg_noise():
    assert list(extract_jpegs([b'no image', b'\xff\xd8\xffabc\xff\xd9'])) == [b'\xff\xd8\xffabc\xff\xd9']


def test_extract_jpegs_rejects_oversized_incomplete_frame():
    with pytest.raises(ValueError):
        list(extract_jpegs([b'\xff\xd8\xff' + b'x' * 32], max_frame_bytes=16))


def test_unit_split_is_deterministic_and_group_stable():
    unit_stages = {1: {1, 2}, 2: {1, 2}, 3: {1, 2}, 4: {3, 4}, 5: {3, 4}, 6: {3, 4}}
    first = build_unit_splits(unit_stages, 42)
    second = build_unit_splits(unit_stages, 42)
    assert first == second
    for stage in range(1, 5):
        assert {first[unit] for unit, stages in unit_stages.items() if stage in stages} == {'train', 'val', 'test'}


def test_methi_class_folder_matches_yolo_classification_name():
    assert class_folder('microgreen', 1) == 'stage_1_seed_tray_preparation'
    assert class_folder('microgreen', 3) == 'stage_3_growth_development'


def test_unavailable_yolo_model_is_not_reported_as_prediction(tmp_path):
    with pytest.raises(GrowthModelNotReady, match='No trained Methi YOLO'):
        predict_stage([], tmp_path / 'missing.pt', tmp_path / 'missing.json', 'methi')


def test_crop_model_registry_recognizes_methi_and_oyster():
    assert crop_model_slug('microgreen', 'Fenugreek (Methi)') == 'methi'
    assert crop_model_slug('mushroom', 'Oyster Mushroom') == 'oyster'
    assert crop_model_slug('microgreen', 'Unknown crop') is None


def _make_labelled_frame_db(tmp_path, owners=(9,)):
    import sqlite3
    db_path = tmp_path / "test.db"
    uploads = tmp_path / "uploads"
    frames_dir = uploads / "video_frames"
    frames_dir.mkdir(parents=True)
    connection = sqlite3.connect(db_path)
    connection.executescript("""
        CREATE TABLE cultivation_units (id INTEGER PRIMARY KEY, user_id INTEGER, crop_type TEXT, crop_name TEXT);
        CREATE TABLE video_frames (id INTEGER PRIMARY KEY, recording_id INTEGER, unit_id INTEGER,
            user_id INTEGER, filename TEXT, stage_label INTEGER);
    """)
    frame_id = 1
    unit_id = 1
    for owner in owners:
        for stage in range(1, 5):
            for _ in range(3):
                connection.execute("INSERT INTO cultivation_units VALUES(?,?,?,?)",
                                   (unit_id, owner, 'microgreen', 'Methi'))
                filename = f"frame_{frame_id}.jpg"
                (frames_dir / filename).write_bytes(b"fake-jpeg-test-payload")
                connection.execute("INSERT INTO video_frames VALUES(?,?,?,?,?,?)",
                                   (frame_id, frame_id, unit_id, owner, filename, stage))
                unit_id += 1
                frame_id += 1
    connection.commit()
    connection.close()
    return db_path, uploads


def test_exporter_writes_yolo_folders_and_preserves_sibling_readme(tmp_path):
    from ml.export_classification_dataset import export_dataset
    db_path, uploads = _make_labelled_frame_db(tmp_path)
    output = tmp_path / 'datasets' / 'methi' / 'yolo_classify'
    output.parent.mkdir(parents=True)
    readme = output.parent / 'README.md'
    readme.write_text('keep this file', encoding='utf-8')

    report = export_dataset(db_path, uploads, output, 'methi', seed=42, user_id=9)

    assert report['total_images'] == 12
    assert (output / 'train' / class_folder('microgreen', 1)).is_dir()
    assert (output / 'val' / class_folder('microgreen', 4)).is_dir()
    assert (output / 'test' / class_folder('microgreen', 2)).is_dir()
    assert readme.read_text(encoding='utf-8') == 'keep this file'


def test_exporter_refuses_to_mix_multiple_farmer_accounts(tmp_path):
    from ml.export_classification_dataset import export_dataset
    db_path, uploads = _make_labelled_frame_db(tmp_path, owners=(9, 10))
    with pytest.raises(ValueError, match='multiple farmer accounts'):
        export_dataset(db_path, uploads, tmp_path / 'dataset', 'methi')


def test_unapproved_crop_model_is_rejected_before_ultralytics_import(tmp_path):
    import json
    model = tmp_path / 'methi_growth_stage.pt'
    manifest = tmp_path / 'methi_growth_stage_manifest.json'
    model.write_bytes(b'placeholder')
    manifest.write_text(json.dumps({
        'crop': 'methi', 'crop_type': 'microgreen', 'task': 'classify',
        'approved_for_inference': False,
    }), encoding='utf-8')
    with pytest.raises(GrowthModelNotReady, match='not been approved'):
        predict_stage([tmp_path / 'frame.jpg'], model, manifest, 'methi')
