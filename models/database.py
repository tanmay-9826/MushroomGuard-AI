from pathlib import Path
import sqlite3
from flask import current_app, g


def get_db():
    if 'db' not in g:
        connection = sqlite3.connect(current_app.config['DATABASE'], timeout=20)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys = ON')
        connection.execute('PRAGMA journal_mode = WAL')
        connection.execute('PRAGMA busy_timeout = 20000')
        g.db = connection
    return g.db


def close_db(_error=None):
    connection = g.pop('db', None)
    if connection is not None:
        connection.close()


def _table_exists(db, table):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def _columns(db, table):
    if not _table_exists(db, table):
        return set()
    return {row['name'] for row in db.execute(f'PRAGMA table_info({table})')}


def _add_columns(db, table, definitions):
    existing = _columns(db, table)
    for name, declaration in definitions:
        if name not in existing:
            db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {declaration}')


def _create_tables(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        mobile TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS farms (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL UNIQUE,
        farm_name TEXT NOT NULL DEFAULT 'My Mushroom Farm',
        location TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS farmer_preferences (
        user_id INTEGER PRIMARY KEY,
        language TEXT NOT NULL DEFAULT 'en',
        grows_mushrooms INTEGER NOT NULL DEFAULT 0,
        grows_microgreens INTEGER NOT NULL DEFAULT 0,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS farmer_crops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        crop_type TEXT NOT NULL,
        crop_name TEXT NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE(user_id, crop_type, crop_name)
    );
    CREATE TABLE IF NOT EXISTS regions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        region_name TEXT NOT NULL,
        species TEXT DEFAULT '',
        growth_stage TEXT DEFAULT '',
        temperature_min REAL DEFAULT 22,
        temperature_max REAL DEFAULT 26,
        humidity_min REAL DEFAULT 85,
        humidity_max REAL DEFAULT 90,
        co2_max REAL DEFAULT 1000,
        control_mode TEXT NOT NULL DEFAULT 'auto',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        UNIQUE(user_id, region_name)
    );
    CREATE TABLE IF NOT EXISTS cultivation_units (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        crop_type TEXT NOT NULL,
        crop_name TEXT NOT NULL,
        unit_name TEXT UNIQUE,
        batch_code TEXT DEFAULT '',
        rack TEXT DEFAULT '',
        region_id INTEGER,
        start_date TEXT NOT NULL,
        growth_stage INTEGER NOT NULL DEFAULT 1,
        health_status TEXT NOT NULL DEFAULT 'unassessed',
        status TEXT NOT NULL DEFAULT 'active',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(region_id) REFERENCES regions(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS cultivation_stage_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unit_id INTEGER NOT NULL,
        user_id INTEGER,
        growth_stage INTEGER,
        previous_stage INTEGER,
        new_stage INTEGER,
        notes TEXT DEFAULT '',
        changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(unit_id) REFERENCES cultivation_units(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS environment_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        region_id INTEGER,
        temperature REAL,
        humidity REAL,
        co2 REAL,
        source TEXT DEFAULT 'manual',
        recorded_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(region_id) REFERENCES regions(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS inventory_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        item_name TEXT NOT NULL,
        category TEXT DEFAULT 'Substrate',
        quantity REAL NOT NULL DEFAULT 0,
        unit TEXT NOT NULL DEFAULT 'units',
        minimum_quantity REAL DEFAULT 0,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS health_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        unit_id INTEGER,
        observation TEXT NOT NULL,
        severity TEXT DEFAULT 'info',
        image_name TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(unit_id) REFERENCES cultivation_units(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS harvest_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        unit_id INTEGER NOT NULL,
        harvest_date TEXT NOT NULL,
        weight REAL NOT NULL,
        unit TEXT NOT NULL DEFAULT 'kg',
        quality TEXT DEFAULT 'Good',
        notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(unit_id) REFERENCES cultivation_units(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS user_device_settings (
        user_id INTEGER PRIMARY KEY,
        serial_port TEXT DEFAULT '',
        serial_baud INTEGER NOT NULL DEFAULT 9600,
        camera_index INTEGER NOT NULL DEFAULT 0,
        camera_name TEXT DEFAULT 'USB Camera',
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        level TEXT NOT NULL DEFAULT 'info',
        message TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS environment_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        region_id INTEGER,
        alert_type TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'warning',
        message TEXT NOT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        resolved_at TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(region_id) REFERENCES regions(id) ON DELETE SET NULL
    );
    CREATE TABLE IF NOT EXISTS video_recordings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        unit_id INTEGER NOT NULL,
        filename TEXT NOT NULL UNIQUE,
        status TEXT NOT NULL DEFAULT 'starting',
        started_at TEXT DEFAULT CURRENT_TIMESTAMP,
        stopped_at TEXT,
        duration_seconds REAL NOT NULL DEFAULT 0,
        frame_count INTEGER NOT NULL DEFAULT 0,
        file_size_bytes INTEGER NOT NULL DEFAULT 0,
        width INTEGER,
        height INTEGER,
        fps REAL,
        notes TEXT DEFAULT '',
        error TEXT DEFAULT '',
        label_stage INTEGER,
        analysis_status TEXT NOT NULL DEFAULT 'not_run',
        predicted_stage INTEGER,
        prediction_confidence REAL,
        analysis_model TEXT DEFAULT '',
        analysis_summary TEXT DEFAULT '',
        analysis_details TEXT DEFAULT '',
        confirmed_stage INTEGER,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(unit_id) REFERENCES cultivation_units(id) ON DELETE CASCADE
    );
    CREATE TABLE IF NOT EXISTS video_frames (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        recording_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        unit_id INTEGER NOT NULL,
        filename TEXT NOT NULL UNIQUE,
        frame_index INTEGER NOT NULL,
        seconds_offset REAL NOT NULL DEFAULT 0,
        stage_label INTEGER,
        label_source TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(recording_id) REFERENCES video_recordings(id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(unit_id) REFERENCES cultivation_units(id) ON DELETE CASCADE,
        UNIQUE(recording_id, frame_index)
    );
    ''')


def init_db(app):
    app.teardown_appcontext(close_db)
    Path(app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)
    with app.app_context():
        db = get_db()
        _create_tables(db)
        # Additive migration path for the earlier MushroomGuard builds.
        migrations = {
            'users': [('mobile', "TEXT DEFAULT ''"), ('created_at', 'TEXT')],
            'farms': [('farm_name', "TEXT NOT NULL DEFAULT 'My Mushroom Farm'"), ('location', "TEXT DEFAULT ''"), ('created_at', 'TEXT')],
            'regions': [
                ('region_name', "TEXT NOT NULL DEFAULT 'Room A'"), ('species', "TEXT DEFAULT ''"),
                ('growth_stage', "TEXT DEFAULT ''"), ('temperature_min', 'REAL DEFAULT 22'),
                ('temperature_max', 'REAL DEFAULT 26'), ('humidity_min', 'REAL DEFAULT 85'),
                ('humidity_max', 'REAL DEFAULT 90'), ('co2_max', 'REAL DEFAULT 1000'),
                ('control_mode', "TEXT NOT NULL DEFAULT 'auto'"), ('created_at', 'TEXT')
            ],
            'user_device_settings': [
                ('serial_port', "TEXT DEFAULT ''"), ('serial_baud', 'INTEGER NOT NULL DEFAULT 9600'),
                ('camera_index', 'INTEGER NOT NULL DEFAULT 0'), ('camera_name', "TEXT DEFAULT 'USB Camera'")
            ],
            'system_logs': [('user_id', 'INTEGER'), ('level', "TEXT NOT NULL DEFAULT 'info'"), ('message', "TEXT DEFAULT ''"), ('created_at', 'TEXT')],
            'harvest_records': [
                ('user_id', 'INTEGER'), ('unit_id', 'INTEGER'), ('harvest_date', 'TEXT'),
                ('weight', 'REAL DEFAULT 0'), ('unit', "TEXT DEFAULT 'kg'"), ('quality', "TEXT DEFAULT 'Good'"),
                ('notes', "TEXT DEFAULT ''"), ('created_at', 'TEXT')
            ],
            'farmer_preferences': [('language', "TEXT DEFAULT 'en'"), ('grows_mushrooms', 'INTEGER NOT NULL DEFAULT 0'), ('grows_microgreens', 'INTEGER NOT NULL DEFAULT 0')],
            'cultivation_units': [
                ('unit_name', 'TEXT'), ('batch_code', "TEXT DEFAULT ''"), ('rack', "TEXT DEFAULT ''"),
                ('region_id', 'INTEGER'), ('health_status', "TEXT NOT NULL DEFAULT 'unassessed'"),
                ('status', "TEXT NOT NULL DEFAULT 'active'"), ('notes', "TEXT DEFAULT ''"), ('created_at', 'TEXT')
            ],
            'cultivation_stage_history': [
                ('user_id', 'INTEGER'), ('growth_stage', 'INTEGER'), ('previous_stage', 'INTEGER'),
                ('new_stage', 'INTEGER'), ('notes', "TEXT DEFAULT ''"), ('changed_at', 'TEXT')
            ],
            'environment_logs': [('user_id', 'INTEGER'), ('region_id', 'INTEGER'), ('co2', 'REAL'), ('source', "TEXT DEFAULT 'manual'"), ('recorded_at', 'TEXT')],
            'inventory_items': [('user_id', 'INTEGER'), ('category', "TEXT DEFAULT 'Substrate'"), ('unit', "TEXT DEFAULT 'units'"), ('minimum_quantity', 'REAL DEFAULT 0'), ('updated_at', 'TEXT')],
            'health_records': [('user_id', 'INTEGER'), ('unit_id', 'INTEGER'), ('severity', "TEXT DEFAULT 'info'"), ('image_name', 'TEXT'), ('created_at', 'TEXT')],
        }
        for table, definitions in migrations.items():
            _add_columns(db, table, definitions)

        # Repair legacy nullable fields without deleting old records. Only assign
        # unowned records when there is exactly one account to avoid data leakage.
        db.execute("INSERT OR IGNORE INTO farmer_preferences(user_id) SELECT id FROM users")
        user_ids = [r[0] for r in db.execute('SELECT id FROM users ORDER BY id').fetchall()]
        db.execute('''UPDATE health_records SET user_id=(SELECT user_id FROM cultivation_units u WHERE u.id=health_records.unit_id)
                      WHERE user_id IS NULL AND unit_id IS NOT NULL''')
        db.execute('''UPDATE cultivation_stage_history SET user_id=(SELECT user_id FROM cultivation_units u WHERE u.id=cultivation_stage_history.unit_id)
                      WHERE user_id IS NULL''')
        if len(user_ids) == 1:
            only_id = user_ids[0]
            for table in ('inventory_items', 'health_records', 'environment_logs', 'system_logs'):
                if 'user_id' in _columns(db, table):
                    db.execute(f'UPDATE {table} SET user_id=? WHERE user_id IS NULL', (only_id,))

        db.execute("UPDATE farmer_preferences SET language='en' WHERE language IS NULL OR language NOT IN ('en','mr','hi')")
        db.execute("UPDATE inventory_items SET category='Substrate' WHERE category IS NULL OR TRIM(category)=''")
        db.execute("UPDATE inventory_items SET unit='units' WHERE unit IS NULL OR TRIM(unit)=''")
        db.execute("UPDATE inventory_items SET minimum_quantity=0 WHERE minimum_quantity IS NULL")
        db.execute("UPDATE environment_logs SET source='manual' WHERE source IS NULL OR TRIM(source)=''")
        db.execute('UPDATE cultivation_stage_history SET changed_at=CURRENT_TIMESTAMP WHERE changed_at IS NULL')
        db.execute('UPDATE cultivation_stage_history SET new_stage=growth_stage WHERE new_stage IS NULL AND growth_stage IS NOT NULL')
        db.execute('UPDATE environment_logs SET recorded_at=CURRENT_TIMESTAMP WHERE recorded_at IS NULL')
        db.execute('UPDATE inventory_items SET updated_at=CURRENT_TIMESTAMP WHERE updated_at IS NULL')
        db.execute('UPDATE health_records SET created_at=CURRENT_TIMESTAMP WHERE created_at IS NULL')
        # A process restart cannot resume an in-progress camera stream. Mark its
        # incomplete session explicitly instead of leaving a false 'recording' state.
        db.execute("UPDATE video_recordings SET status='interrupted',error='Application restarted before the recording was stopped.',stopped_at=CURRENT_TIMESTAMP WHERE status IN ('starting','recording')")

        # Ensure farm, room and device-settings records for existing accounts.
        for uid in user_ids:
            db.execute("INSERT OR IGNORE INTO farms(user_id,farm_name,location) VALUES(?,?,?)", (uid, 'My Mushroom Farm', ''))
            db.execute("INSERT OR IGNORE INTO user_device_settings(user_id) VALUES(?)", (uid,))
            if not db.execute('SELECT 1 FROM regions WHERE user_id=? LIMIT 1', (uid,)).fetchone():
                db.execute("INSERT INTO regions(user_id,region_name) VALUES(?, 'Room A')", (uid,))

        # Restore deterministic unit IDs and initial history for older records.
        units = db.execute('SELECT id,user_id,crop_type,unit_name,growth_stage FROM cultivation_units').fetchall()
        for unit in units:
            if not unit['unit_name']:
                prefix = 'MUSH' if unit['crop_type'] == 'mushroom' else 'MICRO'
                db.execute('UPDATE cultivation_units SET unit_name=? WHERE id=?', (f'{prefix}-{unit["id"]:05d}', unit['id']))
            if not db.execute('SELECT 1 FROM cultivation_stage_history WHERE unit_id=? LIMIT 1', (unit['id'],)).fetchone():
                db.execute('''INSERT INTO cultivation_stage_history(unit_id,user_id,growth_stage,previous_stage,new_stage)
                              VALUES(?,?,?,NULL,?)''', (unit['id'], unit['user_id'], unit['growth_stage'], unit['growth_stage']))

        for statement in (
            'CREATE INDEX IF NOT EXISTS idx_video_owner ON video_recordings(user_id, id DESC)',
            'CREATE INDEX IF NOT EXISTS idx_video_frames_recording ON video_frames(recording_id, frame_index)',
            'CREATE INDEX IF NOT EXISTS idx_video_frames_label ON video_frames(user_id, stage_label, id DESC)',
            'CREATE INDEX IF NOT EXISTS idx_units_owner ON cultivation_units(user_id, id DESC)',
            'CREATE INDEX IF NOT EXISTS idx_health_owner ON health_records(user_id, id DESC)',
            'CREATE INDEX IF NOT EXISTS idx_env_owner ON environment_logs(user_id, region_id, id DESC)',
            'CREATE INDEX IF NOT EXISTS idx_inventory_owner ON inventory_items(user_id, item_name)',
            'CREATE INDEX IF NOT EXISTS idx_history_unit ON cultivation_stage_history(unit_id, id DESC)',
            'CREATE INDEX IF NOT EXISTS idx_alerts_owner_active ON environment_alerts(user_id, active, id DESC)',
        ):
            db.execute(statement)
        db.commit()
