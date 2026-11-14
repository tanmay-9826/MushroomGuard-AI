"""USB serial and camera access for the configured local MushroomGuard devices."""
import re
import threading
import time
from pathlib import Path

try:
    import serial
except ImportError:  # App still starts for offline/manual record keeping.
    serial = None
try:
    import cv2
except ImportError:
    cv2 = None


class HardwareManager:
    """Owns one Arduino serial connection and one USB camera index."""

    ALLOWED_COMMANDS = {
        'FAN_ON', 'FAN_OFF', 'LED_ON', 'LED_OFF',
        'FAN_MODE_AUTO', 'FAN_MODE_MANUAL', 'STATUS',
    }

    def __init__(self, port='', baud=9600, camera_index=0):
        self.port = str(port or '').strip()
        self.baud = int(baud)
        self.camera_index = int(camera_index)
        self.ser = None
        self.reader_thread = None
        self.stop_event = threading.Event()
        self.write_lock = threading.Lock()
        self.command_lock = threading.Lock()
        self.state_lock = threading.RLock()
        self.ack_lock = threading.Lock()
        self.pending_acks = {}
        self.on_reading = None
        self.latest = {
            'temperature': None, 'humidity': None, 'updated': None,
            'connected': False, 'message': 'Arduino not connected',
            'fan_state': None, 'led_state': None, 'mode': None,
            'region_id': None, 'sensor_error': False,
        }
        self.last_command = None
        self.last_command_at = None
        self._legacy_temperature = None
        self._legacy_humidity = None

    def connect(self, on_reading=None, region_id=None):
        if serial is None:
            raise RuntimeError('pyserial is not installed. Run install.bat, then try again.')
        if not self.port:
            raise RuntimeError('Arduino COM port is not configured. Set it in Settings first.')
        with self.state_lock:
            if self.ser and getattr(self.ser, 'is_open', False):
                if on_reading is not None:
                    self.on_reading = on_reading
                if region_id is not None:
                    self.latest['region_id'] = region_id
                return True
            try:
                self.ser = serial.Serial(self.port, self.baud, timeout=1, write_timeout=2)
                time.sleep(2.0)  # Opening the UNO serial port normally resets the board.
                self.ser.reset_input_buffer()
            except Exception as exc:
                self.ser = None
                self.latest.update(connected=False, message=f'Could not open {self.port}: {exc}')
                raise
            self.on_reading = on_reading
            self.stop_event.clear()
            self.latest.update(connected=True, message=f'Port {self.port} open; waiting for DHT11 telemetry', region_id=region_id)
            self.reader_thread = threading.Thread(target=self._reader, name='mushroomguard-serial', daemon=True)
            self.reader_thread.start()
        return True

    def _acknowledge(self, command, ok=True, message=''):
        with self.ack_lock:
            item = self.pending_acks.get(command)
            if item:
                item['ok'] = ok
                item['message'] = message
                item['event'].set()

    def _parse_telemetry(self, line):
        """Support structured firmware frames and the original text sketch."""
        if line.startswith('TEMP:') and ',HUM:' in line:
            values = {}
            for pair in line.split(','):
                if ':' in pair:
                    key, value = pair.split(':', 1)
                    values[key.strip().upper()] = value.strip()
            try:
                temperature = float(values['TEMP'])
                humidity = float(values['HUM'])
            except (KeyError, TypeError, ValueError):
                return None
            fan = values.get('FAN')
            led = values.get('LED')
            mode = values.get('MODE')
        else:
            t_match = re.search(r'Temperature\s*:\s*(-?\d+(?:\.\d+)?)', line, re.I)
            h_match = re.search(r'Humidity\s*:\s*(\d+(?:\.\d+)?)', line, re.I)
            fan_match = re.search(r'(?:Fan Status|FAN)\s*:\s*(ON|OFF)', line, re.I)
            led_match = re.search(r'(?:LED Status|LED)\s*:\s*(ON|OFF)', line, re.I)
            mode_match = re.search(r'Mode\s*:\s*(AUTO|MANUAL)', line, re.I)
            if t_match:
                self._legacy_temperature = float(t_match.group(1))
            if h_match:
                self._legacy_humidity = float(h_match.group(1))
            with self.state_lock:
                if fan_match:
                    self.latest['fan_state'] = fan_match.group(1).upper()
                if led_match:
                    self.latest['led_state'] = led_match.group(1).upper()
                if mode_match:
                    self.latest['mode'] = mode_match.group(1).upper()
            if self._legacy_temperature is None or self._legacy_humidity is None:
                return None
            temperature, humidity = self._legacy_temperature, self._legacy_humidity
            fan = led = mode = None
        if not (-10 <= temperature <= 60 and 0 <= humidity <= 100):
            return None
        return temperature, humidity, fan, led, mode

    def _reader(self):
        while not self.stop_event.is_set():
            try:
                ser = self.ser
                if not ser or not ser.is_open:
                    break
                raw = ser.readline()
                if not raw:
                    continue
                line = raw.decode('utf-8', errors='ignore').strip()
                if not line:
                    continue
                if line.startswith('ACK:'):
                    command = line.split(':', 1)[1].strip().upper()
                    with self.state_lock:
                        if command == 'FAN_ON': self.latest['fan_state'] = 'ON'
                        elif command == 'FAN_OFF': self.latest['fan_state'] = 'OFF'
                        elif command == 'LED_ON': self.latest['led_state'] = 'ON'
                        elif command == 'LED_OFF': self.latest['led_state'] = 'OFF'
                        elif command == 'FAN_MODE_AUTO': self.latest['mode'] = 'AUTO'
                        elif command == 'FAN_MODE_MANUAL': self.latest['mode'] = 'MANUAL'
                        self.latest['message'] = f'Arduino acknowledged {command}'
                    self._acknowledge(command, True, line)
                    continue
                if line.startswith('ERR:'):
                    command = line.split(':', 1)[1].strip().upper()
                    self._acknowledge(command, False, line)
                    with self.state_lock:
                        self.latest['message'] = line
                    continue
                if line == 'DHT_ERROR':
                    with self.state_lock:
                        self.latest.update(sensor_error=True, fan_state='ON', message='DHT11 sensor error; firmware fail-safe has requested fan ON')
                    continue
                if line.startswith('MUSHROOMGUARD_READY'):
                    with self.state_lock:
                        self.latest['message'] = 'Arduino firmware ready'
                    continue
                parsed = self._parse_telemetry(line)
                if not parsed:
                    continue
                temperature, humidity, fan, led, mode = parsed
                updated = time.strftime('%Y-%m-%d %H:%M:%S')
                with self.state_lock:
                    self.latest.update(temperature=temperature, humidity=humidity, updated=updated,
                        connected=True, sensor_error=False,
                        message=f'Receiving DHT11 data from {self.port}')
                    if fan in ('ON', 'OFF'): self.latest['fan_state'] = fan
                    if led in ('ON', 'OFF'): self.latest['led_state'] = led
                    if mode in ('AUTO', 'MANUAL'): self.latest['mode'] = mode
                callback = self.on_reading
                if callback:
                    try:
                        callback(temperature, humidity)
                    except Exception as exc:
                        with self.state_lock:
                            self.latest['message'] = f'Sensor data received; database save failed: {exc}'
            except Exception as exc:
                with self.state_lock:
                    self.latest.update(connected=False, message=f'Serial reader stopped: {exc}')
                break
        with self.state_lock:
            if not self.stop_event.is_set():
                self.latest['connected'] = False

    def command(self, command, timeout=2.0):
        command = str(command).strip().upper()
        if command not in self.ALLOWED_COMMANDS:
            raise ValueError('Unsupported command for the UNO two-relay firmware.')
        # Only one request/acknowledgement may be in flight at a time. This avoids
        # two browser requests overwriting the same command key in pending_acks.
        with self.command_lock:
            if not self.ser or not self.ser.is_open:
                raise RuntimeError('Arduino is not connected. Connect it from Environment first.')
            event = threading.Event()
            pending = {'event': event, 'ok': False, 'message': ''}
            with self.ack_lock:
                self.pending_acks[command] = pending
            try:
                with self.write_lock:
                    self.ser.write((command + '\n').encode('ascii'))
                    self.ser.flush()
                self.last_command = command
                self.last_command_at = time.strftime('%Y-%m-%d %H:%M:%S')
                if not event.wait(timeout):
                    raise TimeoutError(f'No Arduino acknowledgement for {command}. Confirm the updated firmware is uploaded and the baud rate is {self.baud}.')
                if not pending['ok']:
                    raise RuntimeError(pending['message'] or f'Arduino rejected {command}.')
                return f'Arduino acknowledged {command}. Check the physical relay, fan or LED; acknowledgement does not confirm the load is operating.'
            finally:
                with self.ack_lock:
                    self.pending_acks.pop(command, None)

    def disconnect(self):
        self.stop_event.set()
        ser = self.ser
        self.ser = None
        if ser:
            try:
                ser.close()
            except Exception:
                pass
        thread = self.reader_thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2)
        self.reader_thread = None
        with self.state_lock:
            self.latest.update(temperature=None, humidity=None, updated=None, connected=False, message='Arduino disconnected', region_id=None, fan_state=None, led_state=None, mode=None, sensor_error=False)
        with self.ack_lock:
            for pending in self.pending_acks.values():
                pending['event'].set()
                pending['ok'] = False
                pending['message'] = 'Arduino disconnected before acknowledgement.'

    def camera_snapshot(self, destination):
        if cv2 is None:
            raise RuntimeError('OpenCV is not installed. Run install.bat first.')
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        camera = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW if hasattr(cv2, 'CAP_DSHOW') else 0)
        try:
            if not camera.isOpened():
                raise RuntimeError(f'USB camera index {self.camera_index} could not be opened. Close other apps using the camera and check Settings.')
            ok, frame = camera.read()
            if not ok or frame is None:
                raise RuntimeError('Camera opened but did not return a frame.')
            if not cv2.imwrite(str(destination), frame):
                raise RuntimeError('OpenCV could not save the camera frame.')
        finally:
            camera.release()
        return str(destination)

    def test_camera(self):
        if cv2 is None:
            raise RuntimeError('OpenCV is not installed.')
        cap = cv2.VideoCapture(self.camera_index, cv2.CAP_DSHOW if hasattr(cv2, 'CAP_DSHOW') else 0)
        try:
            if not cap.isOpened():
                raise RuntimeError(f'Camera index {self.camera_index} could not be opened.')
            ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError('Camera opened but failed to return a frame.')
            height, width = frame.shape[:2]
            return f'Camera frame captured successfully ({width} × {height}).'
        finally:
            cap.release()

    def shutdown(self):
        self.disconnect()
