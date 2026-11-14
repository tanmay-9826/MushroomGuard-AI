import re
from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from models.database import get_db

settings_bp = Blueprint('settings', __name__)
LANGUAGES = {'en': 'English', 'mr': 'मराठी', 'hi': 'हिन्दी'}


@settings_bp.route('/settings', methods=['GET', 'POST'])
def index():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('auth.login'))
    db = get_db()
    if request.method == 'POST':
        section = request.form.get('section', 'profile')
        if section == 'profile':
            name = request.form.get('name', '').strip()
            mobile = re.sub(r'[^0-9+]', '', request.form.get('mobile', ''))
            farm_name = request.form.get('farm_name', '').strip()
            location = request.form.get('location', '').strip()
            language = request.form.get('language', 'en')
            if not 2 <= len(name) <= 80 or not farm_name or len(farm_name) > 100 or len(location) > 160 or language not in LANGUAGES:
                flash('Check your name, farm name, location and language.', 'danger')
            elif not 10 <= len(re.sub(r'\D', '', mobile)) <= 15:
                flash('Enter a valid mobile number (10–15 digits).', 'danger')
            elif db.execute('SELECT 1 FROM users WHERE mobile=? AND id<>? LIMIT 1', (mobile, uid)).fetchone():
                flash('That mobile number is already used by another account.', 'danger')
            else:
                db.execute('UPDATE users SET name=?,mobile=? WHERE id=?', (name, mobile, uid))
                db.execute('UPDATE farms SET farm_name=?,location=? WHERE user_id=?', (farm_name, location, uid))
                db.execute('UPDATE farmer_preferences SET language=? WHERE user_id=?', (language, uid))
                db.commit()
                session['user_name'], session['language'] = name, language
                flash('Farmer and farm profile saved.', 'success')
        elif section == 'devices':
            port = request.form.get('serial_port', '').strip().upper()
            try:
                baud = int(request.form.get('serial_baud', '9600'))
                camera_index = int(request.form.get('camera_index', '0'))
                if not 300 <= baud <= 2_000_000 or camera_index < 0:
                    raise ValueError
                db.execute('''INSERT INTO user_device_settings(user_id,serial_port,serial_baud,camera_index) VALUES(?,?,?,?)
                    ON CONFLICT(user_id) DO UPDATE SET serial_port=excluded.serial_port,serial_baud=excluded.serial_baud,camera_index=excluded.camera_index''',
                    (uid, port, baud, camera_index))
                db.commit()
                manager = current_app.extensions['mushroomguard_hardware']
                if manager.ser and manager.ser.is_open:
                    manager.disconnect()
                manager.port, manager.baud, manager.camera_index = port, baud, camera_index
                flash('Device connection settings saved. Test them in Tools & Diagnostics.', 'success')
            except (TypeError, ValueError):
                flash('Enter a valid baud rate and camera index.', 'danger')
        elif section == 'password':
            current = request.form.get('current_password', '')
            new = request.form.get('new_password', '')
            user = db.execute('SELECT password_hash FROM users WHERE id=?', (uid,)).fetchone()
            if not user or not check_password_hash(user['password_hash'], current):
                flash('Current password is incorrect.', 'danger')
            elif len(new) < 8:
                flash('New password must contain at least 8 characters.', 'danger')
            else:
                db.execute('UPDATE users SET password_hash=? WHERE id=?', (generate_password_hash(new), uid))
                db.commit()
                flash('Password updated.', 'success')
        return redirect(url_for('settings.index'))

    profile = db.execute('''SELECT u.name,u.email,u.mobile,f.farm_name,f.location,p.language,p.grows_mushrooms,p.grows_microgreens
        FROM users u LEFT JOIN farms f ON f.user_id=u.id LEFT JOIN farmer_preferences p ON p.user_id=u.id WHERE u.id=?''', (uid,)).fetchone()
    devices = db.execute('SELECT * FROM user_device_settings WHERE user_id=?', (uid,)).fetchone()
    regions = db.execute('SELECT * FROM regions WHERE user_id=? ORDER BY id', (uid,)).fetchall()
    crops = db.execute('SELECT * FROM farmer_crops WHERE user_id=? ORDER BY crop_type,crop_name', (uid,)).fetchall()
    return render_template('settings.html', profile=profile, devices=devices, regions=regions,
                           crops=crops, languages=LANGUAGES)
