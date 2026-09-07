"""
callout_detect.py -- Stage 3 of the BlueprintAI hybrid detection pipeline.

Finds BOM balloon/callout candidates on a full-resolution drawing page
using classical computer vision (OpenCV) only -- no AI model is involved
here, and no coordinates are ever produced by classify.py; they all come
from this module.

Approach: grayscale -> adaptive threshold -> contour detection, filtered by
circularity (contour area vs. minEnclosingCircle area) and by a radius
range that is auto-calibrated from the distribution of candidate sizes
found on the sheet, falling back to config defaults when there aren't
enough candidates to estimate a distribution from.
"""

from __future__ import annotations

import logging
import math
import statistics
from dataclasses import dataclass, field

import cv2
import numpy as np

if __package__:
    from .config import get_settings
else:  # flat imports when run as a standalone script from backend/
    from config import get_settings

logger = logging.getLogger(__name__)

CROP_PADDING_PX = 10

# First-pass ("loose") circularity gate used only to build the candidate
# size distribution for auto-calibration -- intentionally more permissive
# than the final settings.callout_min_circularity gate.
_LOOSE_MIN_CIRCULARITY = 0.55
_LOOSE_MIN_RADIUS_PX = 1
_LOOSE_MAX_RADIUS_PX = 500
_MIN_CANDIDATES_FOR_CALIBRATION = 5


@dataclass
class CalloutCandidate:
    crop_id: str
    x: int  # center x, px (full page coordinates)
    y: int  # center y, px
    radius: float  # px
    bbox: dict  # xmin, ymin, xmax, ymax, px -- includes CROP_PADDING_PX
    circularity: float
    crop_bytes: bytes = field(repr=False)


def detect_callouts(image_path: str, page_id: str = "page") -> list[CalloutCandidate]:
    """Detect balloon/callout candidates on one full-resolution page image.

    Each candidate is cropped tightly (~10px padding) and encoded as PNG
    bytes, ready to hand to classify.py.
    """
    settings = get_settings()

    image = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"callout_detect: could not read image at {image_path}")
    height, width = image.shape[:2]

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        25,
        5,
    )

    contours, _ = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    logger.info("[callout_detect] %s: %d raw contours", page_id, len(contours))

    loose = _loose_candidates(contours)
    min_radius, max_radius = _calibrate_radius_range(loose, settings)

    candidates: list[CalloutCandidate] = []
    counter = 0
    for _area, (cx, cy), radius, circularity in loose:
        if radius < min_radius or radius > max_radius:
            continue
        if circularity < settings.callout_min_circularity:
            continue
        counter += 1
        crop_id = f"{page_id}_c{counter:04d}"
        bbox = _padded_bbox(cx, cy, radius, width, height)
        crop_bytes = _crop_bytes(image, bbox)
        candidates.append(
            CalloutCandidate(
                crop_id=crop_id,
                x=int(round(cx)),
                y=int(round(cy)),
                radius=float(radius),
                bbox=bbox,
                circularity=float(circularity),
                crop_bytes=crop_bytes,
            )
        )

    logger.info(
        "[callout_detect] %s: candidates detected: %d (radius range %.1f-%.1f px, min_circularity=%.2f)",
        page_id,
        len(candidates),
        min_radius,
        max_radius,
        settings.callout_min_circularity,
    )
    return candidates


def _loose_candidates(contours) -> list[tuple[float, tuple[float, float], float, float]]:
    """First pass: circularity-filtered (loosely) but not yet radius-
    filtered, used to build the size distribution for auto-calibration.

    Returns tuples of (area, (cx, cy), radius, circularity).
    """
    results = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area <= 0:
            continue
        (cx, cy), radius = cv2.minEnclosingCircle(contour)
        if radius <= 0 or not (_LOOSE_MIN_RADIUS_PX <= radius <= _LOOSE_MAX_RADIUS_PX):
            continue
        circle_area = math.pi * radius * radius
        circularity = area / circle_area if circle_area > 0 else 0.0
        if circularity < _LOOSE_MIN_CIRCULARITY:
            continue
        results.append((area, (cx, cy), radius, circularity))
    return results


def _calibrate_radius_range(loose, settings) -> tuple[float, float]:
    """Auto-calibrate the accepted radius range from the distribution of
    loose candidate sizes on this sheet; fall back to config defaults when
    there aren't enough candidates to estimate a distribution reliably."""
    radii = [radius for _, _, radius, _ in loose]
    if len(radii) < _MIN_CANDIDATES_FOR_CALIBRATION:
        logger.info(
            "[callout_detect] only %d loose candidate(s); using config default radius range",
            len(radii),
        )
        return float(settings.callout_min_radius_px), float(settings.callout_max_radius_px)

    median = statistics.median(radii)
    low = max(settings.callout_min_radius_px, median * 0.4)
    high = min(settings.callout_max_radius_px * 3, median * 2.5)
    if high <= low:
        return float(settings.callout_min_radius_px), float(settings.callout_max_radius_px)
    return low, high


def _padded_bbox(cx: float, cy: float, radius: float, width: int, height: int) -> dict:
    r = radius + CROP_PADDING_PX
    xmin = max(0, int(math.floor(cx - r)))
    ymin = max(0, int(math.floor(cy - r)))
    xmax = min(width, int(math.ceil(cx + r)))
    ymax = min(height, int(math.ceil(cy + r)))
    return {"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax}


def _crop_bytes(image: np.ndarray, bbox: dict) -> bytes:
    crop = image[bbox["ymin"] : bbox["ymax"], bbox["xmin"] : bbox["xmax"]]
    ok, buf = cv2.imencode(".png", crop)
    if not ok:
        raise ValueError("callout_detect: failed to encode candidate crop")
    return buf.tobytes()
