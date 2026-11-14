"""QR decoding and growing-unit code validation for MushroomGuard AI.

The QR code identifies a registered growing unit. It does not classify crop
biology or infer growth stage from a photograph.
"""
from __future__ import annotations

import re
from typing import Optional

UNIT_STAGES = {
    "mushroom": [
        "Preparation & Spawning",
        "Incubation & Mycelium Growth",
        "Pinhead Formation & Fruiting",
        "Harvesting",
    ],
    "microgreen": [
        "Seed & Tray Preparation",
        "Germination",
        "Growth & Development",
        "Harvesting",
    ],
}

_UNIT_CODE = re.compile(r"^(?:MUSH|MICRO)-[0-9]{5,8}$", re.IGNORECASE)


def parse_unit_qr_payload(payload: str) -> Optional[str]:
    """Return a normalized unit code from a MushroomGuard QR payload.

    Accepts the project's canonical ``MUSHROOMGUARD:<UNIT-ID>`` format and
    plain unit IDs for compatibility with manually printed labels.
    """
    if not isinstance(payload, str):
        return None
    value = payload.strip()
    if value.upper().startswith("MUSHROOMGUARD:"):
        value = value.split(":", 1)[1].strip()
    value = value.upper()
    if not _UNIT_CODE.fullmatch(value):
        return None
    return value


def decode_unit_qr_from_jpeg(image_bytes: bytes) -> Optional[str]:
    """Decode a registered-unit QR payload from JPEG bytes using OpenCV.

    Returns the raw decoded QR text; caller must pass it to
    ``parse_unit_qr_payload`` and perform an owner-scoped database lookup.
    """
    if not image_bytes:
        return None
    try:
        import cv2
        import numpy as np
    except ImportError as exc:  # pragma: no cover - optional runtime safeguard
        raise RuntimeError("OpenCV is required for camera QR scanning.") from exc

    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The camera did not return a readable JPEG image.")
    detector = cv2.QRCodeDetector()
    decoded, _points, _straight = detector.detectAndDecode(image)
    return decoded.strip() if decoded and decoded.strip() else None


def stage_name(crop_type: str, stage: int) -> str:
    """Return a human-readable stage label, or a safe fallback."""
    stages = UNIT_STAGES.get(str(crop_type or "").lower(), [])
    if isinstance(stage, int) and 1 <= stage <= len(stages):
        return stages[stage - 1]
    return "Unknown stage"
