"""Confidence score helpers shared across BOM items, callouts, and components."""

from __future__ import annotations

from typing import Optional

CONFIDENCE_MIN = 0.0
CONFIDENCE_MAX = 1.0


def clamp_confidence(value: Optional[float]) -> float:
    """Clamp a confidence score into [0, 1]. Missing/invalid values default to 0.0."""
    if value is None:
        return CONFIDENCE_MIN
    try:
        value = float(value)
    except (TypeError, ValueError):
        return CONFIDENCE_MIN
    return max(CONFIDENCE_MIN, min(CONFIDENCE_MAX, value))


def is_valid_confidence(value: object) -> bool:
    """True if value is a number within [0, 1] without needing clamping."""
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return False
    return CONFIDENCE_MIN <= value <= CONFIDENCE_MAX


def is_low_confidence(value: float, threshold: float) -> bool:
    """True if a (already-clamped) confidence score falls below the given threshold."""
    return value < threshold


def low_confidence_warning(label: str, identifier: str, score: float) -> str:
    """Build a standard warning string for a low-confidence extraction."""
    return f"Low confidence extraction for {label} {identifier} (confidence={score:.2f})"
