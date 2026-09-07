"""Crop ↔ full-page coordinate remapping for callout bounding boxes.

Vision models always report coordinates normalized 0–1000 relative to the
*image they were shown*. When that image is a crop (drawing-region isolation
or an internal tile), callers must convert back to full-page 0–1000 before
anything reaches the frontend.
"""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Optional, Union

from .models import BoundingBox, Callout, LeaderEndpoint
from .utils import NORMALIZED_MAX, clamp


def remap_norm_coord_from_crop(
    value: float,
    *,
    crop_origin: float,
    crop_size: float,
    full_page_size: float,
) -> float:
    """Map one axis from crop-relative 0–1000 to full-page 0–1000.

    Parameters use pixel space for the crop placement on the page::

        page_pixel = crop_origin + (value / 1000) * crop_size
        page_norm  = page_pixel / full_page_size * 1000
    """
    if crop_size <= 0 or full_page_size <= 0:
        raise ValueError("crop_size and full_page_size must be positive")
    page_pixel = float(crop_origin) + (float(value) / NORMALIZED_MAX) * float(crop_size)
    return clamp((page_pixel / float(full_page_size)) * NORMALIZED_MAX)


def remap_bbox_from_crop(
    bbox: Union[BoundingBox, Mapping[str, Any]],
    *,
    crop_x: float,
    crop_y: float,
    crop_width: float,
    crop_height: float,
    full_page_width: float,
    full_page_height: float,
) -> dict[str, float]:
    """Convert a crop-relative ``bubble_bbox`` to full-page normalized 0–1000."""
    if isinstance(bbox, BoundingBox):
        xmin, ymin, xmax, ymax = bbox.xmin, bbox.ymin, bbox.xmax, bbox.ymax
    else:
        xmin = float(bbox["xmin"])
        ymin = float(bbox["ymin"])
        xmax = float(bbox["xmax"])
        ymax = float(bbox["ymax"])

    return {
        "xmin": remap_norm_coord_from_crop(
            xmin, crop_origin=crop_x, crop_size=crop_width, full_page_size=full_page_width
        ),
        "ymin": remap_norm_coord_from_crop(
            ymin, crop_origin=crop_y, crop_size=crop_height, full_page_size=full_page_height
        ),
        "xmax": remap_norm_coord_from_crop(
            xmax, crop_origin=crop_x, crop_size=crop_width, full_page_size=full_page_width
        ),
        "ymax": remap_norm_coord_from_crop(
            ymax, crop_origin=crop_y, crop_size=crop_height, full_page_size=full_page_height
        ),
    }


def crop_pixels_from_normalized_region(
    region: Any,
    full_page_width: int,
    full_page_height: int,
) -> tuple[float, float, float, float]:
    """Convert a page-normalized region (0–1000) into pixel crop placement.

    Returns ``(crop_x, crop_y, crop_width, crop_height)`` in pixels.
    """
    xmin = float(region.xmin)
    ymin = float(region.ymin)
    xmax = float(region.xmax)
    ymax = float(region.ymax)
    crop_x = (xmin / NORMALIZED_MAX) * full_page_width
    crop_y = (ymin / NORMALIZED_MAX) * full_page_height
    crop_width = ((xmax - xmin) / NORMALIZED_MAX) * full_page_width
    crop_height = ((ymax - ymin) / NORMALIZED_MAX) * full_page_height
    return crop_x, crop_y, crop_width, crop_height


def remap_callout_dict_from_crop(
    callout: MutableMapping[str, Any],
    *,
    crop_x: float,
    crop_y: float,
    crop_width: float,
    crop_height: float,
    full_page_width: float,
    full_page_height: float,
) -> MutableMapping[str, Any]:
    """In-place remap of a dumped callout dict to full-page coordinates.

    Prefers ``bubble_bbox`` (current schema); also remaps legacy
    ``bounding_box`` and optional ``leader_endpoint``. After remapping,
    ``bounding_box`` is set equal to ``bubble_bbox`` so downstream
    consumers that still read ``bounding_box`` stay aligned — both are
    full-page. The frontend never sees crop-relative values.
    """
    raw_bbox = callout.get("bubble_bbox") or callout.get("bounding_box")
    if isinstance(raw_bbox, dict):
        remapped = remap_bbox_from_crop(
            raw_bbox,
            crop_x=crop_x,
            crop_y=crop_y,
            crop_width=crop_width,
            crop_height=crop_height,
            full_page_width=full_page_width,
            full_page_height=full_page_height,
        )
        callout["bubble_bbox"] = remapped
        callout["bounding_box"] = dict(remapped)

    endpoint = callout.get("leader_endpoint")
    if isinstance(endpoint, dict) and "x" in endpoint and "y" in endpoint:
        callout["leader_endpoint"] = {
            "x": remap_norm_coord_from_crop(
                float(endpoint["x"]),
                crop_origin=crop_x,
                crop_size=crop_width,
                full_page_size=full_page_width,
            ),
            "y": remap_norm_coord_from_crop(
                float(endpoint["y"]),
                crop_origin=crop_y,
                crop_size=crop_height,
                full_page_size=full_page_height,
            ),
        }
    return callout


def remap_callout_model_from_crop(
    callout: Callout,
    *,
    crop_x: float,
    crop_y: float,
    crop_width: float,
    crop_height: float,
    full_page_width: float,
    full_page_height: float,
) -> Callout:
    """Return a new Callout with full-page normalized coordinates."""
    remapped_box = BoundingBox(
        **remap_bbox_from_crop(
            callout.bubble_bbox,
            crop_x=crop_x,
            crop_y=crop_y,
            crop_width=crop_width,
            crop_height=crop_height,
            full_page_width=full_page_width,
            full_page_height=full_page_height,
        )
    )
    remapped_endpoint: Optional[LeaderEndpoint] = None
    if callout.leader_endpoint is not None:
        remapped_endpoint = LeaderEndpoint(
            x=remap_norm_coord_from_crop(
                callout.leader_endpoint.x,
                crop_origin=crop_x,
                crop_size=crop_width,
                full_page_size=full_page_width,
            ),
            y=remap_norm_coord_from_crop(
                callout.leader_endpoint.y,
                crop_origin=crop_y,
                crop_size=crop_height,
                full_page_size=full_page_height,
            ),
        )
    return Callout(
        bubble_number=callout.bubble_number,
        location_description=callout.location_description,
        bubble_bbox=remapped_box,
        confidence_score=callout.confidence_score,
        leader_endpoint=remapped_endpoint,
        leader_line_status=callout.leader_line_status,
    )
