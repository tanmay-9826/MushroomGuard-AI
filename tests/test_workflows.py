from datetime import date
from io import BytesIO
import base64
import sqlite3
import struct
import zlib

import pytest

from app import create_app


def tiny_png():
    """Return a valid 1x1 RGBA PNG for upload validation tests."""
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    raw = b'\x00\x40\x90\x40\xff'
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>2I5B', 1, 1, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(raw))
            + chunk(b'IEND', b''))


@pytest.fixture()
def client(tmp_path):
    app = create_app({
        'TESTING': True,
        'SECRET_KEY': 'test-secret',
        'DATABASE': str(tmp_path / 'test.db'),
        'UPLOAD_FOLDER': str(tmp_path / 'uploads'),
        'SERIAL_PORT': '',
        'CAMERA_INDEX': 99,
        'MAX_CONTENT_LENGTH': 12 * 1024 * 1024,
    })
    with app.test_client() as test_client:
        yield test_client
    app.extensions['mushroomguard_hardware'].shutdown()


def register_and_set_preferences(client, *, name='Test Farmer', email='farmer@example.test', mobile='9876543210'):
    response = client.post('/select-language', data={'language': 'en'}, follow_redirects=True)
    assert response.status_code == 200
    response = client.post('/register', data={
        'name': name,
        'farm_name': f'{name} Farm',
        'mobile': mobile,
        'farm_location': 'Phaltan, Maharashtra',
        'email': email,
        'language': 'en',
        'password': 'secure-pass-123',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Farm Details' in response.data or b'Farm name' in response.data
    response = client.post('/onboarding/farm', data={
        'farm_name': f'{name} Farm',
        'location': 'Phaltan, Maharashtra',
        'region_names': ['Room A', 'Room B'],
    }, follow_redirects=True)
    assert response.status_code == 200
    response = client.post('/preferences', data={
        'grows_mushrooms': '1',
        'grows_microgreens': '1',
        'mushroom_crops': ['Oyster Mushroom'],
        'microgreen_crops': ['Methi'],
    }, follow_redirects=True)
    assert response.status_code == 200
    response = client.post('/onboarding/devices', data={
        'serial_port': '', 'serial_baud': '9600', 'camera_index': '99'
    }, follow_redirects=True)
    assert response.status_code == 200
    return response


def create_unit(client, *, crop_type='mushroom', crop_name='Oyster Mushroom', stage='1'):
    response = client.post(f'/buckets/add/{crop_type}', data={
        'crop_name': crop_name,
        'start_date': date.today().isoformat(),
        'growth_stage': stage,
        'batch_code': 'BATCH-TEST-01',
        'rack': 'R1-A',
        'region_id': '1',
        'notes': 'Initial test record',
    }, follow_redirects=True)
    assert response.status_code == 200
    return response


def test_registration_preferences_and_dashboard(client):
    response = register_and_set_preferences(client)
    assert b'Farm Dashboard' in response.data
    assert b'Mushroom Cultivation' in response.data
    assert b'Microgreen Cultivation' in response.data
    assert b'Oyster Mushroom' in response.data
    assert b'Methi' in response.data
    assert b'Total Bags' in response.data


def test_bucket_creation_stage_history_and_harvest(client):
    register_and_set_preferences(client)
    response = create_unit(client, stage='1')
    assert b'MUSH-00001' in response.data
    response = client.post('/buckets/1/stage', data={'growth_stage': '2', 'notes': 'Mycelium growth'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Stage History' in response.data
    response = client.post('/buckets/1/stage', data={'growth_stage': '4'}, follow_redirects=True)
    assert response.status_code == 200
    response = client.post('/buckets/1/harvest', data={
        'harvest_date': date.today().isoformat(), 'weight': '1.25', 'unit': 'kg', 'quality': 'Good', 'notes': 'First flush'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'1.25' in response.data
    assert b'First flush' in response.data


def test_microgreen_unit_has_correct_prefix_and_stage_guide(client):
    register_and_set_preferences(client)
    response = create_unit(client, crop_type='microgreen', crop_name='Methi', stage='1')
    assert b'MICRO-00001' in response.data
    assert b'Seed &amp; Tray Preparation' in response.data or b'Seed & Tray Preparation' in response.data


def test_rejects_future_start_date(client):
    register_and_set_preferences(client)
    response = client.post('/buckets/add/mushroom', data={
        'crop_name': 'Oyster Mushroom',
        'start_date': '2999-01-01',
        'growth_stage': '1',
        'region_id': '1',
    }, follow_redirects=True)
    assert b'Start date cannot be in the future' in response.data


def test_inventory_and_environment_alerts(client):
    register_and_set_preferences(client)
    response = client.post('/inventory/stock', data={
        'item_name': 'Wheat straw', 'category': 'Substrate', 'quantity': '12', 'unit': 'kg', 'minimum_quantity': '3'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Wheat straw' in response.data
    response = client.post('/environment/reading', data={
        'region_id': '1', 'temperature': '30.5', 'humidity': '97', 'co2': ''
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'30.5' in response.data
    assert b'97' in response.data
    alerts = client.get('/environment/alerts')
    assert alerts.status_code == 200
    assert b'temperature_high' in alerts.data
    assert b'humidity_high' in alerts.data


def test_plant_health_image_record_and_protected_image(client):
    register_and_set_preferences(client)
    create_unit(client)
    response = client.post('/plant-health/record', data={
        'unit_id': '1',
        'observation': 'Small pale patches observed',
        'severity': 'warning',
        'image': (BytesIO(tiny_png()), 'sample.png'),
    }, content_type='multipart/form-data', follow_redirects=True)
    assert response.status_code == 200
    assert b'Small pale patches observed' in response.data
    app_image = None
    # The image name is stored against the authenticated farmer's health record.
    # Retrieve it through the test client's app context using the same DB path.
    with client.application.app_context():
        from models.database import get_db
        row = get_db().execute('SELECT image_name FROM health_records WHERE user_id=1 ORDER BY id DESC LIMIT 1').fetchone()
        app_image = row['image_name']
    image_response = client.get(f'/plant-health/image/{app_image}')
    assert image_response.status_code == 200
    assert image_response.mimetype == 'image/png'


def test_manual_health_status_and_export(client):
    register_and_set_preferences(client)
    create_unit(client)
    response = client.post('/plant-health/unit/1/status', data={'health_status': 'healthy'}, follow_redirects=True)
    assert response.status_code == 200
    csv_response = client.get('/plant-health/export.csv')
    assert csv_response.status_code == 200
    assert b'Bag / Tray ID' in csv_response.data


def test_settings_profile_and_device_configuration(client):
    register_and_set_preferences(client)
    response = client.post('/settings', data={
        'section': 'profile', 'name': 'Updated Farmer', 'mobile': '9876543210',
        'farm_name': 'Updated Farm', 'location': 'Phaltan', 'language': 'mr'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'Updated Farmer' in response.data
    response = client.post('/settings', data={
        'section': 'devices', 'serial_port': 'COM3', 'serial_baud': '9600', 'camera_index': '0'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'COM3' in response.data


def test_login_accepts_mobile_with_formatting(client):
    register_and_set_preferences(client)
    client.get('/logout')
    response = client.post('/login', data={'identifier': '98765-43210', 'password': 'secure-pass-123'}, follow_redirects=True)
    assert response.status_code == 200
    assert b'Farm Dashboard' in response.data


def test_user_cannot_view_another_users_bucket(client):
    register_and_set_preferences(client)
    create_unit(client)
    client.get('/logout')
    register_and_set_preferences(client, name='Second Farmer', email='second@example.test', mobile='9876543211')
    response = client.get('/buckets/1')
    assert response.status_code == 404



def test_settings_reject_duplicate_mobile_number(client):
    register_and_set_preferences(client, name='First Farmer', email='first@example.test', mobile='9876543210')
    client.get('/logout')
    register_and_set_preferences(client, name='Second Farmer', email='second@example.test', mobile='9876543211')
    response = client.post('/settings', data={
        'section': 'profile', 'name': 'Second Farmer', 'mobile': '9876543210',
        'farm_name': 'Second Farm', 'location': 'Phaltan', 'language': 'en'
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b'already used by another account' in response.data
    with client.application.app_context():
        from models.database import get_db
        mobile = get_db().execute('SELECT mobile FROM users WHERE id=2').fetchone()['mobile']
        assert mobile == '9876543211'
