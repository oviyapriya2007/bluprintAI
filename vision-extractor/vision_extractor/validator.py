"""Turns raw vision-model JSON text into validated ExtractionResult data.

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
from .models import (
    BOMItem,
    BoundingBox,
    Callout,
    ExtractedComponent,
    LeaderEndpoint,
    LeaderLineStatus,
)
from .utils import is_already_normalized, normalize_bbox_pixels, normalize_coordinate

logger = logging.getLogger(__name__)

# Prompt contract: omit callouts below this confidence rather than guessing.
CALLOUT_MIN_CONFIDENCE = 0.85
VALID_LEADER_STATUSES: set[str] = {"clear", "unclear", "missing"}


def parse_json_response(raw_text: str) -> dict[str, Any]:
    """Parse raw model text into a dict, tolerating markdown code fences.

    Raises InvalidExtractionError if the text is empty or not valid JSON.
    """
    if not raw_text or not raw_text.strip():
        raise InvalidExtractionError("Empty response from vision model")

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
        raise InvalidExtractionError(f"Malformed JSON in vision model response: {exc}") from exc

    if not isinstance(parsed, dict):
        raise InvalidExtractionError(
            f"Expected a JSON object from vision model, got {type(parsed).__name__}"
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


def _resolve_leader_endpoint(
    raw_endpoint: Any,
    image_width: Optional[int],
    image_height: Optional[int],
) -> Optional[LeaderEndpoint]:
    if raw_endpoint is None:
        return None
    if not isinstance(raw_endpoint, dict):
        raise ValueError("leader_endpoint must be an object with x/y or null")
    x = float(raw_endpoint["x"])
    y = float(raw_endpoint["y"])
    if not is_already_normalized(x, y, x, y) and image_width and image_height:
        x = normalize_coordinate(x, image_width)
        y = normalize_coordinate(y, image_height)
    return LeaderEndpoint(x=x, y=y)


def _extract_raw_bbox(raw: dict[str, Any]) -> dict[str, Any]:
    """Require ``bubble_bbox``. Legacy ``bounding_box`` accepted only as fallback."""
    bbox_raw = raw.get("bubble_bbox")
    if isinstance(bbox_raw, dict):
        return bbox_raw
    bbox_raw = raw.get("bounding_box")
    if isinstance(bbox_raw, dict):
        return bbox_raw
    raise ValueError("malformed bubble_bbox: missing or not an object")


FORBIDDEN_COMPONENT_NAME_FIELDS = frozenset(
    {
        "inferred_part_name",
        "visual_component_name",
        "guessed_component",
        "guessed_component_name",
    }
)


def _normalize_raw_bom_row(raw: dict[str, Any]) -> dict[str, Any]:
    """Map the transcription schema onto BOMItem fields.

    - ``material`` (prompt schema) -> ``material_specification`` (contract)
    - Discard model-supplied ``part_name`` so the UI cannot show an invented
      name; the visible table text lives only in ``description``.
    - Strip any inferred/guessed name fields entirely.
    """
    row = dict(raw)
    for key in FORBIDDEN_COMPONENT_NAME_FIELDS:
        row.pop(key, None)
    if row.get("material_specification") is None and "material" in row:
        row["material_specification"] = row.get("material")
    row.pop("material", None)
    # Vision is not allowed to invent a separate component name.
    row["part_name"] = None
    return row


def validate_bom_items(
    raw_items: list[dict[str, Any]],
    low_confidence_threshold: float,
) -> tuple[list[BOMItem], list[str]]:
    """Validate raw BOM row dicts into BOMItem models. Bad rows are skipped, not fatal."""
    items: list[BOMItem] = []
    warnings: list[str] = []

    for index, raw in enumerate(raw_items):
        try:
            if not isinstance(raw, dict):
                raise TypeError("BOM row is not an object")
            row = _normalize_raw_bom_row(raw)
            row["confidence_score"] = clamp_confidence(row.get("confidence_score"))
            item = BOMItem(**row)
        except (ValidationError, TypeError, KeyError) as exc:
            warnings.append(f"Skipped invalid BOM row at index {index}: {exc}")
            logger.warning("Invalid BOM row at index %d: %s", index, exc)
            continue

        items.append(item)
        if is_low_confidence(item.confidence_score, low_confidence_threshold):
            warnings.append(low_confidence_warning("BOM item", item.item_number, item.confidence_score))

    return items, warnings


def _normalize_leader_status(raw_status: Any) -> LeaderLineStatus:
    if raw_status is None or raw_status == "":
        return "missing"
    status = str(raw_status).strip().lower()
    if status not in VALID_LEADER_STATUSES:
        raise ValueError(
            f"leader_line_status must be one of {sorted(VALID_LEADER_STATUSES)}, got {raw_status!r}"
        )
    return status  # type: ignore[return-value]


def validate_callouts(
    raw_callouts: list[dict[str, Any]],
    low_confidence_threshold: float,
    image_width: Optional[int] = None,
    image_height: Optional[int] = None,
) -> tuple[list[Callout], list[str]]:
    """Validate raw callout dicts into Callout models (strict bubble schema).

    Rules:
      - ``bubble_bbox`` localizes the numbered balloon only (0–1000 coords).
      - confidence < 0.85 → callout omitted.
      - Optional leader fields (``leader_endpoint``, ``leader_line_status``) are
        accepted for verification/legacy, but balloon-only detections omit them.
      - unclear/missing → ``leader_endpoint`` forced to null.
      - No fuzzy component matching here.

    Warnings (non-fatal) are emitted for unclear leaders, duplicate bubble
    numbers, malformed bboxes, and missing endpoints.
    """
    callouts: list[Callout] = []
    warnings: list[str] = []
    seen_bubble_numbers: set[str] = set()

    for index, raw in enumerate(raw_callouts):
        bubble_label = repr((raw or {}).get("bubble_number")) if isinstance(raw, dict) else "?"
        try:
            if not isinstance(raw, dict):
                raise ValueError("callout row is not an object")
            raw = dict(raw)
            bubble_label = repr(raw.get("bubble_number"))

            confidence = clamp_confidence(raw.get("confidence_score"))
            if confidence < CALLOUT_MIN_CONFIDENCE:
                warnings.append(
                    f"Skipped callout at index {index} (bubble={bubble_label}): "
                    f"confidence {confidence:.2f} below minimum {CALLOUT_MIN_CONFIDENCE}"
                )
                continue

            try:
                bbox = _resolve_bbox(_extract_raw_bbox(raw), image_width, image_height)
            except (ValidationError, TypeError, KeyError, ValueError) as bbox_exc:
                warnings.append(
                    f"Malformed bubble_bbox for callout at index {index} "
                    f"(bubble={bubble_label}): {bbox_exc}"
                )
                logger.warning("Malformed bubble_bbox at index %d: %s", index, bbox_exc)
                continue

            # Balloon-only detection schema omits leader fields; treat as missing
            # without warning. Explicit leader fields still get the strict checks.
            has_leader_fields = (
                "leader_line_status" in raw or "leader_endpoint" in raw
            )
            leader_status = _normalize_leader_status(raw.get("leader_line_status"))
            try:
                leader_endpoint = _resolve_leader_endpoint(
                    raw.get("leader_endpoint"), image_width, image_height
                )
            except (ValidationError, TypeError, KeyError, ValueError) as endpoint_exc:
                warnings.append(
                    f"Missing endpoint for callout bubble {bubble_label}: "
                    f"invalid leader_endpoint ({endpoint_exc})"
                )
                leader_endpoint = None
                if leader_status == "clear":
                    leader_status = "missing"

            if not has_leader_fields:
                leader_status = "missing"
                leader_endpoint = None
            elif leader_status == "unclear":
                if leader_endpoint is not None:
                    warnings.append(
                        f"Unclear leader line for callout bubble {bubble_label}: "
                        "endpoint discarded (do not invent a target)"
                    )
                else:
                    warnings.append(
                        f"Unclear leader line for callout bubble {bubble_label}"
                    )
                leader_endpoint = None
            elif leader_status == "missing":
                if leader_endpoint is not None:
                    warnings.append(
                        f"Missing endpoint for callout bubble {bubble_label}: "
                        "endpoint discarded because leader_line_status is 'missing'"
                    )
                else:
                    warnings.append(
                        f"Missing endpoint for callout bubble {bubble_label}"
                    )
                leader_endpoint = None
            elif leader_status == "clear" and leader_endpoint is None:
                warnings.append(
                    f"Missing endpoint for callout bubble {bubble_label}: "
                    "leader_line_status was 'clear' but leader_endpoint was null; "
                    "downgraded to 'missing'"
                )
                leader_status = "missing"

            callout = Callout(
                bubble_number=str(raw["bubble_number"]),
                location_description=raw.get("location_description"),
                bubble_bbox=bbox,
                confidence_score=confidence,
                leader_endpoint=leader_endpoint,
                leader_line_status=leader_status,
            )
        except (ValidationError, TypeError, KeyError, ValueError) as exc:
            message = str(exc).lower()
            if "bubble_bbox" in message or "bounding_box" in message or "malformed" in message:
                warnings.append(
                    f"Malformed bubble_bbox for callout at index {index} "
                    f"(bubble={bubble_label}): {exc}"
                )
            else:
                warnings.append(f"Skipped invalid callout at index {index}: {exc}")
            logger.warning("Invalid callout at index %d: %s", index, exc)
            continue

        if callout.bubble_number in seen_bubble_numbers:
            warnings.append(
                f"Duplicate bubble number detected: {callout.bubble_number}"
            )
        seen_bubble_numbers.add(callout.bubble_number)

        callouts.append(callout)
        # With CALLOUT_MIN_CONFIDENCE=0.85, this only fires if the warning
        # threshold is raised above 0.85.
        if is_low_confidence(callout.confidence_score, low_confidence_threshold):
            warnings.append(
                low_confidence_warning(
                    "callout bubble", callout.bubble_number, callout.confidence_score
                )
            )

    return callouts, warnings


def build_components(
    bom_items: list[BOMItem],
    callouts: list[Callout],
) -> tuple[list[ExtractedComponent], list[str]]:
    """Strict post-validation join of BOM rows and callout balloons.

    Rules:
      - A component exists only when ``callout.bubble_number == bom_item.item_number``
        (exact string match; no fuzzy / normalized matching).
      - ``part_name`` is copied only from ``bom_item.description`` — never invented.
      - Orphan callouts do not create components (warning emitted).
      - Orphan BOM rows stay in ``bom_items`` but emit ``No callout detected.``
    """
    warnings: list[str] = []
    components: list[ExtractedComponent] = []

    bom_by_item: dict[str, BOMItem] = {}
    for item in bom_items:
        # Keep first BOM row per exact item_number for matching.
        bom_by_item.setdefault(item.item_number, item)

    callouts_by_bubble: dict[str, list[Callout]] = {}
    for callout in callouts:
        callouts_by_bubble.setdefault(callout.bubble_number, []).append(callout)

    matched_item_numbers: set[str] = set()

    for item in bom_items:
        matches = callouts_by_bubble.get(item.item_number, [])
        if not matches:
            warnings.append(f"BOM item {item.item_number}: No callout detected.")
            continue

        callout = matches[0]
        matched_item_numbers.add(item.item_number)
        components.append(
            ExtractedComponent(
                id=(
                    f"cmp_{item.item_number.zfill(3)}"
                    if item.item_number.isdigit()
                    else f"cmp_{item.item_number}"
                ),
                item_number=item.item_number,
                bubble_number=callout.bubble_number,
                part_number=item.part_number,
                # Direct copy from transcribed BOM description only.
                part_name=item.description,
                quantity=item.quantity,
                material_specification=item.material_specification,
                confidence_score=min(item.confidence_score, callout.confidence_score),
                bounding_box=callout.bubble_bbox,
            )
        )

    for callout in callouts:
        if callout.bubble_number not in bom_by_item:
            warnings.append(
                f"Callout {callout.bubble_number} has no matching BOM row."
            )

    return components, warnings
