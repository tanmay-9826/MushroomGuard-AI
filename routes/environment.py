import sqlite3
from datetime import datetime
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from models.database import get_db

environment_bp = Blueprint('environment', __name__)


def _uid():
    return session.get('user_id')


def _manager():
    return current_app.extensions['mushroomguard_hardware']


def _state(manager):
    with manager.state_lock:
        return dict(manager.latest)


def _check_environment(db, uid, region_id, temperature, humidity, co2=None):
    region = db.execute('SELECT * FROM regions WHERE id=? AND user_id=?', (region_id, uid)).fetchone()
    if not region:
        return
    rules = [
        ('temperature_low', temperature < region['temperature_min'], 'warning', f"Temperature is below the {region['region_name']} target range ({temperature:.1f} °C; target {region['temperature_min']:.1f}–{region['temperature_max']:.1f} °C)."),
        ('temperature_high', temperature > region['temperature_max'], 'warning', f"Temperature is above the {region['region_name']} target range ({temperature:.1f} °C; target {region['temperature_min']:.1f}–{region['temperature_max']:.1f} °C)."),
        ('humidity_low', humidity < region['humidity_min'], 'warning', f"Humidity is below the {region['region_name']} target range ({humidity:.1f}% RH; target {region['humidity_min']:.1f}–{region['humidity_max']:.1f}%)."),
        ('humidity_high', humidity > region['humidity_max'], 'warning', f"Humidity is above the {region['region_name']} target range ({humidity:.1f}% RH; target {region['humidity_min']:.1f}–{region['humidity_max']:.1f}%)."),
    ]
    if co2 is not None:
        rules.extend([
            ('co2_high', co2 > region['co2_max'], 'warning', f"CO₂ reading is above the {region['region_name']} configured maximum ({co2:.0f} ppm; maximum {region['co2_max']:.0f} ppm)."),
        ])
    for alert_type, triggered, severity, message in rules:
        active = db.execute('SELECT id FROM environment_alerts WHERE user_id=? AND region_id=? AND alert_type=? AND active=1',
                            (uid, region_id, alert_type)).fetchone()
        if triggered and message and not active:
            db.execute('INSERT INTO environment_alerts(user_id,region_id,alert_type,severity,message) VALUES(?,?,?,?,?)',
                       (uid, region_id, alert_type, severity, message))
            db.execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)', (uid, severity, message))
        elif not triggered and active:
            db.execute('UPDATE environment_alerts SET active=0,resolved_at=CURRENT_TIMESTAMP WHERE user_id=? AND region_id=? AND alert_type=? AND active=1',
                       (uid, region_id, alert_type))


def _persist_callback(uid, region_id, database_path, publisher=None, manager=None):
    def save(temperature, humidity):
        connection = sqlite3.connect(database_path, timeout=20)
        connection.execute('PRAGMA busy_timeout=20000')
        try:
            cursor = connection.execute('INSERT INTO environment_logs(user_id,region_id,temperature,humidity,source) VALUES(?,?,?,?,?)',
                               (uid, region_id, temperature, humidity, 'arduino'))
            # Environment thresholds are stored per room. Use a small SQL-only
            # equivalent here because Flask's application context is not active
            # on the serial reader thread.
            region = connection.execute('SELECT region_name,temperature_min,temperature_max,humidity_min,humidity_max FROM regions WHERE id=? AND user_id=?',
                                        (region_id, uid)).fetchone()
            if region:
                alerts = [
                    ('temperature_low', temperature < region[1], f'Temperature below target in {region[0]}: {temperature:.1f} °C.'),
                    ('temperature_high', temperature > region[2], f'Temperature above target in {region[0]}: {temperature:.1f} °C.'),
                    ('humidity_low', humidity < region[3], f'Humidity below target in {region[0]}: {humidity:.1f}% RH.'),
                    ('humidity_high', humidity > region[4], f'Humidity above target in {region[0]}: {humidity:.1f}% RH.'),
                ]
                for alert_type, triggered, message in alerts:
                    exists = connection.execute('SELECT id FROM environment_alerts WHERE user_id=? AND region_id=? AND alert_type=? AND active=1',
                                                 (uid, region_id, alert_type)).fetchone()
                    if triggered and not exists:
                        connection.execute('INSERT INTO environment_alerts(user_id,region_id,alert_type,severity,message) VALUES(?,?,?,?,?)',
                                            (uid, region_id, alert_type, 'warning', message))
                        connection.execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)', (uid, 'warning', message))
                    elif not triggered and exists:
                        connection.execute('UPDATE environment_alerts SET active=0,resolved_at=CURRENT_TIMESTAMP WHERE user_id=? AND region_id=? AND alert_type=? AND active=1',
                                            (uid, region_id, alert_type))
            connection.commit()
        finally:
            connection.close()
        # Queue cloud upload after the local SQLite write. The publisher is
        # asynchronous and rate-limited, so serial reading and fan control are
        # never blocked by a ThingSpeak/network request.
        if publisher is not None and publisher.enabled:
            telemetry = {}
            if manager is not None:
                with manager.state_lock:
                    telemetry = dict(manager.latest)
            publisher.submit(temperature, humidity, telemetry=telemetry, region_id=region_id)
    return save


