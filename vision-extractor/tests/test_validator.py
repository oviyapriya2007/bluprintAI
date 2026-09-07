import pytest

from vision_extractor.exceptions import InvalidExtractionError
from vision_extractor.validator import (
    build_components,
    parse_json_response,
    validate_bom_items,
    validate_callouts,
)


def test_parse_json_response_plain_json():
    parsed = parse_json_response('{"bom_items": []}')
    assert parsed == {"bom_items": []}


def test_parse_json_response_strips_markdown_fences():
    text = '```json\n{"bom_items": []}\n```'
    parsed = parse_json_response(text)
    assert parsed == {"bom_items": []}


def test_parse_json_response_rejects_empty():
    with pytest.raises(InvalidExtractionError):
        parse_json_response("")


def test_parse_json_response_rejects_malformed_json():
    with pytest.raises(InvalidExtractionError):
        parse_json_response("{not valid json")


def test_parse_json_response_rejects_non_object():
    with pytest.raises(InvalidExtractionError):
        parse_json_response("[1, 2, 3]")


def test_validate_bom_items_happy_path():
    raw = [
        {"item_number": "1", "part_name": "Bolt", "quantity": 4, "confidence_score": 0.9},
    ]
    items, warnings = validate_bom_items(raw, low_confidence_threshold=0.7)
    assert len(items) == 1
    assert items[0].item_number == "1"
    assert warnings == []


def test_validate_bom_items_skips_invalid_row_without_crashing():
    raw = [
        {"item_number": "1", "confidence_score": 0.9},
        {"part_name": "Missing item_number field", "confidence_score": 0.9},
    ]
    items, warnings = validate_bom_items(raw, low_confidence_threshold=0.7)
    assert len(items) == 1
    assert any("Skipped invalid BOM row" in w for w in warnings)


def test_validate_bom_items_flags_low_confidence():
    raw = [{"item_number": "1", "confidence_score": 0.3}]
    items, warnings = validate_bom_items(raw, low_confidence_threshold=0.7)
    assert len(items) == 1
    assert any("Low confidence" in w for w in warnings)


def test_validate_bom_items_clamps_out_of_range_confidence():
    raw = [{"item_number": "1", "confidence_score": 5.0}]
    items, warnings = validate_bom_items(raw, low_confidence_threshold=0.7)
    assert items[0].confidence_score == 1.0


def test_validate_callouts_happy_path():
    raw = [
        {
            "bubble_number": "3",
            "bounding_box": {"xmin": 185, "ymin": 412, "xmax": 230, "ymax": 458},
            "confidence_score": 0.95,
        }
    ]
    callouts, warnings = validate_callouts(raw, low_confidence_threshold=0.7)
    assert len(callouts) == 1
    assert callouts[0].bubble_number == "3"
    assert warnings == []


def test_validate_callouts_skips_missing_bounding_box():
    raw = [{"bubble_number": "3", "confidence_score": 0.9}]
    callouts, warnings = validate_callouts(raw, low_confidence_threshold=0.7)
    assert callouts == []
    assert any("Skipped invalid callout" in w for w in warnings)


def test_validate_callouts_flags_duplicate_bubble_numbers():
    raw = [
        {
            "bubble_number": "3",
            "bounding_box": {"xmin": 0, "ymin": 0, "xmax": 10, "ymax": 10},
            "confidence_score": 0.9,
        },
        {
            "bubble_number": "3",
            "bounding_box": {"xmin": 20, "ymin": 20, "xmax": 30, "ymax": 30},
            "confidence_score": 0.9,
        },
    ]
    callouts, warnings = validate_callouts(raw, low_confidence_threshold=0.7)
    # both are preserved, not silently dropped
    assert len(callouts) == 2
    assert any("Duplicate callout bubble number" in w for w in warnings)


def test_validate_callouts_normalizes_pixel_coordinates():
    # Values clearly outside the 0-1000 normalized range are treated as raw
    # pixel coordinates and converted using the supplied image dimensions.
    raw = [
        {
            "bubble_number": "1",
            "bounding_box": {"xmin": 400, "ymin": 800, "xmax": 1200, "ymax": 1600},
            "confidence_score": 0.9,
        }
    ]
    callouts, _ = validate_callouts(
        raw, low_confidence_threshold=0.7, image_width=4000, image_height=4000
    )
    box = callouts[0].bounding_box
    assert box.xmin == 100.0
    assert box.ymin == 200.0
    assert box.xmax == 300.0
    assert box.ymax == 400.0


def test_validate_callouts_trusts_in_range_coordinates_as_already_normalized():
    # Gemini is prompted to return normalized 0-1000 coordinates directly;
    # in-range values should pass through unchanged even when image
    # dimensions are supplied, rather than being reinterpreted as pixels.
    raw = [
        {
            "bubble_number": "1",
            "bounding_box": {"xmin": 100, "ymin": 200, "xmax": 300, "ymax": 400},
            "confidence_score": 0.9,
        }
    ]
    callouts, _ = validate_callouts(
        raw, low_confidence_threshold=0.7, image_width=2000, image_height=1000
    )
    box = callouts[0].bounding_box
    assert box.xmin == 100.0
    assert box.ymin == 200.0
    assert box.xmax == 300.0
    assert box.ymax == 400.0


def test_build_components_matches_on_shared_number():
    from vision_extractor.models import BOMItem, BoundingBox, Callout

    bom_items = [BOMItem(item_number="3", part_name="Bolt", quantity=6, confidence_score=0.9)]
    callouts = [
        Callout(
            bubble_number="3",
            bounding_box=BoundingBox(xmin=185, ymin=412, xmax=230, ymax=458),
            confidence_score=0.95,
        )
    ]
    components = build_components(bom_items, callouts)
    assert len(components) == 1
    assert components[0].id == "cmp_003"
    assert components[0].part_name == "Bolt"


def test_build_components_skips_unmatched_items():
    from vision_extractor.models import BOMItem

    bom_items = [BOMItem(item_number="99", confidence_score=0.9)]
    components = build_components(bom_items, [])
    assert components == []
