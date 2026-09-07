"""Turns raw Gemini JSON text into validated ExtractionResult data.

Pipeline: raw text -> JSON parsing -> per-item Pydantic validation ->
normalization/cleanup -> ExtractionResult. Never trusts the model blindly:
a single malformed row is dropped with a warning rather than crashing the
whole extraction.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from pydantic import ValidationError

from .confidence import clamp_confidence, is_low_confidence, low_confidence_warning
from .exceptions import InvalidExtractionError
from .models import BOMItem, BoundingBox, Callout, ExtractedComponent
from .utils import is_already_normalized, normalize_bbox_pixels

logger = logging.getLogger(__name__)


def parse_json_response(raw_text: str) -> dict[str, Any]:
    """Parse raw model text into a dict, tolerating markdown code fences.

    Raises InvalidExtractionError if the text is empty or not valid JSON.
    """
    if not raw_text or not raw_text.strip():
        raise InvalidExtractionError("Empty response from Gemini")

    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        # Strip a leading ```json / ``` fence and trailing ``` fence.
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise InvalidExtractionError(f"Malformed JSON in Gemini response: {exc}") from exc

    if not isinstance(parsed, dict):
        raise InvalidExtractionError(
            f"Expected a JSON object from Gemini, got {type(parsed).__name__}"
        )
    return parsed


def _resolve_bbox(
    raw_bbox: dict[str, Any],
    image_width: Optional[int],
    image_height: Optional[int],
) -> BoundingBox:
    xmin = float(raw_bbox["xmin"])
    ymin = float(raw_bbox["ymin"])
    xmax = float(raw_bbox["xmax"])
    ymax = float(raw_bbox["ymax"])

    if not is_already_normalized(xmin, ymin, xmax, ymax) and image_width and image_height:
        normalized = normalize_bbox_pixels(xmin, ymin, xmax, ymax, image_width, image_height)
        return BoundingBox(**normalized)

    return BoundingBox(xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax)


def validate_bom_items(
    raw_items: list[dict[str, Any]],
    low_confidence_threshold: float,
) -> tuple[list[BOMItem], list[str]]:
    """Validate raw BOM row dicts into BOMItem models. Bad rows are skipped, not fatal."""
    items: list[BOMItem] = []
    warnings: list[str] = []

    for index, raw in enumerate(raw_items):
        try:
            raw = dict(raw)
            raw["confidence_score"] = clamp_confidence(raw.get("confidence_score"))
            item = BOMItem(**raw)
        except (ValidationError, TypeError, KeyError) as exc:
            warnings.append(f"Skipped invalid BOM row at index {index}: {exc}")
            logger.warning("Invalid BOM row at index %d: %s", index, exc)
            continue

        items.append(item)
        if is_low_confidence(item.confidence_score, low_confidence_threshold):
            warnings.append(low_confidence_warning("BOM item", item.item_number, item.confidence_score))

    return items, warnings


def validate_callouts(
    raw_callouts: list[dict[str, Any]],
    low_confidence_threshold: float,
    image_width: Optional[int] = None,
    image_height: Optional[int] = None,
) -> tuple[list[Callout], list[str]]:
    """Validate raw callout dicts into Callout models.

    Bad rows are skipped with a warning. Duplicate bubble numbers are kept
    (both are preserved) but flagged with a warning, since downstream
    reconciliation needs to know about the ambiguity rather than have it
    silently dropped.
    """
    callouts: list[Callout] = []
    warnings: list[str] = []
    seen_bubble_numbers: set[str] = set()

    for index, raw in enumerate(raw_callouts):
        try:
            raw = dict(raw)
            bbox_raw = raw.get("bounding_box")
            if not isinstance(bbox_raw, dict):
                raise ValueError("missing or invalid bounding_box")
            bbox = _resolve_bbox(bbox_raw, image_width, image_height)
            confidence = clamp_confidence(raw.get("confidence_score"))
            callout = Callout(
                bubble_number=str(raw["bubble_number"]),
                location_description=raw.get("location_description"),
                bounding_box=bbox,
                confidence_score=confidence,
            )
        except (ValidationError, TypeError, KeyError, ValueError) as exc:
            warnings.append(f"Skipped invalid callout at index {index}: {exc}")
            logger.warning("Invalid callout at index %d: %s", index, exc)
            continue

        if callout.bubble_number in seen_bubble_numbers:
            warnings.append(f"Duplicate callout bubble number detected: {callout.bubble_number}")
        seen_bubble_numbers.add(callout.bubble_number)

        callouts.append(callout)
        if is_low_confidence(callout.confidence_score, low_confidence_threshold):
            warnings.append(
                low_confidence_warning("callout bubble", callout.bubble_number, callout.confidence_score)
            )

    return callouts, warnings


def build_components(
    bom_items: list[BOMItem],
    callouts: list[Callout],
) -> list[ExtractedComponent]:
    """Populate components by directly matching BOM item_number to callout bubble_number.

    This is intentionally a simple exact-match join, not a reconciliation
    engine — deterministic fuzzy/spatial matching is owned by Person 5's
    module. Only pairs that already agree exactly are combined here.
    """
    callouts_by_bubble = {c.bubble_number: c for c in callouts}
    components: list[ExtractedComponent] = []

    for item in bom_items:
        callout = callouts_by_bubble.get(item.item_number)
        if callout is None:
            continue
        components.append(
            ExtractedComponent(
                id=f"cmp_{item.item_number.zfill(3) if item.item_number.isdigit() else item.item_number}",
                item_number=item.item_number,
                bubble_number=callout.bubble_number,
                part_number=item.part_number,
                part_name=item.part_name,
                quantity=item.quantity,
                material_specification=item.material_specification,
                confidence_score=min(item.confidence_score, callout.confidence_score),
                bounding_box=callout.bounding_box,
            )
        )

    return components
