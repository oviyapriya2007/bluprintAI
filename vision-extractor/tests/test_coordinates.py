"""Tests for crop → full-page callout coordinate remapping."""

from types import SimpleNamespace

from vision_extractor.coordinates import (
    crop_pixels_from_normalized_region,
    remap_bbox_from_crop,
    remap_callout_dict_from_crop,
    remap_norm_coord_from_crop,
)
from vision_extractor.models import BoundingBox, Callout
from vision_extractor.tiling import remap_callout_to_page, split_into_tiles
from PIL import Image


def test_remap_norm_coord_from_crop_right_half():
    # Crop starts at x=500 of a 1000px page, width 500.
    assert remap_norm_coord_from_crop(
        0, crop_origin=500, crop_size=500, full_page_size=1000
    ) == 500
    assert remap_norm_coord_from_crop(
        1000, crop_origin=500, crop_size=500, full_page_size=1000
    ) == 1000
    assert remap_norm_coord_from_crop(
        500, crop_origin=500, crop_size=500, full_page_size=1000
    ) == 750


def test_remap_bbox_from_crop_uses_named_crop_params():
    remapped = remap_bbox_from_crop(
        {"xmin": 0, "ymin": 0, "xmax": 200, "ymax": 200},
        crop_x=500,
        crop_y=500,
        crop_width=500,
        crop_height=500,
        full_page_width=1000,
        full_page_height=1000,
    )
    assert remapped["xmin"] == 500
    assert remapped["ymin"] == 500
    assert remapped["xmax"] == 600
    assert remapped["ymax"] == 600


def test_remap_callout_dict_rewrites_bubble_bbox_not_only_bounding_box():
    callout = {
        "bubble_number": "1",
        "bubble_bbox": {"xmin": 0, "ymin": 0, "xmax": 100, "ymax": 100},
        "confidence_score": 0.9,
    }
    remap_callout_dict_from_crop(
        callout,
        crop_x=100,
        crop_y=200,
        crop_width=400,
        crop_height=400,
        full_page_width=1000,
        full_page_height=1000,
    )
    # crop-local 0 -> page pixel 100 -> norm 100
    assert callout["bubble_bbox"]["xmin"] == 100
    assert callout["bubble_bbox"]["ymin"] == 200
    # crop-local 100 -> pixel 100+40=140 -> norm 140
    assert callout["bubble_bbox"]["xmax"] == 140
    assert callout["bubble_bbox"]["ymax"] == 240
    # Frontend/legacy alias must also be full-page, not crop-relative.
    assert callout["bounding_box"] == callout["bubble_bbox"]


def test_crop_pixels_from_normalized_region():
    region = SimpleNamespace(xmin=0, ymin=0, xmax=500, ymax=500)
    crop_x, crop_y, crop_w, crop_h = crop_pixels_from_normalized_region(region, 2000, 1000)
    assert crop_x == 0
    assert crop_y == 0
    assert crop_w == 1000
    assert crop_h == 500


def test_tiling_remap_uses_shared_coordinate_helper():
    image = Image.new("RGB", (1000, 1000), color=(255, 255, 255))
    tiles = split_into_tiles(image, grid_rows=2, grid_cols=2, overlap_fraction=0.0)
    tile = next(t for t in tiles if t.row == 1 and t.col == 1)
    local = Callout(
        bubble_number="1",
        bubble_bbox=BoundingBox(xmin=0, ymin=0, xmax=100, ymax=100),
        confidence_score=0.9,
        leader_line_status="missing",
    )
    page = remap_callout_to_page(local, tile, page_width=1000, page_height=1000)
    assert page.bubble_bbox.xmin == 500
    assert page.bubble_bbox.ymin == 500