@environment_bp.get('/environment')
def index():
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    db = get_db()
    regions = db.execute('SELECT * FROM regions WHERE user_id=? ORDER BY id', (uid,)).fetchall()
    region_id = request.args.get('region', type=int)
    region = next((r for r in regions if r['id'] == region_id), None) if region_id else (regions[0] if regions else None)
    logs = db.execute('SELECT * FROM environment_logs WHERE user_id=? AND region_id=? ORDER BY id DESC LIMIT 48',
                      (uid, region['id'])).fetchall() if region else []
    active_alerts = db.execute('SELECT * FROM environment_alerts WHERE user_id=? AND active=1 AND (region_id=? OR ? IS NULL) ORDER BY id DESC LIMIT 8',
                               (uid, region['id'] if region else None, region['id'] if region else None)).fetchall()
    manager = _manager()
    state = _state(manager)
    fresh = False
    if state.get('updated'):
        try:
            fresh = (datetime.now() - datetime.strptime(state['updated'], '%Y-%m-%d %H:%M:%S')).total_seconds() <= 20
        except ValueError:
            fresh = False
    sensor_online = bool(fresh and state.get('connected') and region and state.get('region_id') == region['id'])
    settings = db.execute('SELECT * FROM user_device_settings WHERE user_id=?', (uid,)).fetchone()
    risk_items = []
    if logs and region:
        last = logs[0]
        for label, value, low, high, unit in (
            ('Temperature', last['temperature'], region['temperature_min'], region['temperature_max'], '°C'),
            ('Humidity', last['humidity'], region['humidity_min'], region['humidity_max'], '% RH'),
        ):
            if value is not None:
                risk_items.append({'label': label, 'value': value, 'unit': unit, 'in_range': low <= value <= high, 'target': f'{low:g}–{high:g} {unit}'})
    return render_template('environment.html', regions=regions, region=region, logs=logs,
        chart_logs=list(reversed(logs)), hardware=state, serial_port=settings['serial_port'] if settings else '',
        serial_baud=settings['serial_baud'] if settings else 9600, sensor_online=sensor_online,
        active_alerts=active_alerts, risk_items=risk_items)


