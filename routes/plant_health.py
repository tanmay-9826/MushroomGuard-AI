import csv
import json
import uuid
import time
from io import StringIO, BytesIO
from pathlib import Path
from flask import Blueprint, Response, abort, current_app, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, session, stream_with_context, url_for
from werkzeug.utils import secure_filename
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from models.database import get_db
from services import hardware as hardware_service
from services.camlora import camlora_endpoint, normalize_camlora_base_url
from services.unit_qr import decode_unit_qr_from_jpeg, parse_unit_qr_payload, stage_name
from services.yolo_growth import GrowthModelNotReady, crop_model_slug, predict_stage

plant_health_bp = Blueprint('plant_health', __name__)


def _owned_unit(db, uid, value):
    if not value:
        return None
    try:
        unit_id = int(value)
    except (TypeError, ValueError):
        raise ValueError('Select a valid bag or tray.')
    if not db.execute('SELECT 1 FROM cultivation_units WHERE id=? AND user_id=?', (unit_id, uid)).fetchone():
        raise ValueError('That growing unit does not belong to this account.')
    return unit_id


def _save_upload(file):
    if not file or not file.filename:
        return None
    filename = secure_filename(file.filename)
    extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    if extension not in current_app.config['ALLOWED_IMAGE_EXTENSIONS']:
        raise ValueError('Only JPG, JPEG, PNG and WEBP images are accepted.')
    stored = f'{uuid.uuid4().hex}.{extension}'
    destination = Path(current_app.config['UPLOAD_FOLDER']) / stored
    file.save(destination)
    if destination.stat().st_size > current_app.config['MAX_IMAGE_BYTES']:
        destination.unlink(missing_ok=True)
        raise ValueError('Image exceeds the 10 MB image limit.')
    # Reject obviously invalid payloads when OpenCV is installed, without making
    # OpenCV a hard dependency for ordinary manual observations.
    if hardware_service.cv2 is not None:
        image = hardware_service.cv2.imread(str(destination))
        if image is None:
            destination.unlink(missing_ok=True)
            raise ValueError('The uploaded file is not a readable image.')
    return stored


@plant_health_bp.get('/plant-health')
def index():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('auth.login'))
    db = get_db()
    search = request.args.get('q', '').strip()[:60]
    status = request.args.get('status', '').strip()
    rack = request.args.get('rack', '').strip()
    batch = request.args.get('batch', '').strip()
    clauses, params = ['u.user_id=?', "u.status<>'archived'"], [uid]
    if search:
        clauses.append('(u.unit_name LIKE ? OR u.crop_name LIKE ? OR u.batch_code LIKE ?)')
        params.extend([f'%{search}%'] * 3)
    if status in ('healthy', 'review', 'high_alert', 'under_observation', 'unassessed'):
        clauses.append('u.health_status=?')
        params.append(status)
    if rack:
        clauses.append('u.rack=?')
        params.append(rack)
    if batch:
        clauses.append('u.batch_code=?')
        params.append(batch)
    units = db.execute('''SELECT u.*,r.region_name,
        CAST(julianday('now')-julianday(u.start_date) AS INTEGER) age_days,
        (SELECT image_name FROM health_records h WHERE h.unit_id=u.id AND h.user_id=u.user_id AND h.image_name IS NOT NULL ORDER BY h.id DESC LIMIT 1) latest_image,
        (SELECT created_at FROM health_records h WHERE h.unit_id=u.id AND h.user_id=u.user_id ORDER BY h.id DESC LIMIT 1) last_observation,
        (SELECT observation FROM health_records h WHERE h.unit_id=u.id AND h.user_id=u.user_id ORDER BY h.id DESC LIMIT 1) latest_note
        FROM cultivation_units u LEFT JOIN regions r ON r.id=u.region_id WHERE ''' + ' AND '.join(clauses) + ' ORDER BY u.id DESC', params).fetchall()
    counts = {r['health_status']: r['n'] for r in db.execute(
        "SELECT health_status,COUNT(*) n FROM cultivation_units WHERE user_id=? AND status<>'archived' GROUP BY health_status", (uid,)).fetchall()}
    selected_id = request.args.get('unit_id', type=int)
    selected = next((u for u in units if u['id'] == selected_id), None) if selected_id else (units[0] if units else None)
    records = db.execute('''SELECT h.*,u.unit_name,u.crop_name,u.crop_type FROM health_records h
        LEFT JOIN cultivation_units u ON u.id=h.unit_id WHERE h.user_id=? ORDER BY h.id DESC LIMIT 40''', (uid,)).fetchall()
    detail_records = db.execute('SELECT * FROM health_records WHERE user_id=? AND unit_id=? ORDER BY id DESC LIMIT 12',
                                (uid, selected['id'])).fetchall() if selected else []
    unit_environment = None
    if selected and selected['region_id']:
        unit_environment = db.execute('''SELECT e.temperature,e.humidity,e.recorded_at,r.region_name,
            r.temperature_min,r.temperature_max,r.humidity_min,r.humidity_max
            FROM environment_logs e JOIN regions r ON r.id=e.region_id
            WHERE e.user_id=? AND e.region_id=? ORDER BY e.id DESC LIMIT 1''',
            (uid, selected['region_id'])).fetchone()
    recommendations = {
        'healthy': 'Continue routine visual checks and update the growth stage when the crop reaches the next stage.',
        'under_observation': 'Capture a clear baseline photo, inspect the unit again during the next check, and record any change.',
        'review': 'Inspect for unusual colour, texture, moisture or odour. Compare with earlier photos and record a follow-up observation.',
        'high_alert': 'Inspect promptly. Keep the unit separate from healthy production if contamination is suspected, and follow your farm hygiene procedure.',
        'unassessed': 'Record a baseline photo and complete a farmer health assessment before relying on this unit in health counts.',
    }
    camera_settings = db.execute('SELECT camera_index FROM user_device_settings WHERE user_id=?', (uid,)).fetchone()
    racks = [r[0] for r in db.execute("SELECT DISTINCT rack FROM cultivation_units WHERE user_id=? AND rack<>'' ORDER BY rack", (uid,)).fetchall()]
    batches = [r[0] for r in db.execute("SELECT DISTINCT batch_code FROM cultivation_units WHERE user_id=? AND batch_code<>'' ORDER BY batch_code DESC", (uid,)).fetchall()]
    all_units = db.execute("SELECT id,unit_name,crop_name,crop_type,growth_stage FROM cultivation_units WHERE user_id=? AND status<>'archived' ORDER BY id DESC", (uid,)).fetchall()
    video_recordings = db.execute("""SELECT v.*,u.unit_name,u.crop_name,u.crop_type,
        (SELECT COUNT(*) FROM video_frames f WHERE f.recording_id=v.id AND f.user_id=v.user_id) frame_total
        FROM video_recordings v JOIN cultivation_units u ON u.id=v.unit_id
        WHERE v.user_id=? ORDER BY v.id DESC LIMIT 10""", (uid,)).fetchall()
    video_previews = {}
    for video in video_recordings:
        video_previews[video['id']] = db.execute('SELECT filename,seconds_offset,stage_label FROM video_frames WHERE recording_id=? AND user_id=? ORDER BY frame_index LIMIT 4', (video['id'], uid)).fetchall()
    camlora_base = normalize_camlora_base_url(current_app.config.get('CAMLORA_BASE_URL', ''))
    return render_template('plant_health.html', units=units, all_units=all_units, video_recordings=video_recordings, video_previews=video_previews, counts=counts,
        selected=selected, detail_records=detail_records, records=records, search=search,
        status_filter=status, rack_filter=rack, batch_filter=batch, racks=racks, batches=batches,
        camera_available=hardware_service.cv2 is not None, camera_index=camera_settings['camera_index'] if camera_settings else current_app.config.get('CAMERA_INDEX', 0),
        camlora_configured=bool(camlora_base),
        camlora_scan_url=url_for('plant_health.camlora_scan'),
        unit_environment=unit_environment, recommendations=recommendations, ai_model_available=False)


