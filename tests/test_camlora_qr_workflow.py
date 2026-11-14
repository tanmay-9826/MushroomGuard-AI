from datetime import date
from io import BytesIO
from unittest.mock import patch

import pytest
import qrcode

from app import create_app
from models.database import get_db


class FakeCameraResponse:
    status = 200

    def __init__(self, image_bytes):
        self._image_bytes = image_bytes
        self.headers = {'Content-Type': 'image/jpeg'}

    def read(self, _limit=-1):
        return self._image_bytes

    def close(self):
        pass


def qr_jpeg(payload='MUSHROOMGUARD:MICRO-00001'):
    image = qrcode.make(payload).convert('RGB')
    output = BytesIO()
    image.save(output, format='JPEG', quality=95)
    return output.getvalue()


@pytest.fixture()
def camera_client(tmp_path):
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-secret',
        'DATABASE': str(tmp_path / 'camera-test.db'),
        'UPLOAD_FOLDER': str(tmp_path / 'uploads'),
        'SERIAL_PORT': '',
        'CAMERA_INDEX': 0,
        'CAMLORA_BASE_URL': 'http://10.132.148.169:5959',
        'MAX_IMAGE_BYTES': 10 * 1024 * 1024,
    })
    with app.app_context():
        db = get_db()
        db.execute('INSERT INTO users(name,email,password_hash) VALUES(?,?,?)',
                   ('Camera Test Farmer', 'camera@example.test', 'not-used-in-test'))
        uid = db.execute('SELECT id FROM users WHERE email=?', ('camera@example.test',)).fetchone()['id']
        db.execute('''INSERT INTO cultivation_units
                      (user_id,crop_type,crop_name,unit_name,start_date,growth_stage)
                      VALUES(?,?,?,?,?,?)''',
                   (uid, 'microgreen', 'Methi', 'MICRO-00001', date.today().isoformat(), 2))
        db.commit()
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['user_id'] = uid
        yield client, app, uid
    app.extensions['mushroomguard_hardware'].shutdown()
    app.extensions['mushroomguard_thingspeak'].shutdown()


def test_camlora_qr_scan_verifies_owner_and_loads_current_stage(camera_client):
    client, _app, uid = camera_client
    with patch('routes.plant_health.urlopen', return_value=FakeCameraResponse(qr_jpeg())):
        response = client.post('/plant-health/camlora/scan')
    assert response.status_code == 200
    data = response.get_json()
    assert data['detected'] is True
    assert data['registered'] is True
    assert data['unit']['unit_name'] == 'MICRO-00001'
    assert data['unit']['crop_name'] == 'Methi'
    assert data['unit']['growth_stage'] == 2
    assert data['unit']['stage_name'] == 'Germination'


def test_unregistered_qr_does_not_return_someone_elses_unit(camera_client):
    client, _app, _uid = camera_client
    with patch('routes.plant_health.urlopen', return_value=FakeCameraResponse(qr_jpeg('MUSHROOMGUARD:MUSH-99999'))):
        response = client.post('/plant-health/camlora/scan')
    data = response.get_json()
    assert response.status_code == 200
    assert data['detected'] is True
    assert data['registered'] is False
    assert 'not registered' in data['message'].lower()
    assert 'unit' not in data


def test_photo_capture_updates_stage_only_after_explicit_farmer_confirmation(camera_client):
    client, app, uid = camera_client
    image_bytes = qr_jpeg('MUSHROOMGUARD:MICRO-00001')
    with patch('routes.plant_health.urlopen', return_value=FakeCameraResponse(image_bytes)):
        scan_response = client.post('/plant-health/camlora/scan')
        assert scan_response.get_json()['registered'] is True
    with patch('routes.plant_health.urlopen', return_value=FakeCameraResponse(image_bytes)):
        response = client.post('/plant-health/camlora/capture', data={
            'unit_id': '1', 'observation': 'Day 4 visual review',
            'observed_stage': '3', 'confirm_stage': '1'
        })
    assert response.status_code == 200
    data = response.get_json()
    assert data['ok'] is True
    assert data['stage_changed'] is True
    assert data['previous_stage'] == 2
    assert data['current_stage'] == 3
    with app.app_context():
        db = get_db()
        unit = db.execute('SELECT growth_stage FROM cultivation_units WHERE id=1 AND user_id=?', (uid,)).fetchone()
        history = db.execute('''SELECT previous_stage,new_stage,notes FROM cultivation_stage_history
                                WHERE unit_id=1 AND user_id=? ORDER BY id DESC LIMIT 1''', (uid,)).fetchone()
        health = db.execute('SELECT image_name,observation FROM health_records WHERE unit_id=1 AND user_id=? ORDER BY id DESC LIMIT 1', (uid,)).fetchone()
        assert unit['growth_stage'] == 3
        assert history['previous_stage'] == 2 and history['new_stage'] == 3
        assert 'Farmer confirmed stage' in history['notes']
        assert health['image_name']
        assert health['observation'] == 'Day 4 visual review Farmer-confirmed observed stage: Stage 3 — Growth & Development.'


def test_photo_capture_does_not_change_stage_without_checkbox(camera_client):
    client, app, uid = camera_client
    with patch('routes.plant_health.urlopen', return_value=FakeCameraResponse(qr_jpeg())):
        response = client.post('/plant-health/camlora/capture', data={
            'unit_id': '1', 'observation': 'Photo only', 'observed_stage': '3'
        })
    assert response.status_code == 200
    assert response.get_json()['stage_changed'] is False
    with app.app_context():
        db = get_db()
        unit = db.execute('SELECT growth_stage FROM cultivation_units WHERE id=1 AND user_id=?', (uid,)).fetchone()
        history_count = db.execute('SELECT COUNT(*) FROM cultivation_stage_history WHERE unit_id=1').fetchone()[0]
        assert unit['growth_stage'] == 2
        assert history_count == 0


def test_stage_change_requires_recent_scan_of_the_same_unit(camera_client):
    client, app, uid = camera_client
    with patch('routes.plant_health.urlopen', return_value=FakeCameraResponse(qr_jpeg())):
        response = client.post('/plant-health/camlora/capture', data={
            'unit_id': '1', 'observation': 'Attempted stage update',
            'observed_stage': '3', 'confirm_stage': '1'
        })
    assert response.status_code == 409
    assert 'scan this growing unit QR' in response.get_json()['error'].lower()
    with app.app_context():
        db = get_db()
        unit = db.execute('SELECT growth_stage FROM cultivation_units WHERE id=1 AND user_id=?', (uid,)).fetchone()
        assert unit['growth_stage'] == 2
        assert db.execute('SELECT COUNT(*) FROM health_records').fetchone()[0] == 0