@environment_bp.post('/environment/reading')
def add_reading():
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    db = get_db()
    region_id = request.form.get('region_id', type=int)
    if not region_id or not db.execute('SELECT 1 FROM regions WHERE id=? AND user_id=?', (region_id, uid)).fetchone():
        flash('Select a valid room.', 'danger')
        return redirect(url_for('environment.index'))
    try:
        temperature = float(request.form.get('temperature', ''))
        humidity = float(request.form.get('humidity', ''))
        co2_text = request.form.get('co2', '').strip()
        co2 = float(co2_text) if co2_text else None
        if not (-10 <= temperature <= 60 and 0 <= humidity <= 100 and (co2 is None or 250 <= co2 <= 10000)):
            raise ValueError
    except (TypeError, ValueError):
        flash('Enter valid temperature, humidity and optional CO₂ readings.', 'danger')
        return redirect(url_for('environment.index', region=region_id))
    db.execute('INSERT INTO environment_logs(user_id,region_id,temperature,humidity,co2,source) VALUES(?,?,?,?,?,?)',
               (uid, region_id, temperature, humidity, co2, 'manual'))
    _check_environment(db, uid, region_id, temperature, humidity, co2)
    db.execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)',
               (uid, 'info', f'Manual environment reading saved for room {region_id}'))
    db.commit()
    flash('Environment reading saved and checked against this room’s configured targets.', 'success')
    return redirect(url_for('environment.index', region=region_id))


@environment_bp.post('/environment/regions')
def add_region():
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    name = request.form.get('region_name', '').strip()
    if not name or len(name) > 40:
        flash('Enter a room name (up to 40 characters).', 'danger')
        return redirect(url_for('environment.index'))
    db = get_db()
    try:
        db.execute('INSERT INTO regions(user_id,region_name) VALUES(?,?)', (uid, name))
        db.commit()
        flash(f'{name} added.', 'success')
    except sqlite3.IntegrityError:
        flash('A room with that name already exists.', 'warning')
    return redirect(url_for('environment.index'))


@environment_bp.post('/environment/regions/<int:region_id>/settings')
def update_region(region_id):
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    db = get_db()
    region = db.execute('SELECT * FROM regions WHERE id=? AND user_id=?', (region_id, uid)).fetchone()
    if not region:
        return redirect(url_for('environment.index'))
    try:
        tmin, tmax = float(request.form.get('temperature_min', '22')), float(request.form.get('temperature_max', '26'))
        hmin, hmax = float(request.form.get('humidity_min', '85')), float(request.form.get('humidity_max', '90'))
        co2max = float(request.form.get('co2_max', '1000'))
        if not (-10 <= tmin < tmax <= 60 and 0 <= hmin < hmax <= 100 and 250 <= co2max <= 10000):
            raise ValueError
    except (TypeError, ValueError):
        flash('Check environmental target ranges.', 'danger')
        return redirect(url_for('environment.index', region=region_id))
    species = request.form.get('species', '').strip()[:80]
    stage = request.form.get('growth_stage', '').strip()[:80]
    db.execute('''UPDATE regions SET temperature_min=?,temperature_max=?,humidity_min=?,humidity_max=?,co2_max=?,species=?,growth_stage=?
                  WHERE id=? AND user_id=?''', (tmin, tmax, hmin, hmax, co2max, species, stage, region_id, uid))
    db.commit()
    flash('Room targets saved. Automatic fan hysteresis on the current UNO remains fixed at 25°C ON / 23°C OFF.', 'success')
    return redirect(url_for('environment.index', region=region_id))


@environment_bp.post('/environment/serial/connect')
def connect():
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    region_id = request.form.get('region_id', type=int)
    db = get_db()
    if not region_id or not db.execute('SELECT 1 FROM regions WHERE id=? AND user_id=?', (region_id, uid)).fetchone():
        flash('Select the room where the DHT11 is installed.', 'danger')
        return redirect(url_for('environment.index'))
    manager = _manager()
    settings = db.execute('SELECT * FROM user_device_settings WHERE user_id=?', (uid,)).fetchone()
    if settings:
        manager.port = settings['serial_port'] or manager.port
        manager.baud = settings['serial_baud'] or manager.baud
    try:
        manager.connect(_persist_callback(uid, region_id, current_app.config['DATABASE'],
                                           current_app.extensions.get('mushroomguard_thingspeak'), manager),
                        region_id=region_id)
        db.execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)', (uid, 'info', f'Arduino serial connection opened for room {region_id}'))
        db.commit()
        flash('Serial port opened. Waiting for fresh DHT11 telemetry from the Arduino.', 'success')
    except Exception as exc:
        flash(str(exc), 'danger')
    return redirect(url_for('environment.index', region=region_id))