@plant_health_bp.post('/plant-health/record')
def record():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('auth.login'))
    db = get_db()
    observation = request.form.get('observation', '').strip()
    severity = request.form.get('severity', 'info')
    if severity not in ('info', 'warning', 'urgent', 'review'):
        severity = 'info'
    if not observation or len(observation) > 2000:
        flash('Enter an observation (up to 2,000 characters).', 'danger')
        return redirect(url_for('plant_health.index'))
    image_name = None
    try:
        unit_id = _owned_unit(db, uid, request.form.get('unit_id'))
        image_name = _save_upload(request.files.get('image'))
        db.execute('INSERT INTO health_records(user_id,unit_id,observation,severity,image_name) VALUES(?,?,?,?,?)',
                   (uid, unit_id, observation, severity, image_name))
        mapped = {'info': 'under_observation', 'review': 'review', 'warning': 'review', 'urgent': 'high_alert'}[severity]
        if unit_id:
            db.execute('UPDATE cultivation_units SET health_status=? WHERE id=? AND user_id=?', (mapped, unit_id, uid))
        db.execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)',
                   (uid, 'warning' if severity in ('warning', 'urgent') else 'info', 'Plant health observation recorded'))
        db.commit()
        flash('Observation and photo record saved. No AI diagnosis was performed.', 'success')
    except ValueError as exc:
        if image_name:
            (Path(current_app.config['UPLOAD_FOLDER']) / image_name).unlink(missing_ok=True)
        flash(str(exc), 'danger')
    except Exception:
        if image_name:
            (Path(current_app.config['UPLOAD_FOLDER']) / image_name).unlink(missing_ok=True)
        db.rollback()
        current_app.logger.exception('Failed to save plant-health record')
        flash('Could not save the observation.', 'danger')
    return redirect(url_for('plant_health.index'))


@plant_health_bp.post('/plant-health/capture')
def capture():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('auth.login'))
    db = get_db()
    destination = Path(current_app.config['UPLOAD_FOLDER']) / f'camera_{uuid.uuid4().hex}.jpg'
    try:
        unit_id = _owned_unit(db, uid, request.form.get('unit_id'))
        manager = current_app.extensions['mushroomguard_hardware']
        camera_settings = db.execute('SELECT camera_index FROM user_device_settings WHERE user_id=?', (uid,)).fetchone()
        if camera_settings:
            manager.camera_index = camera_settings['camera_index']
        manager.camera_snapshot(destination)
        db.execute('INSERT INTO health_records(user_id,unit_id,observation,severity,image_name) VALUES(?,?,?,?,?)',
                   (uid, unit_id, 'Still image captured from the configured USB camera. AI analysis is not available.', 'info', destination.name))
        db.commit()
        flash('Camera photo captured and saved to Plant Health.', 'success')
    except Exception as exc:
        destination.unlink(missing_ok=True)
        db.rollback()
        flash(f'Camera capture failed: {exc}', 'danger')
    return redirect(url_for('plant_health.index'))


