"""Bounded Camlora MJPEG-to-MP4 recorder for MushroomGuard AI.

This records the Camlora HTTP MJPEG stream in a background thread. The camera
continues to run on the Android phone; Flask writes an MP4 on the PC. No
YOLO prediction is performed here.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import cv2
    import numpy as np
except Exception:  # keep ordinary app features available without OpenCV
    cv2 = None
    np = None


def extract_jpegs(chunks, max_frame_bytes=12 * 1024 * 1024):
    """Yield complete JPEG payloads from a multipart/MJPEG byte stream.

    The parser intentionally uses JPEG start/end markers, so it does not rely
    on a particular multipart boundary string.
    """
    buffer = bytearray()
    for chunk in chunks:
        if not chunk:
            continue
        buffer.extend(chunk)
        while True:
            start = buffer.find(b"\xff\xd8\xff")
            if start < 0:
                # Keep a tiny tail in case the SOI marker straddles chunks.
                if len(buffer) > 2:
                    del buffer[:-2]
                break
            if start:
                del buffer[:start]
            end = buffer.find(b"\xff\xd9", 3)
            if end < 0:
                if len(buffer) > max_frame_bytes:
                    raise ValueError("Camlora frame exceeded the allowed frame size.")
                break
            frame = bytes(buffer[:end + 2])
            del buffer[:end + 2]
            if len(frame) <= max_frame_bytes:
                yield frame
            else:
                raise ValueError("Camlora frame exceeded the allowed frame size.")


class CamloraVideoRecorder:
    """Manage per-user bounded recordings with app-context DB updates."""

    def __init__(self, app):
        self.app = app
        self._lock = threading.RLock()
        self._jobs = {}  # recording_id -> {thread, stop_event, user_id}

    def shutdown(self):
        """Ask all active recording threads to stop during app shutdown."""
        with self._lock:
            jobs = list(self._jobs.values())
            for job in jobs:
                job["stop_event"].set()
        for job in jobs:
            job["thread"].join(timeout=12)

    def is_running_for_user(self, user_id):
        with self._lock:
            return any(job["user_id"] == user_id and job["thread"].is_alive()
                       for job in self._jobs.values())

    def start(self, recording_id, user_id, stream_url, output_path,
              max_seconds=600, max_bytes=300 * 1024 * 1024, target_fps=8.0):
        with self._lock:
            if self.is_running_for_user(user_id):
                raise RuntimeError("A video recording is already running for this account.")
            stop_event = threading.Event()
            thread = threading.Thread(
                target=self._record_worker,
                name=f"camlora-recording-{recording_id}",
                args=(recording_id, stream_url, Path(output_path), stop_event,
                      int(max_seconds), int(max_bytes), float(target_fps)),
                daemon=True,
            )
            self._jobs[recording_id] = {
                "thread": thread, "stop_event": stop_event, "user_id": user_id
            }
            thread.start()

    def stop(self, recording_id, user_id, wait_seconds=12):
        with self._lock:
            job = self._jobs.get(recording_id)
            if not job or job["user_id"] != user_id:
                return False
            job["stop_event"].set()
            thread = job["thread"]
        thread.join(timeout=wait_seconds)
        return not thread.is_alive()

    def _db_update(self, recording_id, **values):
        from models.database import get_db
        allowed = {
            "status", "stopped_at", "duration_seconds", "frame_count",
            "file_size_bytes", "width", "height", "fps", "error"
        }
        assignments = [(key, value) for key, value in values.items() if key in allowed]
        if not assignments:
            return
        sql = "UPDATE video_recordings SET " + ",".join(f"{key}=?" for key, _ in assignments) + " WHERE id=?"
        with self.app.app_context():
            db = get_db()
            db.execute(sql, [value for _, value in assignments] + [recording_id])
            db.commit()

    def _record_worker(self, recording_id, stream_url, output_path, stop_event,
                       max_seconds, max_bytes, target_fps):
        writer = None
        response = None
        frame_count = 0
        width = height = 0
        started = time.monotonic()
        last_write = 0.0
        last_db_update = 0.0
        error = None
        final_status = "failed"
        try:
            if cv2 is None or np is None:
                raise RuntimeError("OpenCV and NumPy are required for video recording. Install requirements.txt.")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            response = urlopen(Request(stream_url, headers={"User-Agent": "MushroomGuardAI/1.4"}), timeout=10)
            content_type = response.headers.get("Content-Type", "").lower()
            if response.status != 200 or "multipart/x-mixed-replace" not in content_type:
                raise RuntimeError(f"Camlora did not return an MJPEG stream ({content_type or response.status}).")

            reader = getattr(response, "read1", response.read)
            chunks = iter(lambda: reader(64 * 1024), b"")
            frame_interval = 1.0 / max(1.0, min(target_fps, 15.0))
            for jpeg in extract_jpegs(chunks):
                if stop_event.is_set():
                    final_status = "stopped"
                    break
                elapsed = time.monotonic() - started
                if elapsed >= max_seconds:
                    final_status = "completed"
                    break
                now = time.monotonic()
                if last_write and now - last_write < frame_interval:
                    continue
                image = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
                if image is None:
                    continue
                h, w = image.shape[:2]
                if not width:
                    # Cap output dimensions while preserving the aspect ratio.
                    scale = min(1.0, 1280.0 / max(w, h))
                    width = max(2, int(w * scale) // 2 * 2)
                    height = max(2, int(h * scale) // 2 * 2)
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    writer = cv2.VideoWriter(str(output_path), fourcc, max(1.0, min(target_fps, 15.0)), (width, height))
                    if not writer.isOpened():
                        raise RuntimeError("Could not create the MP4 file. Check that OpenCV video codecs are available.")
                    self._db_update(recording_id, status="recording", width=width, height=height,
                                    fps=max(1.0, min(target_fps, 15.0)))
                if image.shape[1] != width or image.shape[0] != height:
                    image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
                writer.write(image)
                frame_count += 1
                last_write = now

                # Update status periodically, and enforce the file-size ceiling.
                if frame_count % 20 == 0:
                    size = output_path.stat().st_size if output_path.exists() else 0
                    if size >= max_bytes:
                        final_status = "completed"
                        break
                    if now - last_db_update >= 2.0:
                        self._db_update(recording_id, frame_count=frame_count,
                                        duration_seconds=round(elapsed, 2), file_size_bytes=size)
                        last_db_update = now
            else:
                final_status = "completed" if frame_count else "failed"
            if stop_event.is_set() and frame_count:
                final_status = "stopped"
            if frame_count == 0 and not error:
                raise RuntimeError("No video frames were received from Camlora. Check that its live stream is running.")
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            error = str(exc)[:500]
            final_status = "failed" if frame_count == 0 else "completed"
        except Exception as exc:  # ensure worker failures reach the UI and log
            error = f"Unexpected recording error: {exc}"[:500]
            final_status = "failed" if frame_count == 0 else "completed"
            self.app.logger.exception("Camlora recording %s failed", recording_id)
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass
            if writer is not None:
                writer.release()
            duration = max(0.0, time.monotonic() - started)
            size = output_path.stat().st_size if output_path.exists() else 0
            if frame_count == 0 and output_path.exists():
                output_path.unlink(missing_ok=True)
            self._db_update(
                recording_id,
                status=final_status,
                stopped_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                duration_seconds=round(duration, 2),
                frame_count=frame_count,
                file_size_bytes=size,
                width=width or None,
                height=height or None,
                fps=max(1.0, min(target_fps, 15.0)),
                error=error,
            )
            with self._lock:
                self._jobs.pop(recording_id, None)
