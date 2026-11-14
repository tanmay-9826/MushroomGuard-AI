from datetime import date
import uuid
from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, session, url_for
from models.database import get_db

buckets_bp = Blueprint('buckets', __name__, url_prefix='/buckets')
STAGES = {
    'mushroom': [
        'Preparation & Spawning', 'Incubation & Mycelium Growth',
        'Pinhead Formation & Fruiting', 'Harvesting'
    ],
    'microgreen': ['Seed & Tray Preparation', 'Germination', 'Growth & Development', 'Harvesting']
}
DESCRIPTIONS = {
    'mushroom': {
        1: 'Substrate preparation, spawn mixing and bag filling.',
        2: 'Mycelium spreads throughout the substrate.',
        3: 'Pinheads appear and mushrooms develop.',
        4: 'Harvest mature mushrooms and record their weight.'
    },
    'microgreen': {
        1: 'Seed selection, soaking if required, and sowing.',
        2: 'Seeds begin to sprout.',
        3: 'Shoots grow, develop leaves and turn green.',
        4: 'Harvest ready microgreens and record their weight.'
    }
}


def _uid():
    return session.get('user_id')


def _form(kind, crops, regions, values=None):
    values = values or {}
    return render_template('add_bucket.html', crop_type=kind, crops=crops, regions=regions,
        stages=STAGES[kind], stage_descriptions=DESCRIPTIONS[kind], today=date.today().isoformat(), values=values)


@buckets_bp.route('/add/<kind>', methods=['GET', 'POST'])
def add(kind):
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    if kind not in STAGES:
        abort(404)
    db = get_db()
    flag = 'grows_mushrooms' if kind == 'mushroom' else 'grows_microgreens'
    prefs = db.execute('SELECT * FROM farmer_preferences WHERE user_id=?', (uid,)).fetchone()
    if not prefs or not prefs[flag]:
        flash('Enable this crop type and select varieties in Preferences first.', 'warning')
        return redirect(url_for('auth.preferences'))
    crops = db.execute('SELECT crop_name FROM farmer_crops WHERE user_id=? AND crop_type=? ORDER BY crop_name', (uid, kind)).fetchall()
    regions = db.execute('SELECT * FROM regions WHERE user_id=? ORDER BY id', (uid,)).fetchall()
    if request.method == 'GET':
        return _form(kind, crops, regions, {'start_date': date.today().isoformat(), 'growth_stage': '1'})

    values = {k: request.form.get(k, '').strip() for k in ('crop_name','start_date','batch_code','rack','notes')}
    values['growth_stage'] = request.form.get('growth_stage', '1')
    values['region_id'] = request.form.get('region_id', '')
    allowed = {r['crop_name'] for r in crops}
    try:
        stage = int(values['growth_stage'])
        parsed_date = date.fromisoformat(values['start_date'])
        if values['crop_name'] not in allowed:
            raise ValueError('Choose one of the varieties saved in Preferences.')
        if parsed_date > date.today():
            raise ValueError('Start date cannot be in the future.')
        if stage not in (1, 2, 3, 4):
            raise ValueError('Select a valid growth stage.')
        if not values['batch_code']:
            values['batch_code'] = f"B{date.today():%y%m%d}"
        region_id = int(values['region_id']) if values['region_id'] else None
        if region_id is not None and not db.execute('SELECT 1 FROM regions WHERE id=? AND user_id=?', (region_id, uid)).fetchone():
            raise ValueError('Select a valid room/region.')
    except (TypeError, ValueError) as exc:
        flash(str(exc) if str(exc) else 'Enter a valid stage and start date.', 'danger')
        return _form(kind, crops, regions, values)

    try:
        cursor = db.execute('''INSERT INTO cultivation_units
            (user_id,crop_type,crop_name,unit_name,batch_code,rack,region_id,start_date,growth_stage,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?)''',
            (uid, kind, values['crop_name'], f'PENDING-{uuid.uuid4().hex}', values['batch_code'], values['rack'], region_id,
             values['start_date'], stage, values['notes']))
        unit_id = cursor.lastrowid
        prefix = 'MUSH' if kind == 'mushroom' else 'MICRO'
        unit_name = f'{prefix}-{unit_id:05d}'
        db.execute('UPDATE cultivation_units SET unit_name=? WHERE id=?', (unit_name, unit_id))
        db.execute('''INSERT INTO cultivation_stage_history(unit_id,user_id,growth_stage,previous_stage,new_stage,notes)
                      VALUES(?,?,?,NULL,?,?)''', (unit_id, uid, stage, stage, 'Initial stage'))
        db.execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)', (uid, 'info', f'Created {unit_name}'))
        db.commit()
        flash(f'{unit_name} created successfully.', 'success')
        return redirect(url_for('buckets.detail', unit_id=unit_id))
    except Exception:
        db.rollback()
        current_app.logger.exception('Could not create growing unit')
        flash('The growing unit could not be saved. Check the application log.', 'danger')
        return _form(kind, crops, regions, values)


@buckets_bp.get('/<int:unit_id>')
def detail(unit_id):
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    db = get_db()
    unit = db.execute('''SELECT u.*,r.region_name FROM cultivation_units u LEFT JOIN regions r ON r.id=u.region_id
                         WHERE u.id=? AND u.user_id=?''', (unit_id, uid)).fetchone()
    if not unit:
        abort(404)
    history = db.execute('SELECT * FROM cultivation_stage_history WHERE unit_id=? AND user_id=? ORDER BY id DESC', (unit_id, uid)).fetchall()
    health = db.execute('SELECT * FROM health_records WHERE unit_id=? AND user_id=? ORDER BY id DESC LIMIT 10', (unit_id, uid)).fetchall()
    harvests = db.execute('SELECT * FROM harvest_records WHERE unit_id=? AND user_id=? ORDER BY harvest_date DESC,id DESC', (unit_id, uid)).fetchall()
    regions = db.execute('SELECT * FROM regions WHERE user_id=? ORDER BY id', (uid,)).fetchall()
    kind = unit['crop_type']
    return render_template('bucket_detail.html', unit=unit, history=history, health=health, harvests=harvests,
                           stages=STAGES[kind], stage_descriptions=DESCRIPTIONS[kind], regions=regions, today=date.today().isoformat())