@plant_health_bp.get('/plant-health/camlora/stream')
def camlora_stream():
    """Proxy Camlora's local MJPEG stream through the authenticated Flask app."""
    if not session.get('user_id'):
        abort(401)
    base = normalize_camlora_base_url(current_app.config.get('CAMLORA_BASE_URL', ''))
    stream_url = camlora_endpoint(base, 'video') if base else None
    if not stream_url:
        return jsonify(ok=False, error='Camlora is not configured. Add CAMLORA_BASE_URL to .env and restart MushroomGuard AI.'), 503

    upstream = None
    try:
        upstream = urlopen(Request(stream_url, headers={'User-Agent': 'MushroomGuardAI/1.2'}), timeout=8)
        content_type = upstream.headers.get('Content-Type', '')
        if upstream.status != 200 or 'multipart/x-mixed-replace' not in content_type.lower():
            upstream.close()
            return jsonify(ok=False, error=f'Camlora returned an unexpected stream response ({content_type or upstream.status}).'), 502
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        if upstream:
            upstream.close()
        current_app.logger.warning('Camlora stream connection failed: %s', exc)
        return jsonify(ok=False, error='Cannot reach Camlora. Check the phone IP, USB tethering and that streaming is running.'), 502

    def generate():
        try:
            reader = getattr(upstream, 'read1', upstream.read)
            while True:
                chunk = reader(8192)
                if not chunk:
                    break
                yield chunk
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            upstream.close()

    return Response(stream_with_context(generate()), content_type=content_type,
                    headers={'Cache-Control': 'no-store, no-cache, must-revalidate',
                             'Pragma': 'no-cache', 'X-Accel-Buffering': 'no'})


def _fetch_camlora_jpeg():
    # Fetch one bounded JPEG snapshot from the configured private Camlora host.
    base = normalize_camlora_base_url(current_app.config.get('CAMLORA_BASE_URL', ''))
    snapshot_url = camlora_endpoint(base, 'shot.jpg') if base else None
    if not snapshot_url:
        raise ValueError('Camlora is not configured. Add CAMLORA_BASE_URL to .env and restart MushroomGuard AI.')
    upstream = urlopen(Request(snapshot_url, headers={'User-Agent': 'MushroomGuardAI/1.3'}), timeout=6)
    try:
        content_type = upstream.headers.get('Content-Type', '').lower()
        image_bytes = upstream.read(current_app.config['MAX_IMAGE_BYTES'] + 1)
    finally:
        upstream.close()
    if len(image_bytes) > current_app.config['MAX_IMAGE_BYTES']:
        raise ValueError('The camera snapshot exceeds the 10 MB image limit.')
    if not image_bytes.startswith(b'\xff\xd8\xff') or ('image/jpeg' not in content_type and content_type):
        raise ValueError('Camlora did not return a valid JPEG snapshot.')
    return image_bytes


@plant_health_bp.post('/plant-health/camlora/scan')
def camlora_scan():
    # The QR identifies a unit. The returned stage is read from SQLite; this is
    # not a vision model and does not classify biological growth stage.
    uid = session.get('user_id')
    if not uid:
        return jsonify(ok=False, error='Your session has expired. Log in again.'), 401
    if hardware_service.cv2 is None:
        return jsonify(ok=False, error='OpenCV is not installed. Install requirements.txt to enable QR scanning.'), 503
    try:
        image_bytes = _fetch_camlora_jpeg()
        raw_payload = decode_unit_qr_from_jpeg(image_bytes)
        if not raw_payload:
            session.pop('camlora_verified_unit_id', None)
            session.pop('camlora_verified_at', None)
            return jsonify(ok=True, detected=False, message='No QR code found yet. Keep the unit label inside the camera frame.'), 200
        unit_code = parse_unit_qr_payload(raw_payload)
        if not unit_code:
            session.pop('camlora_verified_unit_id', None)
            session.pop('camlora_verified_at', None)
            return jsonify(ok=True, detected=True, registered=False,
                           message='A QR code was detected, but it is not a valid MushroomGuard growing-unit label.'), 200
        db = get_db()
        unit = db.execute('''SELECT id,unit_name,crop_type,crop_name,growth_stage,start_date,batch_code,rack,health_status,status
                             FROM cultivation_units WHERE unit_name=? AND user_id=? AND status<>'archived' ''',
                          (unit_code, uid)).fetchone()
        if not unit:
            # Do not reveal whether the code belongs to a different farmer.
            session.pop('camlora_verified_unit_id', None)
            session.pop('camlora_verified_at', None)
            return jsonify(ok=True, detected=True, registered=False, unit_code=unit_code,
                           message='This ID is not registered in your growing units.'), 200
        stage = int(unit['growth_stage'])
        session['camlora_verified_unit_id'] = int(unit['id'])
        session['camlora_verified_at'] = time.time()
        return jsonify(ok=True, detected=True, registered=True,
                       unit={
                           'id': unit['id'], 'unit_name': unit['unit_name'],
                           'crop_type': unit['crop_type'], 'crop_name': unit['crop_name'],
                           'growth_stage': stage, 'stage_name': stage_name(unit['crop_type'], stage),
                           'start_date': unit['start_date'], 'batch_code': unit['batch_code'] or '',
                           'rack': unit['rack'] or '', 'health_status': unit['health_status'],
                           'detail_url': url_for('buckets.detail', unit_id=unit['id'])
                       },
                       message='Registered growing unit verified. Current stage loaded from the database.'), 200
    except ValueError as exc:
        return jsonify(ok=False, error=str(exc)), 400
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        current_app.logger.warning('Camlora QR scan failed: %s', exc)
        return jsonify(ok=False, error='Cannot reach the Camlora snapshot. Check USB tethering, phone IP and camera streaming.'), 502
    except Exception:
        current_app.logger.exception('Unexpected Camlora QR scan error')
        return jsonify(ok=False, error='QR scanning failed. Check the application log.'), 500


