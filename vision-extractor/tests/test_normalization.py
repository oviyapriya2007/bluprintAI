import pytest

from vision_extractor.utils import (
    clamp,
    is_already_normalized,
    normalize_bbox_pixels,
    normalize_coordinate,
)


def test_normalize_coordinate_basic():
    # pixel 500 of a 1000px-wide image -> 500 normalized
    assert normalize_coordinate(500, 1000) == 500.0
    # pixel 100 of a 200px-wide image -> 500 normalized
    assert normalize_coordinate(100, 200) == 500.0


def test_normalize_coordinate_clamps_to_max():
    # a coordinate beyond the image dimension should clamp to 1000
    assert normalize_coordinate(2000, 1000) == 1000.0


def test_normalize_coordinate_clamps_to_min():
    assert normalize_coordinate(-50, 1000) == 0.0


def test_normalize_coordinate_rejects_invalid_dimension():
    with pytest.raises(ValueError):
        normalize_coordinate(10, 0)


def test_normalize_bbox_pixels():
    result = normalize_bbox_pixels(
        xmin=100, ymin=200, xmax=300, ymax=400, image_width=1000, image_height=800
    )
    assert result["xmin"] == 100.0
    assert result["ymin"] == 250.0
    assert result["xmax"] == 300.0
    assert result["ymax"] == 500.0


def test_clamp():
    assert clamp(-10) == 0.0
    assert clamp(5000) == 1000.0
    assert clamp(500) == 500.0


def test_is_already_normalized():
    assert is_already_normalized(0, 0, 1000, 1000) is True
    assert is_already_normalized(185, 412, 230, 458) is True
    assert is_already_normalized(0, 0, 1500, 100) is False
