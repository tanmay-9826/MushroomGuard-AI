"""ThingSpeak cloud bridge for MushroomGuard AI.

The Arduino remains connected to the local PC over USB serial. This service
publishes the most recent valid telemetry asynchronously so a slow/unavailable
internet connection never blocks the Arduino reader or local fan control.
"""
from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_ROOT = "https://api.thingspeak.com"


class ThingSpeakError(RuntimeError):
    """Raised when ThingSpeak rejects a request or cannot be reached."""


class ThingSpeakPublisher:
    def __init__(self, channel_id="", write_key="", read_key="", update_interval=20, timeout=8):
        self.channel_id = str(channel_id or "").strip()
        self.write_key = str(write_key or "").strip()
        self.read_key = str(read_key or "").strip()
        # ThingSpeak's free service requires at least 15 seconds between writes.
        self.update_interval = max(15, int(update_interval or 20))
        self.timeout = max(2, int(timeout or 8))
        self.channel_id_is_valid = self.channel_id.isdigit()
        self.enabled = bool(self.channel_id_is_valid and self.write_key)

        self._lock = threading.RLock()
        self._event = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._latest_payload = None
        self._last_attempt = 0.0
        self._status = {
            "enabled": self.enabled,
            "connected": False,
            "channel_id": self.channel_id if self.enabled else None,
            "update_interval_seconds": self.update_interval,
            "last_attempt_at": None,
            "last_success_at": None,
            "entry_id": None,
            "last_error": None,
            "message": "ThingSpeak is configured but no sensor reading has been uploaded." if self.enabled
                       else ("ThingSpeak Channel ID must contain digits only." if self.channel_id and not self.channel_id_is_valid
                             else "ThingSpeak is not configured. Add channel ID and write API key to .env."),
        }

    @staticmethod
    def make_fields(temperature, humidity, telemetry=None, region_id=None):
        """Map MushroomGuard telemetry to the channel's seven numeric fields.

        Field 1 temperature (C), 2 humidity (%), 3 fan (1/0), 4 LED (1/0),
        5 mode (0=AUTO, 1=MANUAL), 6 sensor OK (1), 7 local room database ID.
        Unknown relay/mode values are omitted rather than guessed.
        """
        telemetry = telemetry or {}
        fields = {
            "field1": round(float(temperature), 1),
            "field2": round(float(humidity), 1),
        }
        fan = str(telemetry.get("fan_state") or "").upper()
        led = str(telemetry.get("led_state") or "").upper()
        mode = str(telemetry.get("mode") or "").upper()
        if fan in ("ON", "OFF"):
            fields["field3"] = 1 if fan == "ON" else 0
        if led in ("ON", "OFF"):
            fields["field4"] = 1 if led == "ON" else 0
        if mode in ("AUTO", "MANUAL"):
            fields["field5"] = 0 if mode == "AUTO" else 1
        if telemetry.get("sensor_error") is False:
            fields["field6"] = 1
        if region_id is not None:
            fields["field7"] = int(region_id)
        return fields

    def start(self):
        if not self.enabled:
            return False
        with self._lock:
            if self._thread and self._thread.is_alive():
                return True
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="mushroomguard-thingspeak", daemon=True)
            self._thread.start()
        return True

    def submit(self, temperature, humidity, telemetry=None, region_id=None):
        """Queue the newest reading. This method performs no network I/O."""
        if not self.enabled:
            return False
        payload = self.make_fields(temperature, humidity, telemetry, region_id)
        with self._lock:
            self._latest_payload = payload
        self._event.set()
        return True

    def _post_fields(self, fields):
        body = {"api_key": self.write_key, **fields}
        request = Request(
            f"{API_ROOT}/update.json",
            data=urlencode(body).encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "MushroomGuardAI/1.1"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise ThingSpeakError(f"ThingSpeak upload failed: {exc}") from exc
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ThingSpeakError(f"ThingSpeak returned an unreadable response: {raw[:120]}") from exc
        entry_id = result.get("entry_id") if isinstance(result, dict) else None
        if not entry_id:
            raise ThingSpeakError("ThingSpeak did not accept the update (entry_id was empty/zero). Check the Write API Key and channel fields.")
        return int(entry_id)

    def _run(self):
        while not self._stop.is_set():
            self._event.wait(timeout=1.0)
            if self._stop.is_set():
                break
            if not self._event.is_set():
                continue
            self._event.clear()

            wait_for = self.update_interval - (time.monotonic() - self._last_attempt)
            while wait_for > 0 and not self._stop.is_set():
                # New readings replace the queued payload while waiting for the
                # ThingSpeak rate limit; upload only the newest sample.
                self._event.wait(timeout=min(wait_for, 1.0))
                self._event.clear()
                wait_for = self.update_interval - (time.monotonic() - self._last_attempt)
            if self._stop.is_set():
                break

            with self._lock:
                payload = dict(self._latest_payload or {})
            if not payload:
                continue

            attempted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._last_attempt = time.monotonic()
            with self._lock:
                self._status["last_attempt_at"] = attempted_at
            try:
                entry_id = self._post_fields(payload)
                success_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
                with self._lock:
                    self._status.update(connected=True, last_success_at=success_at,
                                        entry_id=entry_id, last_error=None,
                                        message=f"Latest sensor data uploaded to ThingSpeak (entry {entry_id}).")
            except ThingSpeakError as exc:
                with self._lock:
                    self._status.update(connected=False, last_error=str(exc), message=str(exc))

    def fetch_latest(self):
        """Read the latest private channel feed entry for display in Flask."""
        if not self.enabled:
            raise ThingSpeakError("ThingSpeak is not configured. Add channel credentials to .env.")
        if not self.read_key:
            raise ThingSpeakError("ThingSpeak Read API Key is missing from .env.")
        url = f"{API_ROOT}/channels/{self.channel_id}/feeds/last.json?{urlencode({'api_key': self.read_key})}"
        request = Request(url, headers={"User-Agent": "MushroomGuardAI/1.1"}, method="GET")
        try:
            with urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise ThingSpeakError(f"Could not read the ThingSpeak channel: {exc}") from exc
        if not isinstance(result, dict) or not result.get("created_at"):
            raise ThingSpeakError("ThingSpeak returned no channel reading. Wait for the first sensor upload.")
        return {
            "created_at": result.get("created_at"),
            "entry_id": result.get("entry_id"),
            "temperature": _to_float(result.get("field1")),
            "humidity": _to_float(result.get("field2")),
            "fan_state": _state_from_bit(result.get("field3")),
            "led_state": _state_from_bit(result.get("field4")),
            "fan_mode": _mode_from_value(result.get("field5")),
            "sensor_ok": _to_float(result.get("field6")),
            "region_id": _to_float(result.get("field7")),
        }

    def status(self):
        with self._lock:
            return dict(self._status)

    def shutdown(self):
        self._stop.set()
        self._event.set()
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
        self._thread = None


def _to_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _state_from_bit(value):
    parsed = _to_float(value)
    if parsed is None:
        return None
    return "ON" if parsed == 1 else "OFF" if parsed == 0 else None


def _mode_from_value(value):
    parsed = _to_float(value)
    if parsed == 0:
        return "AUTO"
    if parsed == 1:
        return "MANUAL"
    return None
