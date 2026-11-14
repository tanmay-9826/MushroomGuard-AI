import re
import sqlite3
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from models.database import get_db


auth_bp = Blueprint('auth', __name__)
MUSHROOMS = ['Oyster Mushroom', 'Button Mushroom', 'Milky Mushroom', 'Shiitake Mushroom']
MICROGREENS = ['Methi', 'Palak', 'Radish', 'Mustard', 'Broccoli']
LANGUAGES = {'en': 'English', 'mr': 'मराठी', 'hi': 'हिन्दी'}


def login_required_redirect():
    if not session.get('user_id'):
        return redirect(url_for('auth.login'))
    return None


@auth_bp.get('/language')
def language():
    if session.get('user_id'):
        return redirect(url_for('dashboard.index'))
    return render_template('language.html')


@auth_bp.post('/select-language')
def select_language():
    code = request.form.get('language', 'en')
    session['language'] = code if code in LANGUAGES else 'en'
    if session.get('user_id'):
        db = get_db()
        db.execute('UPDATE farmer_preferences SET language=? WHERE user_id=?', (session['language'], session['user_id']))
        db.commit()
        target = request.form.get('next', '')
        return redirect(target if target.startswith('/') and not target.startswith('//') else url_for('dashboard.index'))
    return redirect(url_for('auth.register'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if session.get('user_id'):
        return redirect(url_for('dashboard.index'))
    form = request.form if request.method == 'POST' else {}
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip().lower()
        mobile = re.sub(r'[^0-9+]', '', request.form.get('mobile', ''))
        password = request.form.get('password', '')
        farm_name = request.form.get('farm_name', '').strip()
        location = request.form.get('farm_location', '').strip()
        language = request.form.get('language', session.get('language', 'en'))
        errors = []
        if not 2 <= len(name) <= 80:
            errors.append('Enter your full name (2–80 characters).')
        digits = re.sub(r'\D', '', mobile)
        if not 10 <= len(digits) <= 15:
            errors.append('Enter a valid mobile number (10–15 digits).')
        if email and not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
            errors.append('Enter a valid email address or leave it blank.')
        if len(password) < 8:
            errors.append('Password must contain at least 8 characters.')
        if not 2 <= len(farm_name) <= 100:
            errors.append('Enter a farm name (2–100 characters).')
        if not location or len(location) > 160:
            errors.append('Enter a farm location (up to 160 characters).')
        if language not in LANGUAGES:
            language = 'en'
        if errors:
            for error in errors:
                flash(error, 'danger')
            return render_template('register.html', form=form, languages=LANGUAGES)

        db = get_db()
        # Email is optional in the supplied UI. A private local identifier is used
        # only when it is omitted; login accepts the registered mobile number too.
        if not email:
            email = f"mobile-{digits}@local.mushroomguard"
        if db.execute('SELECT 1 FROM users WHERE mobile=? LIMIT 1', (mobile,)).fetchone():
            flash('That mobile number is already registered. Please log in.', 'danger')
            return render_template('register.html', form=form, languages=LANGUAGES)
        try:
            cursor = db.execute(
                'INSERT INTO users(name,email,password_hash,mobile) VALUES(?,?,?,?)',
                (name, email, generate_password_hash(password), mobile)
            )
            user_id = cursor.lastrowid
            db.execute('INSERT INTO farms(user_id,farm_name,location) VALUES(?,?,?)', (user_id, farm_name, location))
            db.execute('INSERT INTO farmer_preferences(user_id,language) VALUES(?,?)', (user_id, language))
            db.execute('INSERT INTO user_device_settings(user_id) VALUES(?)', (user_id,))
            db.execute('INSERT INTO regions(user_id,region_name) VALUES(?,?)', (user_id, 'Room A'))
            db.commit()
        except sqlite3.IntegrityError:
            db.rollback()
            flash('That email or mobile-based account identifier is already registered. Please log in.', 'danger')
            return render_template('register.html', form=form, languages=LANGUAGES)

        session.clear()
        session.permanent = True
        session.update(user_id=user_id, user_name=name, language=language)
        return redirect(url_for('auth.onboarding_farm'))
    return render_template('register.html', form=form, languages=LANGUAGES)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user_id'):
        return redirect(url_for('dashboard.index'))
    if request.method == 'POST':
        identifier = request.form.get('identifier', request.form.get('email', '')).strip().lower()
        password = request.form.get('password', '')
        db = get_db()
        # Accept email or phone. Normalize common phone punctuation on login so
        # the same number works whether the farmer types spaces or hyphens.
        phone_identifier = re.sub(r'[^0-9+]', '', identifier)
        user = db.execute('SELECT * FROM users WHERE lower(email)=? OR mobile=?', (identifier, phone_identifier)).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            prefs = db.execute('SELECT language FROM farmer_preferences WHERE user_id=?', (user['id'],)).fetchone()
            session.clear()
            session.permanent = True
            session.update(user_id=user['id'], user_name=user['name'], language=prefs['language'] if prefs else 'en')
            return redirect(url_for('dashboard.index'))
        flash('Email/mobile number or password is incorrect.', 'danger')
    return render_template('login.html')


@auth_bp.route('/onboarding/farm', methods=['GET', 'POST'])
def onboarding_farm():
    redirect_response = login_required_redirect()
    if redirect_response:
        return redirect_response
    db = get_db()
    uid = session['user_id']
    farm = db.execute('SELECT * FROM farms WHERE user_id=?', (uid,)).fetchone()
    regions = db.execute('SELECT * FROM regions WHERE user_id=? ORDER BY id', (uid,)).fetchall()
    if request.method == 'POST':
        farm_name = request.form.get('farm_name', '').strip()
        location = request.form.get('location', '').strip()
        names = list(dict.fromkeys(n.strip() for n in request.form.getlist('region_names') if n.strip()))[:8]
        if not farm_name or len(farm_name) > 100 or len(location) > 160 or not names or any(len(n) > 40 for n in names):
            flash('Enter a farm name, location and at least one room name (maximum 8 rooms).', 'danger')
            return render_template('onboarding_farm.html', farm=farm, regions=regions)
        db.execute('UPDATE farms SET farm_name=?,location=? WHERE user_id=?', (farm_name, location, uid))
        existing = {r['region_name']: r['id'] for r in regions}
        keep = set(names)
        for name in names:
            if name not in existing:
                db.execute('INSERT OR IGNORE INTO regions(user_id,region_name) VALUES(?,?)', (uid, name))
        # Never delete a room that already has associated records.
        for room in regions:
            if room['region_name'] not in keep:
                used = db.execute('SELECT 1 FROM cultivation_units WHERE region_id=? LIMIT 1', (room['id'],)).fetchone()
                logged = db.execute('SELECT 1 FROM environment_logs WHERE region_id=? LIMIT 1', (room['id'],)).fetchone()
                if not used and not logged:
                    db.execute('DELETE FROM regions WHERE id=? AND user_id=?', (room['id'], uid))
        db.commit()
        flash('Farm details saved. Choose your cultivation preferences next.', 'success')
        return redirect(url_for('auth.preferences'))
    return render_template('onboarding_farm.html', farm=farm, regions=regions)


@auth_bp.route('/preferences', methods=['GET', 'POST'])
def preferences():
    redirect_response = login_required_redirect()
    if redirect_response:
        return redirect_response
    db = get_db()
    uid = session['user_id']
    if request.method == 'POST':
        grows_mushrooms = request.form.get('grows_mushrooms') == '1'
        grows_microgreens = request.form.get('grows_microgreens') == '1'
        mushrooms = [x for x in request.form.getlist('mushroom_crops') if x in MUSHROOMS]
        microgreens = [x for x in request.form.getlist('microgreen_crops') if x in MICROGREENS]
        if not grows_mushrooms and not grows_microgreens:
            flash('Select mushrooms, microgreens or both.', 'warning')
        elif (grows_mushrooms and not mushrooms) or (grows_microgreens and not microgreens):
            flash('Select at least one variety for each cultivation type you enable.', 'warning')
        else:
            db.execute('UPDATE farmer_preferences SET grows_mushrooms=?,grows_microgreens=? WHERE user_id=?',
                       (int(grows_mushrooms), int(grows_microgreens), uid))
            db.execute('DELETE FROM farmer_crops WHERE user_id=?', (uid,))
            for crop in mushrooms if grows_mushrooms else []:
                db.execute('INSERT INTO farmer_crops(user_id,crop_type,crop_name) VALUES(?,?,?)', (uid, 'mushroom', crop))
            for crop in microgreens if grows_microgreens else []:
                db.execute('INSERT INTO farmer_crops(user_id,crop_type,crop_name) VALUES(?,?,?)', (uid, 'microgreen', crop))
            db.commit()
            flash('Cultivation preferences saved.', 'success')
            return redirect(url_for('auth.onboarding_devices'))
    selected = db.execute('SELECT crop_type,crop_name FROM farmer_crops WHERE user_id=?', (uid,)).fetchall()
    prefs = db.execute('SELECT * FROM farmer_preferences WHERE user_id=?', (uid,)).fetchone()
    return render_template('preferences.html', mushrooms=MUSHROOMS, microgreens=MICROGREENS,
        selected_mushrooms={r['crop_name'] for r in selected if r['crop_type'] == 'mushroom'},
        selected_microgreens={r['crop_name'] for r in selected if r['crop_type'] == 'microgreen'}, preferences=prefs)


@auth_bp.route('/onboarding/devices', methods=['GET', 'POST'])
def onboarding_devices():
    redirect_response = login_required_redirect()
    if redirect_response:
        return redirect_response
    uid = session['user_id']
    db = get_db()
    settings = db.execute('SELECT * FROM user_device_settings WHERE user_id=?', (uid,)).fetchone()
    if request.method == 'POST':
        port = request.form.get('serial_port', '').strip().upper()
        try:
            camera_index = int(request.form.get('camera_index', '0'))
            baud = int(request.form.get('serial_baud', '9600'))
            if camera_index < 0 or not (300 <= baud <= 2_000_000):
                raise ValueError
        except ValueError:
            flash('Enter a valid serial baud rate and non-negative camera index.', 'danger')
            return render_template('onboarding_devices.html', settings=settings)
        db.execute('''INSERT INTO user_device_settings(user_id,serial_port,serial_baud,camera_index) VALUES(?,?,?,?)
            ON CONFLICT(user_id) DO UPDATE SET serial_port=excluded.serial_port,serial_baud=excluded.serial_baud,camera_index=excluded.camera_index''',
            (uid, port, baud, camera_index))
        db.commit()
        manager = current_app.extensions['mushroomguard_hardware']
        if manager.ser and manager.ser.is_open:
            manager.disconnect()
        manager.port, manager.baud, manager.camera_index = port, baud, camera_index
        flash('Device settings saved. You can test the Arduino and camera from Tools & Diagnostics.', 'success')
        return redirect(url_for('dashboard.index'))
    return render_template('onboarding_devices.html', settings=settings)


@auth_bp.get('/logout')
def logout():
    manager = current_app.extensions.get('mushroomguard_hardware')
    if manager:
        manager.disconnect()
    session.clear()
    return redirect(url_for('auth.login'))
