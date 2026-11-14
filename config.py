import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(BASE_DIR / '.env')
except ImportError:
    pass

class Config:
    SECRET_KEY = os.environ.get('MUSHROOMGUARD_SECRET', 'change-this-local-secret-before-sharing')
    DATABASE = str(BASE_DIR / 'database' / 'mushroomguard.db')
    UPLOAD_FOLDER = str(BASE_DIR / 'uploads')
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False  # Localhost HTTP application
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12
    SERIAL_PORT = os.environ.get('MUSHROOMGUARD_COM', '').strip()
    SERIAL_BAUD = int(os.environ.get('MUSHROOMGUARD_BAUD', '9600'))
    CAMERA_INDEX = int(os.environ.get('MUSHROOMGUARD_CAMERA', '0'))
    CAMLORA_BASE_URL = os.environ.get('CAMLORA_BASE_URL', '').strip().rstrip('/')
    CAMLORA_MAX_RECORDING_SECONDS = max(60, min(1800, int(os.environ.get('CAMLORA_MAX_RECORDING_SECONDS', '600'))))
    CAMLORA_MAX_RECORDING_BYTES = max(50 * 1024 * 1024, min(1024 * 1024 * 1024, int(os.environ.get('CAMLORA_MAX_RECORDING_MB', '300')) * 1024 * 1024))
    CAMLORA_RECORDING_FPS = max(1.0, min(15.0, float(os.environ.get('CAMLORA_RECORDING_FPS', '8'))))
    VIDEO_FRAME_INTERVAL_SECONDS = max(1.0, min(30.0, float(os.environ.get('VIDEO_FRAME_INTERVAL_SECONDS', '5'))))
    VIDEO_MAX_EXTRACTED_FRAMES = max(10, min(300, int(os.environ.get('VIDEO_MAX_EXTRACTED_FRAMES', '120'))))
    YOLO_MODEL_DIR = str(BASE_DIR / 'ml' / 'models')
    THINGSPEAK_CHANNEL_ID = os.environ.get('THINGSPEAK_CHANNEL_ID', '').strip()
    THINGSPEAK_WRITE_API_KEY = os.environ.get('THINGSPEAK_WRITE_API_KEY', '').strip()
    THINGSPEAK_READ_API_KEY = os.environ.get('THINGSPEAK_READ_API_KEY', '').strip()
    THINGSPEAK_UPDATE_INTERVAL = max(15, int(os.environ.get('THINGSPEAK_UPDATE_INTERVAL', '20')))
    THINGSPEAK_TIMEOUT = max(2, int(os.environ.get('THINGSPEAK_TIMEOUT', '8')))
    ALLOWED_IMAGE_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp'}
    MAX_IMAGE_BYTES = 10 * 1024 * 1024
