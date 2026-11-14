import queue
import threading

from services.hardware import HardwareManager


def test_structured_telemetry_and_bad_frame_is_ignored():
    manager = HardwareManager()
    assert manager._parse_telemetry('TEMP:24.6,HUM:88.2,FAN:ON,LED:OFF,MODE:AUTO') == (24.6, 88.2, 'ON', 'OFF', 'AUTO')
    assert manager._parse_telemetry('TEMP:not-a-number,HUM:88.2,FAN:ON') is None
    assert manager._parse_telemetry('TEMP:24.6,HUM:110,FAN:ON') is None


def test_original_sketch_text_telemetry_is_supported():
    manager = HardwareManager()
    assert manager._parse_telemetry('Temperature: 24.0 C') is None
    parsed = manager._parse_telemetry('Humidity: 88 %')
    assert parsed == (24.0, 88.0, None, None, None)
    manager._parse_telemetry('Fan Status: ON')
    assert manager.latest['fan_state'] == 'ON'


class FakeSerial:
    def __init__(self):
        self.is_open = True
        self.lines = queue.Queue()
        self.sensor_fault = False

    def readline(self):
        try:
            return self.lines.get(timeout=0.1)
        except queue.Empty:
            return b''

    def write(self, payload):
        command = payload.decode('ascii').strip()
        if command == 'FAN_OFF' and self.sensor_fault:
            self.lines.put(b'ERR:FAN_OFF\n')
        else:
            self.lines.put(f'ACK:{command}\n'.encode('ascii'))
        return len(payload)

    def flush(self):
        pass

    def close(self):
        self.is_open = False


def test_command_requires_and_waits_for_matching_acknowledgement():
    manager = HardwareManager()
    fake = FakeSerial()
    manager.ser = fake
    manager.stop_event.clear()
    manager.reader_thread = threading.Thread(target=manager._reader, daemon=True)
    manager.reader_thread.start()
    try:
        message = manager.command('FAN_MODE_AUTO')
        assert 'acknowledged FAN_MODE_AUTO' in message
        try:
            manager.command('FAN_OFF')
        except Exception as exc:
            raise AssertionError(f'Expected FAN_OFF acknowledgement: {exc}')
        fake.sensor_fault = True
        try:
            manager.command('FAN_OFF')
        except RuntimeError as exc:
            assert 'ERR:FAN_OFF' in str(exc)
        else:
            raise AssertionError('A rejected FAN_OFF should not be treated as successful.')
    finally:
        manager.disconnect()
