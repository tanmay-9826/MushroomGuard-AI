import sqlite3
from datetime import date

from app import create_app


def test_legacy_stage_history_and_single_farmer_data_are_preserved(tmp_path):
    database_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(database_path)
    connection.executescript("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        INSERT INTO users(name,email,password_hash)
        VALUES('Legacy Farmer','legacy@example.test','test-hash');

        CREATE TABLE cultivation_units (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            crop_type TEXT NOT NULL,
            crop_name TEXT NOT NULL,
            unit_name TEXT NOT NULL UNIQUE,
            start_date TEXT NOT NULL,
            growth_stage INTEGER NOT NULL DEFAULT 1
        );
        INSERT INTO cultivation_units(user_id,crop_type,crop_name,unit_name,start_date,growth_stage)
        VALUES(1,'mushroom','Oyster Mushroom','MUSH-00001','2026-10-01',2);

        CREATE TABLE cultivation_stage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            growth_stage INTEGER NOT NULL,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO cultivation_stage_history(unit_id,user_id,growth_stage) VALUES(1,1,2);

        CREATE TABLE inventory_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_name TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0
        );
        INSERT INTO inventory_items(item_name,quantity) VALUES('Wheat straw',12);

        CREATE TABLE health_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            observation TEXT NOT NULL
        );
        INSERT INTO health_records(observation) VALUES('Legacy crop note');

        CREATE TABLE environment_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            temperature REAL,
            humidity REAL
        );
        INSERT INTO environment_logs(temperature,humidity) VALUES(24.5,80);
    """)
    connection.commit()
    connection.close()

    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "migration-test-secret",
        "DATABASE": str(database_path),
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "SERIAL_PORT": "",
        "CAMERA_INDEX": 99,
    })
    try:
        with app.app_context():
            from models.database import get_db
            db = get_db()
            unit = db.execute("SELECT * FROM cultivation_units WHERE id=1").fetchone()
            history = db.execute(
                "SELECT * FROM cultivation_stage_history WHERE unit_id=1 ORDER BY id"
            ).fetchall()
            inventory = db.execute("SELECT * FROM inventory_items WHERE item_name='Wheat straw'").fetchone()
            health = db.execute("SELECT * FROM health_records WHERE observation='Legacy crop note'").fetchone()
            environment = db.execute("SELECT * FROM environment_logs ORDER BY id DESC LIMIT 1").fetchone()
            preferences = db.execute("SELECT * FROM farmer_preferences WHERE user_id=1").fetchone()

            assert unit["unit_name"] == "MUSH-00001"
            assert unit["growth_stage"] == 2
            assert history[0]["user_id"] == 1
            assert history[0]["growth_stage"] == 2
            assert history[0]["new_stage"] == 2
            assert inventory["user_id"] == 1
            assert health["user_id"] == 1
            assert environment["user_id"] == 1
            assert preferences["language"] == "en"
            db.execute("UPDATE farmer_preferences SET grows_mushrooms=1 WHERE user_id=1")
            db.execute("INSERT OR IGNORE INTO farmer_crops(user_id,crop_type,crop_name) VALUES(1,'mushroom','Oyster Mushroom')")
            db.commit()

            # The prior schema has unit_name TEXT NOT NULL and stage-history
            # user_id/growth_stage NOT NULL. Exercise the actual route against it.
            with app.test_client() as client:
                with client.session_transaction() as session:
                    session['user_id'] = 1
                    session['user_name'] = 'Legacy Farmer'
                    session['language'] = 'en'
                response = client.post('/buckets/add/mushroom', data={
                    'crop_name': 'Oyster Mushroom',
                    'start_date': date.today().isoformat(),
                    'growth_stage': '1',
                    'region_id': '1',
                    'batch_code': 'LEGACY-COMPAT',
                    'rack': 'R1-A',
                }, follow_redirects=True)
                assert response.status_code == 200
                assert b'MUSH-00002' in response.data

            db.execute(
                "INSERT INTO cultivation_units(user_id,crop_type,crop_name,unit_name,start_date,growth_stage) VALUES(1,'mushroom','Oyster Mushroom','PENDING-test','2026-11-03',1)"
            )
            new_unit_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
            db.execute("UPDATE cultivation_units SET unit_name=? WHERE id=?", (f"MUSH-{new_unit_id:05d}", new_unit_id))
            db.execute(
                "INSERT INTO cultivation_stage_history(unit_id,user_id,growth_stage,previous_stage,new_stage) VALUES(?,?,?,?,?)",
                (new_unit_id, 1, 1, None, 1),
            )
            db.commit()
            new_history = db.execute(
                "SELECT * FROM cultivation_stage_history WHERE unit_id=?", (new_unit_id,)
            ).fetchone()
            assert new_history["new_stage"] == 1
    finally:
        app.extensions["mushroomguard_hardware"].shutdown()