@plant_health_bp.post('/plant-health/camlora/capture')
def camlora_capture():
    # Save a camera photograph. A stage update is only applied after the farmer
    # explicitly confirms the observed stage in the UI.
    uid = session.get('user_id')
    if not uid:
        return jsonify(ok=False, error='Your session has expired. Log in again.'), 401

    db = get_db()
    destination = None
    try:
        unit_id = _owned_unit(db, uid, request.form.get('unit_id'))
        unit = None
        if unit_id:
            unit = db.execute('''SELECT id,unit_name,crop_type,crop_name,growth_stage
                                 FROM cultivation_units WHERE id=? AND user_id=?''', (unit_id, uid)).fetchone()
            if not unit:
                return jsonify(ok=False, error='The selected growing unit is not registered to this account.'), 404

        confirm_stage = request.form.get('confirm_stage') == '1'
        requested_stage = request.form.get('observed_stage', '').strip()
        if confirm_stage:
            if not unit:
                return jsonify(ok=False, error='Scan and verify a registered unit before updating its stage.'), 400
            verified_id = session.get('camlora_verified_unit_id')
            verified_at = session.get('camlora_verified_at', 0)
            if int(verified_id or 0) != int(unit_id) or (time.time() - float(verified_at or 0)) > 600:
                return jsonify(ok=False, error='Scan this growing unit QR with Camlora immediately before confirming a stage update.'), 409
            try:
                observed_stage = int(requested_stage)
            except (TypeError, ValueError):
                return jsonify(ok=False, error='Choose the stage that you observed in the photograph.'), 400
            if observed_stage not in (1, 2, 3, 4):
                return jsonify(ok=False, error='Choose a valid growth stage.'), 400
        else:
            observed_stage = None

        image_bytes = _fetch_camlora_jpeg()
        image_name = f'camlora_{uuid.uuid4().hex}.jpg'
        destination = Path(current_app.config['UPLOAD_FOLDER']) / image_name
        destination.write_bytes(image_bytes)
        note = request.form.get('observation', '').strip()[:1500]
        if not note:
            note = 'Snapshot captured from the Camlora Android camera. Visual record only; no AI diagnosis was performed.'

        stage_changed = bool(unit and confirm_stage and observed_stage != int(unit['growth_stage']))
        if confirm_stage and unit and stage_changed:
            selected_label = stage_name(unit['crop_type'], observed_stage)
            note += f' Farmer-confirmed observed stage: Stage {observed_stage} — {selected_label}.'

        db.execute('INSERT INTO health_records(user_id,unit_id,observation,severity,image_name) VALUES(?,?,?,?,?)',
                   (uid, unit_id, note, 'info', image_name))

        if stage_changed:
            db.execute('UPDATE cultivation_units SET growth_stage=? WHERE id=? AND user_id=?',
                       (observed_stage, unit_id, uid))
            db.execute('''INSERT INTO cultivation_stage_history
                          (unit_id,user_id,growth_stage,previous_stage,new_stage,notes)
                          VALUES(?,?,?,?,?,?)''',
                       (unit_id, uid, observed_stage, int(unit['growth_stage']), observed_stage,
                        f'Farmer confirmed stage after reviewing Camlora photo. Photo: {image_name}'))
            db.execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)',
                       (uid, 'info', f"{unit['unit_name']} stage changed from {unit['growth_stage']} to {observed_stage} after farmer photo review"))
        elif confirm_stage and unit:
            db.execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)',
                       (uid, 'info', f"{unit['unit_name']} stage {observed_stage} confirmed from Camlora photo; no stage change needed"))

        db.commit()
        return jsonify(ok=True, message='Camlora photograph saved to Plant Health.',
                       image_url=url_for('plant_health.image', filename=image_name),
                       unit_id=unit_id, filename=image_name, stage_changed=stage_changed,
                       previous_stage=int(unit['growth_stage']) if unit else None,
                       current_stage=observed_stage if stage_changed else (int(unit['growth_stage']) if unit else None),
                       detail_url=url_for('buckets.detail', unit_id=unit_id) if unit_id else None)
    except ValueError as exc:
        if destination:
            destination.unlink(missing_ok=True)
        db.rollback()
        return jsonify(ok=False, error=str(exc)), 400
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        if destination:
            destination.unlink(missing_ok=True)
        db.rollback()
        current_app.logger.warning('Camlora snapshot failed: %s', exc)
        return jsonify(ok=False, error='Could not retrieve a snapshot from Camlora. Check that the phone stream is running and the configured IP is current.'), 502
    except Exception:
        if destination:
            destination.unlink(missing_ok=True)
        db.rollback()
        current_app.logger.exception('Failed to save Camlora snapshot')
        return jsonify(ok=False, error='The camera image could not be saved.'), 500

