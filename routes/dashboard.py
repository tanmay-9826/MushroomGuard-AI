from datetime import datetime
from flask import Blueprint, current_app, redirect, render_template, request, session, url_for
from models.database import get_db

dashboard_bp = Blueprint('dashboard', __name__)


def _fresh(stamp, seconds=20):
    if not stamp:
        return False
    try:
        return (datetime.now() - datetime.strptime(stamp, '%Y-%m-%d %H:%M:%S')).total_seconds() <= seconds
    except ValueError:
        return False


@dashboard_bp.get('/dashboard')
def index():
    uid = session.get('user_id')
    if not uid:
        return redirect(url_for('auth.login'))
    db = get_db()
    farm = db.execute('SELECT * FROM farms WHERE user_id=?', (uid,)).fetchone()
    regions = db.execute('SELECT * FROM regions WHERE user_id=? ORDER BY id', (uid,)).fetchall()
    region_id = request.args.get('region', type=int)
    region = next((r for r in regions if r['id'] == region_id), None) if region_id else (regions[0] if regions else None)
    counts = {r['health_status']: r['n'] for r in db.execute(
        'SELECT health_status,COUNT(*) n FROM cultivation_units WHERE user_id=? AND status<>\'archived\' GROUP BY health_status', (uid,)).fetchall()}
    total = sum(counts.values())
    healthy = counts.get('healthy', 0)
    review = counts.get('review', 0)
    high = counts.get('high_alert', 0)
    under_observation = counts.get('under_observation', 0) + counts.get('unassessed', 0)
    need_attention = review + under_observation

    latest = None
    if region:
        latest = db.execute('SELECT * FROM environment_logs WHERE user_id=? AND region_id=? ORDER BY id DESC LIMIT 1', (uid, region['id'])).fetchone()
    manager = current_app.extensions['mushroomguard_hardware']
    with manager.state_lock:
        hardware = dict(manager.latest)
    sensor_online = bool(hardware.get('connected') and _fresh(hardware.get('updated')) and region and hardware.get('region_id') == region['id'])

    alerts = db.execute('''SELECT a.*,r.region_name FROM environment_alerts a
        LEFT JOIN regions r ON r.id=a.region_id WHERE a.user_id=? AND a.active=1
        ORDER BY CASE a.severity WHEN 'critical' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END,a.id DESC LIMIT 5''', (uid,)).fetchall()
    alert_bags = db.execute('''SELECT u.*,r.region_name FROM cultivation_units u LEFT JOIN regions r ON r.id=u.region_id
        WHERE u.user_id=? AND u.health_status IN ('high_alert','review') AND u.status<>'archived'
        ORDER BY CASE u.health_status WHEN 'high_alert' THEN 0 ELSE 1 END,u.id DESC LIMIT 4''', (uid,)).fetchall()
    observations = db.execute('''SELECT h.*,u.unit_name,u.crop_name FROM health_records h LEFT JOIN cultivation_units u ON u.id=h.unit_id
        WHERE h.user_id=? ORDER BY h.id DESC LIMIT 4''', (uid,)).fetchall()
    crops = db.execute('SELECT crop_type,crop_name FROM farmer_crops WHERE user_id=? ORDER BY crop_type,crop_name', (uid,)).fetchall()
    mushroom_crops = [r for r in crops if r['crop_type'] == 'mushroom']
    microgreen_crops = [r for r in crops if r['crop_type'] == 'microgreen']
    low_stock = db.execute('SELECT COUNT(*) FROM inventory_items WHERE user_id=? AND quantity<=minimum_quantity', (uid,)).fetchone()[0]
    units = db.execute('''SELECT u.*,r.region_name FROM cultivation_units u LEFT JOIN regions r ON r.id=u.region_id
        WHERE u.user_id=? AND u.status<>'archived' ORDER BY u.id DESC LIMIT 6''', (uid,)).fetchall()
    prefs = db.execute('SELECT * FROM farmer_preferences WHERE user_id=?', (uid,)).fetchone()
    return render_template('dashboard.html', farm=farm, regions=regions, region=region, counts=counts,
        total=total, healthy=healthy, review=review, high=high, observation=under_observation,
        need_attention=need_attention, latest=latest, sensor_online=sensor_online, hardware=hardware,
        alerts=alerts, alert_bags=alert_bags, observations=observations, crops=crops,
        mushroom_crops=mushroom_crops, microgreen_crops=microgreen_crops,
        low_stock=low_stock, units=units, preferences=prefs,
        current_date=datetime.now().strftime('%d %b %Y'), now_hour=datetime.now().hour)