@environment_bp.post('/environment/serial/disconnect')
def disconnect():
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    _manager().disconnect()
    get_db().execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)', (uid, 'info', 'Arduino serial connection closed'))
    get_db().commit()
    flash('Arduino disconnected.', 'info')
    return redirect(url_for('environment.index'))


@environment_bp.post('/environment/control/<device>/<action>')
def control(device, action):
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    manager = _manager()
    db = get_db()
    region_id = request.form.get('region_id', type=int)
    if not region_id or not db.execute('SELECT 1 FROM regions WHERE id=? AND user_id=?', (region_id, uid)).fetchone():
        flash('Select a valid room before controlling hardware.', 'danger')
        return redirect(url_for('environment.index'))
    state = _state(manager)
    if not state.get('connected') or state.get('region_id') != region_id:
        flash('Connect the Arduino to this room before sending relay commands.', 'warning')
        return redirect(url_for('environment.index', region=region_id))

    try:
        if device == 'fan' and action in ('on', 'off'):
            # A direct fan override explicitly switches the UNO to manual mode.
            manager.command('FAN_MODE_MANUAL')
            result = manager.command(f'FAN_{action.upper()}')
            db.execute("UPDATE regions SET control_mode='manual' WHERE id=? AND user_id=?", (region_id, uid))
        elif device == 'fan' and action in ('auto', 'manual'):
            command = 'FAN_MODE_AUTO' if action == 'auto' else 'FAN_MODE_MANUAL'
            result = manager.command(command)
            db.execute('UPDATE regions SET control_mode=? WHERE id=? AND user_id=?', (action, region_id, uid))
        elif device == 'led' and action in ('on', 'off'):
            result = manager.command(f'LED_{action.upper()}')
        else:
            flash('Unsupported device or control action.', 'danger')
            return redirect(url_for('environment.index', region=region_id))
    except Exception as exc:
        db.rollback()
        flash(str(exc), 'danger')
        return redirect(url_for('environment.index', region=region_id))

    db.execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)',
               (uid, 'info', f'{device.upper()} {action.upper()}: {result}'))
    db.commit()
    flash(result, 'success')
    return redirect(url_for('environment.index', region=region_id))


@environment_bp.get('/environment/status')
def status():
    if not _uid():
        return jsonify({'error': 'authentication required'}), 401
    return jsonify(_state(_manager()))


@environment_bp.get('/environment/thingspeak/status')
def thingspeak_status():
    if not _uid():
        return jsonify({'error': 'authentication required'}), 401
    publisher = current_app.extensions.get('mushroomguard_thingspeak')
    if publisher is None:
        return jsonify({'enabled': False, 'connected': False, 'message': 'ThingSpeak service is not initialized.'})
    return jsonify(publisher.status())


@environment_bp.get('/environment/thingspeak/latest')
def thingspeak_latest():
    if not _uid():
        return jsonify({'error': 'authentication required'}), 401
    publisher = current_app.extensions.get('mushroomguard_thingspeak')
    if publisher is None or not publisher.enabled:
        return jsonify({'error': 'ThingSpeak is not configured. Add channel credentials to .env.'}), 503
    try:
        return jsonify(publisher.fetch_latest())
    except Exception as exc:
        return jsonify({'error': str(exc)}), 502


@environment_bp.get('/environment/alerts')
def alerts():
    uid = _uid()
    if not uid:
        return jsonify({'error': 'authentication required'}), 401
    rows = get_db().execute('SELECT * FROM environment_alerts WHERE user_id=? AND active=1 ORDER BY id DESC LIMIT 20', (uid,)).fetchall()
    return jsonify([dict(row) for row in rows])
