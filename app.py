import atexit
import os
from pathlib import Path
from flask import Flask, redirect, session, url_for
from config import Config
from models.database import init_db
from services.hardware import HardwareManager
from services.thingspeak import ThingSpeakPublisher
from services.video_recorder import CamloraVideoRecorder

TRANSLATIONS = {
    'en': {'dashboard':'Dashboard','plant_health':'Plant Health','inventory':'Inventory','environment':'Environment','diagnostics':'Tools & Diagnostics','settings':'Settings','farm_dashboard':'Farm Dashboard','good_morning':'Good morning','total_bags':'Total Bags','healthy_bags':'Healthy','need_attention':'Need Attention','high_alerts':'High Alerts','under_observation':'Under Observation','add_bag':'Add Bag','add_mushroom':'Add Mushroom Bucket','add_microgreen':'Add Microgreen Tray','save':'Save changes','cancel':'Cancel','logout':'Log out','system_local':'Local System','no_sensor':'Waiting for sensor data','manual_note':'Farmer-entered observation','ai_unavailable':'AI model not configured'},
    'mr': {'dashboard':'डॅशबोर्ड','plant_health':'पीक आरोग्य','inventory':'साठा','environment':'पर्यावरण','diagnostics':'साधने व निदान','settings':'सेटिंग्ज','farm_dashboard':'शेत डॅशबोर्ड','good_morning':'शुभ सकाळ','total_bags':'एकूण बॅग','healthy_bags':'निरोगी','need_attention':'लक्ष आवश्यक','high_alerts':'उच्च सूचना','under_observation':'निरीक्षणाखाली','add_bag':'बॅग जोडा','add_mushroom':'मशरूम बॅग जोडा','add_microgreen':'मायक्रोग्रीन्स ट्रे जोडा','save':'बदल जतन करा','cancel':'रद्द करा','logout':'बाहेर पडा','system_local':'स्थानिक प्रणाली','no_sensor':'सेन्सर डेटाची प्रतीक्षा','manual_note':'शेतकऱ्याने नोंदवलेले निरीक्षण','ai_unavailable':'AI मॉडेल कॉन्फिगर केलेले नाही'},
    'hi': {'dashboard':'डैशबोर्ड','plant_health':'फसल स्वास्थ्य','inventory':'इन्वेंटरी','environment':'पर्यावरण','diagnostics':'टूल्स और डायग्नोस्टिक्स','settings':'सेटिंग्स','farm_dashboard':'फार्म डैशबोर्ड','good_morning':'सुप्रभात','total_bags':'कुल बैग','healthy_bags':'स्वस्थ','need_attention':'ध्यान आवश्यक','high_alerts':'उच्च अलर्ट','under_observation':'निगरानी में','add_bag':'बैग जोड़ें','add_mushroom':'मशरूम बैग जोड़ें','add_microgreen':'माइक्रोग्रीन्स ट्रे जोड़ें','save':'बदलाव सहेजें','cancel':'रद्द करें','logout':'लॉग आउट','system_local':'स्थानीय सिस्टम','no_sensor':'सेंसर डेटा की प्रतीक्षा','manual_note':'किसान द्वारा दर्ज निरीक्षण','ai_unavailable':'AI मॉडल कॉन्फ़िगर नहीं है'},
}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    Path(app.config['DATABASE']).parent.mkdir(parents=True, exist_ok=True)
    Path(app.config['UPLOAD_FOLDER']).mkdir(parents=True, exist_ok=True)
    init_db(app)
    manager = HardwareManager(app.config.get('SERIAL_PORT', ''), app.config.get('SERIAL_BAUD', 9600), app.config.get('CAMERA_INDEX', 0))
    app.extensions['mushroomguard_hardware'] = manager
    video_recorder = CamloraVideoRecorder(app)
    app.extensions['mushroomguard_video_recorder'] = video_recorder
    thingspeak = ThingSpeakPublisher(
        channel_id=app.config.get('THINGSPEAK_CHANNEL_ID', ''),
        write_key=app.config.get('THINGSPEAK_WRITE_API_KEY', ''),
        read_key=app.config.get('THINGSPEAK_READ_API_KEY', ''),
        update_interval=app.config.get('THINGSPEAK_UPDATE_INTERVAL', 20),
        timeout=app.config.get('THINGSPEAK_TIMEOUT', 8),
    )
    app.extensions['mushroomguard_thingspeak'] = thingspeak
    if thingspeak.enabled:
        thingspeak.start()
    atexit.register(video_recorder.shutdown)
    atexit.register(manager.shutdown)
    atexit.register(thingspeak.shutdown)

    @app.context_processor
    def inject_common():
        language = session.get('language', 'en')
        farm_name = 'My Mushroom Farm'
        if session.get('user_id'):
            try:
                from models.database import get_db
                farm = get_db().execute('SELECT farm_name FROM farms WHERE user_id=?', (session['user_id'],)).fetchone()
                if farm and farm['farm_name']:
                    farm_name = farm['farm_name']
            except Exception:
                pass
        return {'t': TRANSLATIONS.get(language, TRANSLATIONS['en']), 'current_language': language,
                'language_names': {'en':'English','mr':'मराठी','hi':'हिन्दी'}, 'farm_name': farm_name}

    from routes.auth import auth_bp
    from routes.dashboard import dashboard_bp
    from routes.buckets import buckets_bp
    from routes.plant_health import plant_health_bp
    from routes.inventory import inventory_bp
    from routes.environment import environment_bp
    from routes.diagnostics import diagnostics_bp
    from routes.settings import settings_bp
    for blueprint in (auth_bp, dashboard_bp, buckets_bp, plant_health_bp, inventory_bp, environment_bp, diagnostics_bp, settings_bp):
        app.register_blueprint(blueprint)

    @app.route('/')
    def home():
        if session.get('user_id'):
            return redirect(url_for('dashboard.index'))
        return redirect(url_for('auth.language'))

    @app.errorhandler(413)
    def too_large(_error):
        from flask import flash, redirect, url_for
        flash('The uploaded image is too large. Maximum upload size is 12 MB.', 'danger')
        return redirect(url_for('plant_health.index'))

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', '5000')), debug=False)
