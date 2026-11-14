import csv
from io import StringIO, BytesIO
from flask import Blueprint, abort, flash, redirect, render_template, request, send_file, session, url_for
from models.database import get_db

inventory_bp = Blueprint('inventory', __name__)


def _uid():
    return session.get('user_id')


@inventory_bp.get('/inventory')
def index():
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    db = get_db()
    search = request.args.get('q', '').strip()[:60]
    region_filter = request.args.get('region', '').strip()
    batch_filter = request.args.get('batch', '').strip()
    status_filter = request.args.get('status', '').strip()
    clauses, params = ['u.user_id=?'], [uid]
    if search:
        clauses.append('(u.unit_name LIKE ? OR u.batch_code LIKE ? OR u.rack LIKE ? OR u.crop_name LIKE ?)')
        params.extend([f'%{search}%']*4)
    if region_filter:
        clauses.append('CAST(u.region_id AS TEXT)=?')
        params.append(region_filter)
    if batch_filter:
        clauses.append('u.batch_code=?')
        params.append(batch_filter)
    if status_filter in ('active','harvested','archived'):
        clauses.append('u.status=?')
        params.append(status_filter)
    units = db.execute('''SELECT u.*,r.region_name,
        COALESCE((SELECT SUM(CASE WHEN h.unit='kg' THEN h.weight WHEN h.unit='g' THEN h.weight/1000.0 ELSE 0 END) FROM harvest_records h WHERE h.unit_id=u.id AND h.user_id=u.user_id),0) total_yield_kg,
        COALESCE((SELECT SUM(CASE WHEN h.unit='tray' THEN h.weight ELSE 0 END) FROM harvest_records h WHERE h.unit_id=u.id AND h.user_id=u.user_id),0) total_yield_trays,
        (SELECT MAX(h.created_at) FROM health_records h WHERE h.unit_id=u.id AND h.user_id=u.user_id) last_observation
        FROM cultivation_units u LEFT JOIN regions r ON r.id=u.region_id WHERE ''' + ' AND '.join(clauses) + ' ORDER BY u.id DESC', params).fetchall()
    regions = db.execute('SELECT * FROM regions WHERE user_id=? ORDER BY id', (uid,)).fetchall()
    batches = [r[0] for r in db.execute("SELECT DISTINCT batch_code FROM cultivation_units WHERE user_id=? AND batch_code<>'' ORDER BY batch_code DESC", (uid,)).fetchall()]
    items = db.execute('SELECT * FROM inventory_items WHERE user_id=? ORDER BY item_name COLLATE NOCASE', (uid,)).fetchall()
    low_stock = [r for r in items if r['quantity'] <= r['minimum_quantity']]
    selected_id = request.args.get('unit_id', type=int)
    selected = next((u for u in units if u['id'] == selected_id), None) if selected_id else (units[0] if units else None)
    history = harvests = stage_history = []
    if selected:
        stage_history = db.execute('SELECT * FROM cultivation_stage_history WHERE user_id=? AND unit_id=? ORDER BY id DESC', (uid, selected['id'])).fetchall()
        harvests = db.execute('SELECT * FROM harvest_records WHERE user_id=? AND unit_id=? ORDER BY harvest_date DESC,id DESC', (uid, selected['id'])).fetchall()
        history = db.execute('SELECT * FROM health_records WHERE user_id=? AND unit_id=? ORDER BY id DESC LIMIT 5', (uid, selected['id'])).fetchall()
    return render_template('inventory.html', units=units, regions=regions, batches=batches, items=items, low_stock=low_stock,
        selected=selected, stage_history=stage_history, harvests=harvests, health_history=history,
        search=search, region_filter=region_filter, batch_filter=batch_filter, status_filter=status_filter)


@inventory_bp.post('/inventory/stock')
def add_stock():
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    name = request.form.get('item_name', '').strip()
    category = request.form.get('category', 'Substrate').strip()
    unit = request.form.get('unit', 'kg').strip()
    try:
        quantity = float(request.form.get('quantity', ''))
        minimum = float(request.form.get('minimum_quantity', '0'))
        if not name or len(name) > 100 or len(unit) > 20 or not 0 <= quantity <= 1e9 or not 0 <= minimum <= 1e9:
            raise ValueError
    except (TypeError, ValueError):
        flash('Enter a valid item name and non-negative quantities.', 'danger')
        return redirect(url_for('inventory.index'))
    if category not in ('Substrate','Spawn / Seed','Packaging','Sanitation','Tools','Other'):
        category = 'Other'
    db = get_db()
    db.execute('INSERT INTO inventory_items(user_id,item_name,category,quantity,unit,minimum_quantity) VALUES(?,?,?,?,?,?)',
               (uid, name, category, quantity, unit, minimum))
    db.commit()
    flash('Supply item added to inventory.', 'success')
    return redirect(url_for('inventory.index') + '#supplies')


@inventory_bp.post('/inventory/stock/<int:item_id>/update')
def update_stock(item_id):
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    try:
        quantity = float(request.form.get('quantity', ''))
        minimum = float(request.form.get('minimum_quantity', '0'))
        if not 0 <= quantity <= 1e9 or not 0 <= minimum <= 1e9:
            raise ValueError
    except (TypeError, ValueError):
        flash('Enter valid non-negative quantities.', 'danger')
        return redirect(url_for('inventory.index') + '#supplies')
    db = get_db()
    cur = db.execute('UPDATE inventory_items SET quantity=?,minimum_quantity=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=?',
                     (quantity, minimum, item_id, uid))
    if not cur.rowcount:
        abort(404)
    db.commit()
    flash('Inventory stock updated.', 'success')
    return redirect(url_for('inventory.index') + '#supplies')


@inventory_bp.post('/inventory/stock/<int:item_id>/delete')
def delete_stock(item_id):
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    cur = get_db().execute('DELETE FROM inventory_items WHERE id=? AND user_id=?', (item_id, uid))
    if not cur.rowcount:
        abort(404)
    get_db().commit()
    flash('Inventory item deleted.', 'info')
    return redirect(url_for('inventory.index') + '#supplies')


@inventory_bp.get('/inventory/export.csv')
def export():
    uid = _uid()
    if not uid:
        return redirect(url_for('auth.login'))
    rows = get_db().execute('''SELECT u.unit_name,u.crop_type,u.crop_name,u.batch_code,u.rack,r.region_name,u.start_date,u.growth_stage,u.health_status,u.status
        FROM cultivation_units u LEFT JOIN regions r ON r.id=u.region_id WHERE u.user_id=? ORDER BY u.id DESC''', (uid,)).fetchall()
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Bag / Tray ID','Crop type','Variety','Batch','Rack','Region','Start date','Growth stage','Health status','Status'])
    writer.writerows([tuple(r) for r in rows])
    return send_file(BytesIO(output.getvalue().encode('utf-8-sig')), mimetype='text/csv', as_attachment=True, download_name='mushroomguard-inventory.csv')
