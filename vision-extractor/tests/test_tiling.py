"""Unit tests for overlapping-tile callout helpers."""

from PIL import Image

from vision_extractor.models import BoundingBox, Callout, LeaderEndpoint
from vision_extractor.tiling import (
    bbox_iou,
    deduplicate_callouts,
    parse_grid_size,
    remap_callout_to_page,
    split_into_tiles,
    tile_norm_to_page_norm,
)


def _blank(width: int = 1000, height: int = 1000) -> Image.Image:
    return Image.new("RGB", (width, height), color=(255, 255, 255))


def test_parse_grid_size():
    assert parse_grid_size("2x2") == (2, 2)
    assert parse_grid_size("3x3") == (3, 3)
    assert parse_grid_size(" 2X3 ") == (2, 3)
    assert parse_grid_size("") == (2, 2)


def test_split_into_tiles_2x2_with_overlap():
    image = _blank(1000, 1000)
    tiles = split_into_tiles(image, grid_rows=2, grid_cols=2, overlap_fraction=0.12)
    assert len(tiles) == 4

    # Corner tile starts at origin and extends past the cell midline into overlap.
    top_left = next(t for t in tiles if t.row == 0 and t.col == 0)
    assert top_left.x0 == 0 and top_left.y0 == 0
    assert top_left.x1 > 500  # 500 + 0.12*500/2 = 530
    assert top_left.y1 > 500

    top_right = next(t for t in tiles if t.row == 0 and t.col == 1)
    assert top_right.x1 == 1000
    assert top_right.x0 < 500  # overlaps left tile
    # Overlap band between left and right tiles.
    assert top_left.x1 > top_right.x0


def test_split_into_tiles_3x3():
    image = _blank(900, 900)
    tiles = split_into_tiles(image, grid_rows=3, grid_cols=3, overlap_fraction=0.15)
    assert len(tiles) == 9
    assert all(t.width > 0 and t.height > 0 for t in tiles)


def test_tile_norm_to_page_norm_identity_for_full_page_tile():
    # A tile covering the whole page should leave coordinates unchanged.
    assert tile_norm_to_page_norm(250, tile_origin=0, tile_size=1000, page_size=1000) == 250
    assert tile_norm_to_page_norm(0, tile_origin=0, tile_size=1000, page_size=1000) == 0
    assert tile_norm_to_page_norm(1000, tile_origin=0, tile_size=1000, page_size=1000) == 1000


def test_tile_norm_to_page_norm_right_half_tile():
    # Tile covers pixels [500, 1000) of a 1000px page.
    # Tile-local 0 -> page 500 -> norm 500; tile-local 1000 -> page 1000 -> norm 1000.
    assert tile_norm_to_page_norm(0, tile_origin=500, tile_size=500, page_size=1000) == 500
    assert tile_norm_to_page_norm(1000, tile_origin=500, tile_size=500, page_size=1000) == 1000
    assert tile_norm_to_page_norm(500, tile_origin=500, tile_size=500, page_size=1000) == 750


def test_remap_callout_to_page():
    image = _blank(1000, 1000)
    tiles = split_into_tiles(image, grid_rows=2, grid_cols=2, overlap_fraction=0.0)
    # With 0 overlap, bottom-right tile is exactly [500,1000) x [500,1000).
    tile = next(t for t in tiles if t.row == 1 and t.col == 1)
    assert tile.x0 == 500 and tile.y0 == 500

    local = Callout(
        bubble_number="3",
        bubble_bbox=BoundingBox(xmin=0, ymin=0, xmax=200, ymax=200),
        confidence_score=0.9,
        leader_endpoint=LeaderEndpoint(x=400, y=400),
        leader_line_status="clear",
    )
    page = remap_callout_to_page(local, tile, page_width=1000, page_height=1000)
    assert page.bubble_bbox.xmin == 500
    assert page.bubble_bbox.ymin == 500
    assert page.bubble_bbox.xmax == 600
    assert page.bubble_bbox.ymax == 600
    assert page.leader_endpoint.x == 700
    assert page.leader_endpoint.y == 700


def test_bbox_iou_identical_is_one():
    box = BoundingBox(xmin=100, ymin=100, xmax=200, ymax=200)
    assert bbox_iou(box, box) == 1.0


def test_bbox_iou_disjoint_is_zero():
    a = BoundingBox(xmin=0, ymin=0, xmax=10, ymax=10)
    b = BoundingBox(xmin=20, ymin=20, xmax=30, ymax=30)
    assert bbox_iou(a, b) == 0.0


def test_deduplicate_keeps_highest_confidence_on_strong_overlap():
    high = Callout(
        bubble_number="3",
        bubble_bbox=BoundingBox(xmin=100, ymin=100, xmax=200, ymax=200),
        confidence_score=0.95,
        leader_line_status="missing",
    )
    low = Callout(
        bubble_number="3",
        bubble_bbox=BoundingBox(xmin=110, ymin=110, xmax=210, ymax=210),
        confidence_score=0.80,
        leader_line_status="missing",
    )
    kept, warnings = deduplicate_callouts([low, high], iou_threshold=0.5)
    assert len(kept) == 1
    assert kept[0].confidence_score == 0.95
    assert any("Deduplicated overlapping callout" in w for w in warnings)


def test_deduplicate_keeps_same_number_when_boxes_do_not_overlap():
    a = Callout(
        bubble_number="3",
        bubble_bbox=BoundingBox(xmin=0, ymin=0, xmax=50, ymax=50),
        confidence_score=0.9,
        leader_line_status="missing",
    )
    b = Callout(
        bubble_number="3",
        bubble_bbox=BoundingBox(xmin=500, ymin=500, xmax=550, ymax=550),
        confidence_score=0.85,
        leader_line_status="missing",
    )
    kept, warnings = deduplicate_callouts([a, b], iou_threshold=0.5)
    assert len(kept) == 2
    assert warnings == []


def test_deduplicate_never_merges_different_bubble_numbers():
    a = Callout(
        bubble_number="1",
        bubble_bbox=BoundingBox(xmin=100, ymin=100, xmax=200, ymax=200),
        confidence_score=0.9,
        leader_line_status="missing",
    )
    b = Callout(
        bubble_number="2",
        bubble_bbox=BoundingBox(xmin=100, ymin=100, xmax=200, ymax=200),
        confidence_score=0.9,
        leader_line_status="missing",
    )
    kept, warnings = deduplicate_callouts([a, b], iou_threshold=0.5)
    assert len(kept) == 2
    assert warnings == []