@plant_health_bp.post('/plant-health/video/start')
def start_video_recording():
    uid = session.get('user_id')
    if not uid:
        return jsonify(ok=False, error='Your session has expired. Log in again.'), 401
    if hardware_service.cv2 is None:
        return jsonify(ok=False, error='OpenCV is required for MP4 recording. Install requirements.txt.'), 503
    base = normalize_camlora_base_url(current_app.config.get('CAMLORA_BASE_URL', ''))
    stream_url = camlora_endpoint(base, 'video') if base else None
    if not stream_url:
        return jsonify(ok=False, error='Camlora is not configured. Set CAMLORA_BASE_URL in .env and restart.'), 503
    db = get_db()
    try:
        payload = request.get_json(silent=True) or {}
        unit_id = _owned_unit(db, uid, request.form.get('unit_id') or payload.get('unit_id'))
        if not unit_id:
            return jsonify(ok=False, error='Select a registered mushroom bag or microgreen tray before recording.'), 400
        unit = db.execute("SELECT id,unit_name,crop_type,crop_name,status FROM cultivation_units WHERE id=? AND user_id=?", (unit_id, uid)).fetchone()
        if not unit or unit['status'] == 'archived':
            return jsonify(ok=False, error='The selected growing unit is not active or does not belong to this account.'), 404
        recorder = current_app.extensions['mushroomguard_video_recorder']
        if recorder.is_running_for_user(uid):
            return jsonify(ok=False, error='A video recording is already running for this account. Stop it before starting another.'), 409
        filename = f'mg_video_{uuid.uuid4().hex}.mp4'
        output_dir = Path(current_app.config['UPLOAD_FOLDER']) / 'videos'
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / filename
        notes = (request.form.get('notes') or payload.get('notes') or '').strip()[:500]
        cur = db.execute("INSERT INTO video_recordings(user_id,unit_id,filename,status,notes) VALUES(?,?,?,'starting',?)",
                         (uid, unit_id, filename, notes))
        recording_id = cur.lastrowid
        db.commit()
        try:
            recorder.start(recording_id, uid, stream_url, output_path,
                           max_seconds=current_app.config.get('CAMLORA_MAX_RECORDING_SECONDS', 600),
                           max_bytes=current_app.config.get('CAMLORA_MAX_RECORDING_BYTES', 300 * 1024 * 1024),
                           target_fps=current_app.config.get('CAMLORA_RECORDING_FPS', 8.0))
        except Exception as exc:
            db.execute("UPDATE video_recordings SET status='failed',error=?,stopped_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?",
                       (str(exc)[:500], recording_id, uid))
            db.commit()
            return jsonify(ok=False, error=str(exc)), 409
        return jsonify(ok=True, recording_id=recording_id, unit_name=unit['unit_name'],
                       message=f"Recording started for {unit['unit_name']}.",
                       status_url=url_for('plant_health.video_recording_status', recording_id=recording_id),
                       stop_url=url_for('plant_health.stop_video_recording', recording_id=recording_id)), 202
    except ValueError as exc:
        db.rollback()
        return jsonify(ok=False, error=str(exc)), 400
    except Exception:
        db.rollback()
        current_app.logger.exception('Could not start Camlora video recording')
        return jsonify(ok=False, error='Could not start the video recording. Check the Flask log.'), 500


