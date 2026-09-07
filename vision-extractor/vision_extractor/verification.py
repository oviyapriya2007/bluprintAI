"""Second-pass verification of detected callout bubbles.

Crops around each proposed ``bubble_bbox``, asks Claude to confirm the bubble,
number, leader, endpoint, and bbox quality, then drops or corrects the callout.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from PIL import Image
from pydantic import BaseModel, Field, ValidationError, model_validator

from .exceptions import ClaudeAPIError, InvalidExtractionError
from .models import BoundingBox, Callout
from .prompts import CALLOUT_VERIFICATION_PROMPT
from .utils import NORMALIZED_MAX
from .validator import parse_json_response

logger = logging.getLogger(__name__)

# Expand the bubble box so the crop usually includes the leader stub/endpoint.
DEFAULT_CROP_PADDING_FACTOR = 3.0
DEFAULT_MIN_CROP_NORM = 80.0  # minimum crop size on the 0–1000 scale


class CalloutVerificationResult(BaseModel):
    """Parsed verifier response (valid confirmation or rejection)."""

    valid: bool
    reason: Optional[str] = None
    bubble_number: Optional[str] = None
    leader_visible: Optional[bool] = None
    endpoint_visible: Optional[bool] = None
    bbox_surrounds_bubble: Optional[bool] = None
    confidence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _shape(self) -> "CalloutVerificationResult":
        if self.valid:
            if not self.bubble_number:
                raise ValueError("valid=true requires bubble_number")
            if self.leader_visible is None or self.endpoint_visible is None:
                raise ValueError("valid=true requires leader_visible and endpoint_visible")
            if self.bbox_surrounds_bubble is False:
                raise ValueError("bbox_surrounds_bubble=false must be reported as valid=false")
            if self.confidence_score is None:
                raise ValueError("valid=true requires confidence_score")
        else:
            if not self.reason:
                object.__setattr__(self, "reason", "Verification rejected without a reason")
        return self


def build_verification_prompt(callout: Callout) -> str:
    box = callout.bubble_bbox
    bbox_text = (
        f"{{xmin={box.xmin:.1f}, ymin={box.ymin:.1f}, "
        f"xmax={box.xmax:.1f}, ymax={box.ymax:.1f}}}"
    )
    return CALLOUT_VERIFICATION_PROMPT.format(
        proposed_bubble_number=callout.bubble_number,
        proposed_bubble_bbox=bbox_text,
    )


def page_norm_to_pixel(value: float, page_size: int) -> float:
    return (float(value) / NORMALIZED_MAX) * page_size


def crop_around_bubble(
    image: Image.Image,
    bubble_bbox: BoundingBox,
    *,
    padding_factor: float = DEFAULT_CROP_PADDING_FACTOR,
    min_crop_norm: float = DEFAULT_MIN_CROP_NORM,
) -> Image.Image:
    """Crop a padded region around ``bubble_bbox`` (full-page 0–1000 coords)."""
    page_w, page_h = image.size
    xmin = page_norm_to_pixel(bubble_bbox.xmin, page_w)
    ymin = page_norm_to_pixel(bubble_bbox.ymin, page_h)
    xmax = page_norm_to_pixel(bubble_bbox.xmax, page_w)
    ymax = page_norm_to_pixel(bubble_bbox.ymax, page_h)

    cx = (xmin + xmax) / 2.0
    cy = (ymin + ymax) / 2.0
    half_w = max((xmax - xmin) / 2.0 * padding_factor, page_norm_to_pixel(min_crop_norm / 2.0, page_w))
    half_h = max((ymax - ymin) / 2.0 * padding_factor, page_norm_to_pixel(min_crop_norm / 2.0, page_h))

    x0 = int(max(0, cx - half_w))
    y0 = int(max(0, cy - half_h))
    x1 = int(min(page_w, cx + half_w))
    y1 = int(min(page_h, cy + half_h))
    if x1 <= x0:
        x1 = min(page_w, x0 + 1)
    if y1 <= y0:
        y1 = min(page_h, y0 + 1)
    return image.crop((x0, y0, x1, y1))


def parse_verification_response(raw: dict[str, Any]) -> CalloutVerificationResult:
    data = dict(raw)
    # Treat a failed bbox check as an invalid detection (per verification rules).
    if data.get("valid") is True and data.get("bbox_surrounds_bubble") is False:
        data = {
            "valid": False,
            "reason": data.get("reason")
            or "Proposed bounding box does not surround the bubble",
        }
    return CalloutVerificationResult(**data)


def apply_verification_to_callout(
    callout: Callout,
    result: CalloutVerificationResult,
) -> Optional[Callout]:
    """Return an updated Callout, or None if verification rejected it."""
    if not result.valid:
        return None

    leader_visible = bool(result.leader_visible)
    endpoint_visible = bool(result.endpoint_visible)

    if leader_visible and endpoint_visible and callout.leader_endpoint is not None:
        leader_status = "clear"
        endpoint = callout.leader_endpoint
    elif leader_visible and not endpoint_visible:
        leader_status = "unclear"
        endpoint = None
    elif not leader_visible:
        leader_status = "missing"
        endpoint = None
    else:
        # Leader + endpoint claimed visible but original detection had no endpoint.
        leader_status = "unclear"
        endpoint = None

    return Callout(
        bubble_number=str(result.bubble_number),
        location_description=callout.location_description if leader_visible else None,
        bubble_bbox=callout.bubble_bbox,
        confidence_score=float(result.confidence_score),
        leader_endpoint=endpoint,
        leader_line_status=leader_status,
    )


def verify_callouts(
    client: Any,
    image: Image.Image,
    callouts: list[Callout],
) -> tuple[list[Callout], list[str]]:
    """Run second-pass verification on each callout. Drops invalid detections.

    ``client`` must expose ``detect_callouts(image, prompt) -> str`` (ClaudeVisionClient).
    """
    kept: list[Callout] = []
    warnings: list[str] = []

    for callout in callouts:
        try:
            crop = crop_around_bubble(image, callout.bubble_bbox)
            prompt = build_verification_prompt(callout)
            raw_text = client.detect_callouts(crop, prompt)
            parsed = parse_json_response(raw_text)
            result = parse_verification_response(parsed)
        except (ClaudeAPIError, InvalidExtractionError, ValidationError, TypeError, ValueError) as exc:
            warnings.append(
                f"Callout verification failed for bubble {callout.bubble_number!r}; "
                f"keeping original detection ({exc})"
            )
            logger.warning(
                "Verification failed for bubble %s: %s", callout.bubble_number, exc
            )
            kept.append(callout)
            continue

        if not result.valid:
            reason = result.reason or "unspecified"
            warnings.append(
                f"Rejected callout bubble {callout.bubble_number!r} after verification: {reason}"
            )
            continue

        updated = apply_verification_to_callout(callout, result)
        if updated is None:
            warnings.append(
                f"Rejected callout bubble {callout.bubble_number!r} after verification"
            )
            continue

        if updated.bubble_number != callout.bubble_number:
            warnings.append(
                f"Verification corrected bubble number "
                f"{callout.bubble_number!r} -> {updated.bubble_number!r}"
            )
        kept.append(updated)

    return kept, warnings
