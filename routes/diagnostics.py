import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from models.database import get_db
from services import hardware as hardware_service

diagnostics_bp = Blueprint('diagnostics', __name__)


def _fresh(updated, seconds=20):
    if not updated:
        return False
    try:
        return (datetime.now() - datetime.strptime(updated, '%Y-%m-%d %H:%M:%S')).total_seconds() <= seconds
    except ValueError:
        return False


@diagnostics_bp.get('/diagnostics')
def index():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('auth.login'))
    manager = current_app.extensions['mushroomguard_hardware']
    with manager.state_lock:
        state = dict(manager.latest)
    db = get_db()
    if not db.execute('SELECT 1 FROM users WHERE id=?', (uid,)).fetchone():
        session.clear()
        flash('Your session is no longer valid. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))
    settings = db.execute('SELECT * FROM user_device_settings WHERE user_id=?', (uid,)).fetchone()
    logs = db.execute('SELECT * FROM system_logs WHERE user_id=? ORDER BY id DESC LIMIT 12', (uid,)).fetchall()
    region_count = db.execute('SELECT COUNT(*) FROM regions WHERE user_id=?', (uid,)).fetchone()[0]
    active_alerts = db.execute('SELECT COUNT(*) FROM environment_alerts WHERE user_id=? AND active=1', (uid,)).fetchone()[0]
    usage = shutil.disk_usage(current_app.config['DATABASE'])
    free_gb = usage.free / (1024 ** 3)
    camera_library = hardware_service.cv2 is not None
    serial_library = hardware_service.serial is not None
    sensor_online = bool(state.get('connected') and _fresh(state.get('updated')))
    device_cards = [
        {'name': 'USB Camera', 'detail': f"Configured index {settings['camera_index'] if settings else manager.camera_index}", 'state': 'ready' if camera_library else 'offline', 'status': 'OpenCV installed' if camera_library else 'OpenCV missing'},
        {'name': 'DHT11 Sensor', 'detail': 'Temperature and relative humidity · D2', 'state': 'ready' if sensor_online else 'offline', 'status': 'Fresh reading received' if sensor_online else 'No recent telemetry'},
        {'name': 'Arduino UNO', 'detail': (settings['serial_port'] if settings and settings['serial_port'] else 'COM port not configured'), 'state': 'ready' if state.get('connected') else 'offline', 'status': 'Serial port open' if state.get('connected') else 'Disconnected'},
        {'name': 'Fan Relay', 'detail': 'Channel 1 · D7', 'state': 'ready' if state.get('fan_state') in ('ON','OFF') else 'muted', 'status': f"Reported {state.get('fan_state')}" if state.get('fan_state') else 'State unknown'},
        {'name': 'LED Relay', 'detail': 'Channel 2 · D8', 'state': 'ready' if state.get('led_state') in ('ON','OFF') else 'muted', 'status': f"Reported {state.get('led_state')}" if state.get('led_state') else 'State unknown'},
        {'name': 'AI Disease Model', 'detail': 'No trained model or validated dataset configured', 'state': 'muted', 'status': 'Not installed'},
    ]
    return render_template('diagnostics.html', serial_state=state, settings=settings, logs=logs,
        device_cards=device_cards, free_gb=free_gb, serial_library=serial_library,
        camera_library=camera_library, sensor_online=sensor_online,
        serial_port=settings['serial_port'] if settings else '', serial_baud=settings['serial_baud'] if settings else 9600,
        camera_index=settings['camera_index'] if settings else manager.camera_index,
        region_count=region_count, active_alerts=active_alerts)


@diagnostics_bp.post('/diagnostics/test/<device>')
def test_device(device):
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('auth.login'))
    manager = current_app.extensions['mushroomguard_hardware']
    db = get_db()
    if not db.execute('SELECT 1 FROM users WHERE id=?', (uid,)).fetchone():
        session.clear()
        flash('Your session is no longer valid. Please log in again.', 'warning')
        return redirect(url_for('auth.login'))
    settings = db.execute('SELECT * FROM user_device_settings WHERE user_id=?', (uid,)).fetchone()
    ok = False
    message = ''
    if device == 'camera':
        temp_path = None
        try:
            if settings:
                manager.camera_index = settings['camera_index']
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                temp_path = Path(tmp.name)
            message = manager.test_camera()
            ok = True
        except Exception as exc:
            message = str(exc)
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)
    elif device == 'controller':
        try:
            if settings:
                manager.port = settings['serial_port'] or manager.port
                manager.baud = settings['serial_baud'] or manager.baud
            regions = db.execute('SELECT id FROM regions WHERE user_id=? ORDER BY id LIMIT 1', (uid,)).fetchone()
            if not regions:
                raise RuntimeError('Create a room before connecting the sensor.')
            from routes.environment import _persist_callback
            manager.connect(_persist_callback(uid, regions['id'], current_app.config['DATABASE'],
                                               current_app.extensions.get('mushroomguard_thingspeak'), manager),
                            region_id=regions['id'])
            message = f'Serial port {manager.port} opened. Waiting for a DHT11 reading.'
            ok = True
        except Exception as exc:
            message = str(exc)
    elif device == 'sensor':
        with manager.state_lock:
            state = dict(manager.latest)
        ok = _fresh(state.get('updated'))
        message = f"Latest DHT11 reading: {state.get('temperature')} °C, {state.get('humidity')}% RH." if ok else 'No fresh DHT11 frame. Open Environment, select the room and connect the Arduino.'
    elif device in ('fan', 'led'):
        try:
            if device == 'fan':
                manager.command('FAN_MODE_MANUAL')
            message = manager.command(f'{device.upper()}_ON')
            ok = True
        except Exception as exc:
            message = str(exc)
    elif device == 'database':
        try:
            db.execute('SELECT 1').fetchone()
            message, ok = 'SQLite database query successful.', True
        except Exception as exc:
            message = str(exc)
    elif device == 'qr':
        message = 'QR scan runs in the browser on the Scan QR page. The BarcodeDetector API is feature-tested there; manual bag-ID lookup is always available.'
        ok = True
    else:
        message = 'Unknown diagnostic test.'
    db.execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)',
               (uid, 'info' if ok else 'warning', f'{device.title()} test: {message}'))
    db.commit()
    flash(('PASS: ' if ok else 'CHECK: ') + message, 'success' if ok else 'warning')
    return redirect(url_for('diagnostics.index'))