@buckets_bp.post('/<int:unit_id>/stage')
def update_stage(unit_id):
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    db = get_db()
    unit = db.execute('SELECT * FROM cultivation_units WHERE id=? AND user_id=?', (unit_id, uid)).fetchone()
    if not unit:
        abort(404)
    try:
        new_stage = int(request.form.get('growth_stage', '0'))
        if new_stage not in (1,2,3,4):
            raise ValueError
    except ValueError:
        flash('Select a valid growth stage.', 'danger')
        return redirect(url_for('buckets.detail', unit_id=unit_id))
    if new_stage == unit['growth_stage']:
        flash('This unit is already at that stage.', 'info')
        return redirect(url_for('buckets.detail', unit_id=unit_id))
    note = request.form.get('notes', '').strip()[:500]
    db.execute('UPDATE cultivation_units SET growth_stage=? WHERE id=? AND user_id=?', (new_stage, unit_id, uid))
    db.execute('''INSERT INTO cultivation_stage_history(unit_id,user_id,growth_stage,previous_stage,new_stage,notes)
                  VALUES(?,?,?,?,?,?)''', (unit_id, uid, new_stage, unit['growth_stage'], new_stage, note))
    db.execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)', (uid, 'info', f"{unit['unit_name']} stage updated to {new_stage}"))
    db.commit()
    flash('Growth stage and history updated.', 'success')
    return redirect(url_for('buckets.detail', unit_id=unit_id))


@buckets_bp.post('/<int:unit_id>/harvest')
def harvest(unit_id):
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    db = get_db()
    unit = db.execute('SELECT * FROM cultivation_units WHERE id=? AND user_id=?', (unit_id, uid)).fetchone()
    if not unit:
        abort(404)
    try:
        weight = float(request.form.get('weight', ''))
        harvest_date = date.fromisoformat(request.form.get('harvest_date', date.today().isoformat()))
        if not 0 < weight <= 100000 or harvest_date > date.today():
            raise ValueError
    except (ValueError, TypeError):
        flash('Enter a valid harvest date and positive weight.', 'danger')
        return redirect(url_for('buckets.detail', unit_id=unit_id))
    unit_label = request.form.get('unit', 'kg')
    if unit_label not in ('kg','g','tray','bunch'):
        unit_label = 'kg'
    quality = request.form.get('quality', 'Good')
    if quality not in ('Good','Average','Reject'):
        quality = 'Good'
    notes = request.form.get('notes', '').strip()[:500]
    db.execute('INSERT INTO harvest_records(user_id,unit_id,harvest_date,weight,unit,quality,notes) VALUES(?,?,?,?,?,?,?)',
               (uid, unit_id, harvest_date.isoformat(), weight, unit_label, quality, notes))
    db.execute('UPDATE cultivation_units SET status=? WHERE id=? AND user_id=?',
               ('harvested' if unit['growth_stage'] == 4 else unit['status'], unit_id, uid))
    db.commit()
    flash('Harvest record saved.', 'success')
    return redirect(url_for('buckets.detail', unit_id=unit_id))


@buckets_bp.get('/<int:unit_id>/qr.png')
def qr(unit_id):
    uid = _uid()
    if not uid:
        abort(401)
    unit = get_db().execute('SELECT unit_name FROM cultivation_units WHERE id=? AND user_id=?', (unit_id, uid)).fetchone()
    if not unit:
        abort(404)
    try:
        import qrcode
        from io import BytesIO
        from flask import send_file
        payload = f"MUSHROOMGUARD:{unit['unit_name']}"
        image = qrcode.make(payload)
        output = BytesIO()
        image.save(output, format='PNG')
        output.seek(0)
        return send_file(output, mimetype='image/png', download_name=f"{unit['unit_name']}-qr.png")
    except ImportError:
        abort(503, description='Install qrcode[pil] to generate printable QR labels.')


@buckets_bp.post('/<int:unit_id>/archive')
def archive(unit_id):
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    db = get_db()
    unit = db.execute('SELECT unit_name FROM cultivation_units WHERE id=? AND user_id=?', (unit_id, uid)).fetchone()
    if not unit:
        abort(404)
    db.execute("UPDATE cultivation_units SET status='archived' WHERE id=? AND user_id=?", (unit_id, uid))
    db.execute('INSERT INTO system_logs(user_id,level,message) VALUES(?,?,?)', (uid, 'info', f"Archived {unit['unit_name']}"))
    db.commit()
    flash(f"{unit['unit_name']} archived. Its history has been retained.", 'success')
    return redirect(url_for('inventory.index'))


@buckets_bp.get('/scan')
def scan():
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    return render_template('scan.html')


@buckets_bp.post('/scan')
def scan_lookup():
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    raw = request.form.get('code', '').strip()[:100]
    code = raw.split(':', 1)[1] if raw.upper().startswith('MUSHROOMGUARD:') else raw
    code = code.strip().upper()
    db = get_db()
    unit = db.execute('SELECT id FROM cultivation_units WHERE unit_name=? AND user_id=?', (code, uid)).fetchone()
    if not unit:
        flash('No growing unit matched that QR / bag ID.', 'warning')
        return redirect(url_for('buckets.scan'))
    return redirect(url_for('buckets.detail', unit_id=unit['id']))
