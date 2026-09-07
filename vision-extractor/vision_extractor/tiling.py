"""Overlapping image tiles for large-drawing callout detection.

Tiles are cropped from the full page, sent to the vision model independently,
then detections are remapped into full-page 0–1000 coordinates and deduplicated.
BOM extraction never uses this module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional, Sequence

from PIL import Image

from .coordinates import remap_callout_model_from_crop
from .models import BoundingBox, Callout

logger = logging.getLogger(__name__)

# IoU at or above this for the same bubble_number => strong overlap / duplicate.
DEFAULT_DEDUPE_IOU = 0.5


@dataclass(frozen=True)
class Tile:
    """One overlapping crop of the full drawing (pixel space, exclusive max)."""

    row: int
    col: int
    x0: int
    y0: int
    x1: int
    y1: int
    image: Image.Image

    @property
    def width(self) -> int:
        return self.x1 - self.x0

    @property
    def height(self) -> int:
        return self.y1 - self.y0

    @property
    def label(self) -> str:
        return f"tile[r{self.row}c{self.col}]"


def split_into_tiles(
    image: Image.Image,
    grid_rows: int = 2,
    grid_cols: int = 2,
    overlap_fraction: float = 0.12,
) -> list[Tile]:
    """Split ``image`` into a ``grid_rows`` x ``grid_cols`` grid with overlap.

    ``overlap_fraction`` is relative to each non-overlapping cell (default 12%,
    within the 10–15% range). Edge tiles are clamped to the image bounds.
    """
    if grid_rows < 1 or grid_cols < 1:
        raise ValueError(f"grid must be at least 1x1, got {grid_rows}x{grid_cols}")
    if not 0.0 <= overlap_fraction < 1.0:
        raise ValueError(f"overlap_fraction must be in [0, 1), got {overlap_fraction}")

    page_w, page_h = image.size
    if page_w <= 0 or page_h <= 0:
        raise ValueError(f"image dimensions must be positive, got {page_w}x{page_h}")

    cell_w = page_w / grid_cols
    cell_h = page_h / grid_rows
    overlap_x = cell_w * overlap_fraction
    overlap_y = cell_h * overlap_fraction

    tiles: list[Tile] = []
    for row in range(grid_rows):
        for col in range(grid_cols):
            x0 = int(max(0, col * cell_w - (overlap_x / 2 if col > 0 else 0)))
            y0 = int(max(0, row * cell_h - (overlap_y / 2 if row > 0 else 0)))
            x1 = int(
                min(
                    page_w,
                    (col + 1) * cell_w + (overlap_x / 2 if col < grid_cols - 1 else 0),
                )
            )
            y1 = int(
                min(
                    page_h,
                    (row + 1) * cell_h + (overlap_y / 2 if row < grid_rows - 1 else 0),
                )
            )

            # Guarantee at least a 1px crop even on tiny images.
            if x1 <= x0:
                x1 = min(page_w, x0 + 1)
            if y1 <= y0:
                y1 = min(page_h, y0 + 1)

            crop = image.crop((x0, y0, x1, y1))
            tiles.append(Tile(row=row, col=col, x0=x0, y0=y0, x1=x1, y1=y1, image=crop))

    logger.info(
        "Split image %dx%d into %d tiles (%dx%d grid, overlap=%.0f%%)",
        page_w,
        page_h,
        len(tiles),
        grid_rows,
        grid_cols,
        overlap_fraction * 100,
    )
    return tiles


def tile_norm_to_page_norm(
    value: float,
    tile_origin: int,
    tile_size: int,
    page_size: int,
) -> float:
    """Map one axis from tile-relative 0–1000 to full-page 0–1000."""
    from .coordinates import remap_norm_coord_from_crop

    return remap_norm_coord_from_crop(
        value,
        crop_origin=tile_origin,
        crop_size=tile_size,
        full_page_size=page_size,
    )


def remap_callout_to_page(
    callout: Callout,
    tile: Tile,
    page_width: int,
    page_height: int,
) -> Callout:
    """Convert a tile-local Callout into full-page normalized coordinates."""
    return remap_callout_model_from_crop(
        callout,
        crop_x=tile.x0,
        crop_y=tile.y0,
        crop_width=tile.width,
        crop_height=tile.height,
        full_page_width=page_width,
        full_page_height=page_height,
    )


def bbox_iou(a: BoundingBox, b: BoundingBox) -> float:
    """Intersection-over-union for two normalized bounding boxes."""
    inter_xmin = max(a.xmin, b.xmin)
    inter_ymin = max(a.ymin, b.ymin)
    inter_xmax = min(a.xmax, b.xmax)
    inter_ymax = min(a.ymax, b.ymax)

    inter_w = max(0.0, inter_xmax - inter_xmin)
    inter_h = max(0.0, inter_ymax - inter_ymin)
    inter_area = inter_w * inter_h
    if inter_area <= 0:
        return 0.0

    area_a = max(0.0, a.xmax - a.xmin) * max(0.0, a.ymax - a.ymin)
    area_b = max(0.0, b.xmax - b.xmin) * max(0.0, b.ymax - b.ymin)
    union = area_a + area_b - inter_area
    if union <= 0:
        return 0.0
    return inter_area / union


def deduplicate_callouts(
    callouts: Sequence[Callout],
    iou_threshold: float = DEFAULT_DEDUPE_IOU,
) -> tuple[list[Callout], list[str]]:
    """Keep the highest-confidence callout when same bubble# boxes overlap strongly.

    Callouts with the same bubble number but low IoU are kept (both are valid
    candidates for downstream duplicate warnings). Different bubble numbers
    are never merged.
    """
    warnings: list[str] = []
    # Process highest confidence first so the survivor is stable.
    ordered = sorted(callouts, key=lambda c: c.confidence_score, reverse=True)
    kept: list[Callout] = []

    for candidate in ordered:
        duplicate_of: Optional[Callout] = None
        for existing in kept:
            if existing.bubble_number != candidate.bubble_number:
                continue
            if bbox_iou(existing.bubble_bbox, candidate.bubble_bbox) >= iou_threshold:
                duplicate_of = existing
                break
        if duplicate_of is not None:
            warnings.append(
                f"Deduplicated overlapping callout bubble {candidate.bubble_number!r}: "
                f"kept confidence={duplicate_of.confidence_score:.2f}, "
                f"dropped confidence={candidate.confidence_score:.2f} "
                f"(IoU>={iou_threshold})"
            )
            continue
        kept.append(candidate)

    # Stable reading order for downstream consumers.
    kept.sort(
        key=lambda c: (
            c.bubble_bbox.ymin,
            c.bubble_bbox.xmin,
            c.bubble_number,
        )
    )
    return kept, warnings


def parse_grid_size(value: str, default: tuple[int, int] = (2, 2)) -> tuple[int, int]:
    """Parse ``\"2x2\"`` / ``\"3x3\"`` style grid specs into (rows, cols)."""
    raw = (value or "").strip().lower().replace(" ", "")
    if not raw:
        return default
    if "x" not in raw:
        raise ValueError(f"Invalid grid size {value!r}; expected like '2x2' or '3x3'")
    left, right = raw.split("x", 1)
    rows, cols = int(left), int(right)
    if rows < 1 or cols < 1:
        raise ValueError(f"grid dimensions must be >= 1, got {rows}x{cols}")
    return rows, cols