@plant_health_bp.post('/plant-health/video/<int:recording_id>/stop')
def stop_video_recording(recording_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify(ok=False, error='Your session has expired. Log in again.'), 401
    db = get_db()
    row = db.execute('SELECT id,status FROM video_recordings WHERE id=? AND user_id=?', (recording_id, uid)).fetchone()
    if not row:
        abort(404)
    if row['status'] not in ('starting', 'recording'):
        return jsonify(ok=True, status=row['status'], message='This recording is already stopped.'), 200
    recorder = current_app.extensions['mushroomguard_video_recorder']
    finished = recorder.stop(recording_id, uid, wait_seconds=12)
    updated = db.execute('SELECT status,frame_count,duration_seconds,error FROM video_recordings WHERE id=? AND user_id=?',
                         (recording_id, uid)).fetchone()
    db.commit()
    return jsonify(ok=True, finished=finished, status=updated['status'],
                   frame_count=updated['frame_count'], duration_seconds=updated['duration_seconds'],
                   error=updated['error'] or '',
                   message='Recording stopped and saved.' if updated['status'] in ('stopped','completed') else 'Stop requested; recorder is finishing the current stream.'), 200


@plant_health_bp.get('/plant-health/video/<int:recording_id>/status')
def video_recording_status(recording_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify(ok=False, error='Your session has expired. Log in again.'), 401
    row = get_db().execute("""SELECT v.id,v.status,v.duration_seconds,v.frame_count,v.file_size_bytes,v.width,v.height,v.fps,v.error,
        v.analysis_status,v.predicted_stage,v.prediction_confidence,v.analysis_summary,v.confirmed_stage,
        (SELECT COUNT(*) FROM video_frames f WHERE f.recording_id=v.id AND f.user_id=v.user_id) frame_total
        FROM video_recordings v WHERE v.id=? AND v.user_id=?""", (recording_id, uid)).fetchone()
    if not row:
        abort(404)
    return jsonify(ok=True, **dict(row))


def _extract_recording_frames(recording, upload_folder, db, frame_interval, max_frames):
    if hardware_service.cv2 is None:
        raise ValueError('OpenCV is not installed; video frame extraction is unavailable.')
    video_path = Path(upload_folder) / 'videos' / recording['filename']
    if not video_path.is_file():
        raise ValueError('The recorded MP4 file is missing from uploads/videos.')
    existing = db.execute('SELECT COUNT(*) FROM video_frames WHERE recording_id=?', (recording['id'],)).fetchone()[0]
    if existing:
        return int(existing), True
    cap = hardware_service.cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        cap.release()
        raise ValueError('OpenCV could not read this MP4. Check video codec support on this PC.')
    fps = cap.get(hardware_service.cv2.CAP_PROP_FPS) or (recording['fps'] or 8.0)
    frame_count = int(cap.get(hardware_service.cv2.CAP_PROP_FRAME_COUNT) or 0)
    duration = (frame_count / fps) if fps > 0 and frame_count else float(recording['duration_seconds'] or 0)
    if duration <= 0:
        cap.release()
        raise ValueError('The recording has no readable duration.')
    frames_dir = Path(upload_folder) / 'video_frames'
    frames_dir.mkdir(parents=True, exist_ok=True)
    created = []
    try:
        offset = 0.0
        frame_index = 0
        while offset < duration and frame_index < max_frames:
            cap.set(hardware_service.cv2.CAP_PROP_POS_MSEC, offset * 1000.0)
            ok, frame = cap.read()
            if ok and frame is not None:
                filename = f'video_frame_{recording["id"]}_{uuid.uuid4().hex}.jpg'
                target = frames_dir / filename
                if not hardware_service.cv2.imwrite(str(target), frame, [int(hardware_service.cv2.IMWRITE_JPEG_QUALITY), 90]):
                    raise ValueError('Could not write an extracted JPEG frame.')
                created.append((filename, frame_index, round(offset, 2)))
                frame_index += 1
            offset += frame_interval
    except Exception:
        for filename, _, _ in created:
            (frames_dir / filename).unlink(missing_ok=True)
        raise
    finally:
        cap.release()
    if not created:
        raise ValueError('No frames could be extracted from this video.')
    for filename, index, seconds in created:
        db.execute("INSERT INTO video_frames(recording_id,user_id,unit_id,filename,frame_index,seconds_offset) VALUES(?,?,?,?,?,?)",
                   (recording['id'], recording['user_id'], recording['unit_id'], filename, index, seconds))
    db.execute("UPDATE video_recordings SET analysis_status='frames_extracted' WHERE id=?", (recording['id'],))
    return len(created), False


@plant_health_bp.post('/plant-health/video/<int:recording_id>/extract-frames')
def extract_video_frames(recording_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify(ok=False, error='Your session has expired. Log in again.'), 401
    db = get_db()
    recording = db.execute('SELECT * FROM video_recordings WHERE id=? AND user_id=?', (recording_id, uid)).fetchone()
    if not recording:
        abort(404)
    if recording['status'] not in ('stopped', 'completed'):
        return jsonify(ok=False, error='Stop and finish the recording before extracting frames.'), 409
    try:
        count, already = _extract_recording_frames(recording, current_app.config['UPLOAD_FOLDER'], db,
            current_app.config.get('VIDEO_FRAME_INTERVAL_SECONDS', 5.0),
            current_app.config.get('VIDEO_MAX_EXTRACTED_FRAMES', 120))
        db.commit()
        return jsonify(ok=True, count=count, already_extracted=already,
            message=f'{count} sampled frames are ready for farmer labelling and YOLO training data.' if not already else f'{count} frames were already extracted.')
    except ValueError as exc:
        db.rollback()
        return jsonify(ok=False, error=str(exc)), 400
    except Exception:
        db.rollback()
        current_app.logger.exception('Video frame extraction failed')
        return jsonify(ok=False, error='Video frame extraction failed. Check the Flask log.'), 500


@plant_health_bp.post('/plant-health/video/<int:recording_id>/label-frames')
def label_video_frames(recording_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify(ok=False, error='Your session has expired. Log in again.'), 401
    try:
        stage = int(request.form.get('stage', ''))
    except (TypeError, ValueError):
        return jsonify(ok=False, error='Select a valid observed growth stage.'), 400
    if stage not in (1, 2, 3, 4):
        return jsonify(ok=False, error='Growth stage must be between 1 and 4.'), 400
    db = get_db()
    recording = db.execute("""SELECT v.id,v.unit_id,u.crop_type,u.crop_name FROM video_recordings v
        JOIN cultivation_units u ON u.id=v.unit_id WHERE v.id=? AND v.user_id=? AND u.user_id=?""", (recording_id, uid, uid)).fetchone()
    if not recording:
        abort(404)
    count = db.execute('SELECT COUNT(*) FROM video_frames WHERE recording_id=? AND user_id=?', (recording_id, uid)).fetchone()[0]
    if not count:
        return jsonify(ok=False, error='Extract frames before labelling this recording.'), 409
    db.execute("UPDATE video_frames SET stage_label=?,label_source='farmer_reviewed' WHERE recording_id=? AND user_id=?", (stage, recording_id, uid))
    db.execute('UPDATE video_recordings SET label_stage=? WHERE id=? AND user_id=?', (stage, recording_id, uid))
    db.commit()
    return jsonify(ok=True, labelled_frames=count,
        message=f'{count} frames labelled as Stage {stage} by farmer review. The growing-unit stage was not changed.')


@plant_health_bp.post('/plant-health/video/<int:recording_id>/analyse')
def analyse_video_recording(recording_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify(ok=False, error='Your session has expired. Log in again.'), 401
    db = get_db()
    recording = db.execute("""SELECT v.*,u.crop_type,u.crop_name,u.unit_name FROM video_recordings v
        JOIN cultivation_units u ON u.id=v.unit_id WHERE v.id=? AND v.user_id=? AND u.user_id=?""", (recording_id, uid, uid)).fetchone()
    if not recording:
        abort(404)
    if recording['status'] not in ('stopped', 'completed'):
        return jsonify(ok=False, error='Stop the recording before analysis.'), 409
    crop_slug = crop_model_slug(recording['crop_type'], recording['crop_name'])
    if not crop_slug:
        return jsonify(ok=False, error='No crop-specific growth-stage model is registered for this growing unit. The video is saved; add a labelled dataset and train a model for this crop first.'), 409
    frames = db.execute('SELECT filename FROM video_frames WHERE recording_id=? AND user_id=? ORDER BY frame_index', (recording_id, uid)).fetchall()
    if not frames:
        return jsonify(ok=False, error='Extract video frames first, then run YOLO analysis.'), 409
    frame_paths = [Path(current_app.config['UPLOAD_FOLDER']) / 'video_frames' / row['filename'] for row in frames]
    try:
        model_dir = Path(current_app.config['YOLO_MODEL_DIR'])
        model_path = model_dir / f'{crop_slug}_growth_stage.pt'
        manifest_path = model_dir / f'{crop_slug}_growth_stage_manifest.json'
        result = predict_stage(frame_paths, model_path, manifest_path, crop_slug)
        db.execute("""UPDATE video_recordings SET analysis_status='predicted',predicted_stage=?,prediction_confidence=?,
            analysis_model=?,analysis_summary=?,analysis_details=? WHERE id=? AND user_id=?""",
            (result['stage'], result['confidence'], result['model'], result['note'],
             __import__('json').dumps(result, ensure_ascii=False), recording_id, uid))
        db.commit()
        return jsonify(ok=True, **result, stage_name=stage_name(recording['crop_type'], result['stage']),
            crop_name=recording['crop_name'],
            message=f"YOLO returned a provisional {recording['crop_name']} stage estimate from sampled video frames. Review the full video and confirm before changing the growing-unit record.")
    except GrowthModelNotReady as exc:
        db.execute("UPDATE video_recordings SET analysis_status='model_not_ready',analysis_summary=? WHERE id=? AND user_id=?", (str(exc), recording_id, uid))
        db.commit()
        return jsonify(ok=False, model_ready=False, error=str(exc)), 409
    except Exception:
        db.rollback()
        current_app.logger.exception('YOLO video analysis failed')
        return jsonify(ok=False, error='YOLO analysis failed. Check the optional AI installation and Flask log.'), 500


@plant_health_bp.post('/plant-health/video/<int:recording_id>/confirm-stage')
def confirm_video_stage(recording_id):
    uid = session.get('user_id')
    if not uid:
        return jsonify(ok=False, error='Your session has expired. Log in again.'), 401
    if request.form.get('confirm') != '1' or request.form.get('reviewed') != '1':
        return jsonify(ok=False, error='Tick the confirmation box after reviewing the full video and prediction.'), 400
    db = get_db()
    recording = db.execute("""SELECT v.*,u.growth_stage,u.unit_name,u.crop_type,u.crop_name FROM video_recordings v
        JOIN cultivation_units u ON u.id=v.unit_id WHERE v.id=? AND v.user_id=? AND u.user_id=?""", (recording_id, uid, uid)).fetchone()
    if not recording:
        abort(404)
    if recording['predicted_stage'] is None:
        return jsonify(ok=False, error='There is no YOLO prediction to confirm. Run analysis first or use the separate manual stage-update workflow.'), 409
    try:
        stage = int(request.form.get('stage', recording['predicted_stage'] or 0))
    except (TypeError, ValueError):
        stage = 0
    if stage not in (1, 2, 3, 4):
        return jsonify(ok=False, error='Select a valid stage to confirm.'), 400
    previous = int(recording['growth_stage'])
    changed = previous != stage
    if changed:
        db.execute('UPDATE cultivation_units SET growth_stage=? WHERE id=? AND user_id=?', (stage, recording['unit_id'], uid))
        label = stage_name(recording['crop_type'], stage)
        db.execute("""INSERT INTO cultivation_stage_history
            (unit_id,user_id,growth_stage,previous_stage,new_stage,notes) VALUES(?,?,?,?,?,?)""",
            (recording['unit_id'], uid, stage, previous, stage,
             f'Farmer confirmed video review for {recording["filename"]}. YOLO prediction: {recording["predicted_stage"] or "not available"}.'))
        db.execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)',
            (uid, 'info', f'{recording["unit_name"]} growth stage confirmed from video review: Stage {previous} to Stage {stage} ({label})'))
    db.execute('UPDATE video_recordings SET confirmed_stage=? WHERE id=? AND user_id=?', (stage, recording_id, uid))
    db.commit()
    return jsonify(ok=True, changed=changed, previous_stage=previous, current_stage=stage,
        stage_name=stage_name(recording['crop_type'], stage),
        message='Growing-unit stage updated and stage history saved.' if changed else 'The current growing-unit stage was confirmed; no change was needed.')


@plant_health_bp.get('/plant-health/video/<int:recording_id>/download')
def download_video_recording(recording_id):
    uid = session.get('user_id')
    if not uid:
        abort(401)
    row = get_db().execute('SELECT filename FROM video_recordings WHERE id=? AND user_id=?', (recording_id, uid)).fetchone()
    if not row:
        abort(404)
    return send_from_directory(Path(current_app.config['UPLOAD_FOLDER']) / 'videos', row['filename'], as_attachment=True)


@plant_health_bp.get('/plant-health/video/<int:recording_id>/play')
def play_video_recording(recording_id):
    uid = session.get('user_id')
    if not uid:
        abort(401)
    row = get_db().execute('SELECT filename FROM video_recordings WHERE id=? AND user_id=?',
                           (recording_id, uid)).fetchone()
    if not row:
        abort(404)
    video_path = Path(current_app.config['UPLOAD_FOLDER']) / 'videos' / row['filename']
    if not video_path.is_file():
        abort(404)
    return send_from_directory(video_path.parent, video_path.name, mimetype='video/mp4',
                               as_attachment=False, conditional=True, max_age=0)


@plant_health_bp.get('/plant-health/video/frame/<filename>')
def video_frame_image(filename):
    uid = session.get('user_id')
    if not uid:
        abort(401)
    if Path(filename).name != filename:
        abort(404)
    exists = get_db().execute('SELECT 1 FROM video_frames WHERE user_id=? AND filename=?', (uid, filename)).fetchone()
    if not exists:
        abort(404)
    return send_from_directory(Path(current_app.config['UPLOAD_FOLDER']) / 'video_frames', filename, max_age=0)


@plant_health_bp.post('/plant-health/video/frames/<filename>/label')
def label_video_frame(filename):
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('auth.login'))
    if Path(filename).name != filename:
        abort(404)
    try:
        stage = int(request.form.get('stage', ''))
    except (TypeError, ValueError):
        flash('Choose a valid stage.', 'danger')
        return redirect(url_for('plant_health.index'))
    if stage not in (1, 2, 3, 4):
        flash('Choose a valid stage.', 'danger')
        return redirect(url_for('plant_health.index'))
    db = get_db()
    row = db.execute('SELECT id,recording_id FROM video_frames WHERE user_id=? AND filename=?', (uid, filename)).fetchone()
    if not row:
        abort(404)
    db.execute("UPDATE video_frames SET stage_label=?,label_source='farmer_reviewed' WHERE id=? AND user_id=?", (stage, row['id'], uid))
    db.commit()
    flash(f'Frame labelled as Stage {stage}. This label is for dataset training only; the growing-unit stage was not changed.', 'success')
    return redirect(url_for('plant_health.index'))


@plant_health_bp.post('/plant-health/unit/<int:unit_id>/status')
def update_status(unit_id):
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('auth.login'))
    status = request.form.get('health_status', '')
    if status not in ('healthy', 'under_observation', 'review', 'high_alert', 'unassessed'):
        flash('Choose a valid health status.', 'danger')
        return redirect(url_for('plant_health.index'))
    db = get_db()
    cur = db.execute('UPDATE cultivation_units SET health_status=? WHERE id=? AND user_id=?', (status, unit_id, uid))
    if not cur.rowcount:
        abort(404)
    db.execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)', (uid, 'info', f'Health status for unit {unit_id} set to {status}'))
    db.commit()
    flash('Farmer-assessed health status updated.', 'success')
    return redirect(url_for('plant_health.index', unit_id=unit_id))


@plant_health_bp.get('/plant-health/image/<filename>')
def image(filename):
    uid = session.get('user_id')
    if not uid:
        abort(401)
    if Path(filename).name != filename:
        abort(404)
    exists = get_db().execute('SELECT 1 FROM health_records WHERE user_id=? AND image_name=?', (uid, filename)).fetchone()
    if not exists:
        abort(404)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename, max_age=0)


@plant_health_bp.get('/plant-health/export.csv')
def export():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('auth.login'))
    rows = get_db().execute('''SELECT u.unit_name,u.crop_type,u.crop_name,u.rack,u.batch_code,u.health_status,
        h.severity,h.observation,h.created_at FROM health_records h
        LEFT JOIN cultivation_units u ON u.id=h.unit_id WHERE h.user_id=? ORDER BY h.id DESC''', (uid,)).fetchall()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Bag / Tray ID', 'Crop type', 'Variety', 'Rack', 'Batch', 'Farmer health status', 'Observation severity', 'Observation', 'Recorded at'])
    writer.writerows([tuple(row) for row in rows])
    return send_file(BytesIO(output.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True, download_name='mushroomguard-plant-health.csv')
