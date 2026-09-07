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
        {
            "item_number": "1",
            "part_number": "HB-M8-001",
            "description": "Hexagon Head Bolt M8 x 25",
            "material": "Carbon Steel",
            "quantity": 4,
            "confidence_score": 0.98,
        },
    ]
    items, warnings = validate_bom_items(raw, low_confidence_threshold=0.7)
    assert len(items) == 1
    assert items[0].item_number == "1"
    assert items[0].description == "Hexagon Head Bolt M8 x 25"
    assert items[0].material_specification == "Carbon Steel"
    assert items[0].part_name is None  # vision must not invent part_name
    assert warnings == []


def test_validate_bom_items_discards_invented_part_name():
    raw = [
        {
            "item_number": "1",
            "part_name": "Invented Fancy Bolt",
            "description": "Hexagon Head Bolt M8 x 25",
            "confidence_score": 0.9,
        },
    ]
    items, _ = validate_bom_items(raw, low_confidence_threshold=0.7)
    assert items[0].part_name is None
    assert items[0].description == "Hexagon Head Bolt M8 x 25"


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
            "bubble_number": "1",
            "bubble_bbox": {"xmin": 100, "ymin": 80, "xmax": 140, "ymax": 120},
            "confidence_score": 0.96,
        }
    ]
    callouts, warnings = validate_callouts(raw, low_confidence_threshold=0.7)
    assert len(callouts) == 1
    assert callouts[0].bubble_number == "1"
    assert callouts[0].bubble_bbox.xmin == 100
    assert callouts[0].leader_endpoint is None
    assert callouts[0].leader_line_status == "missing"
    dumped = callouts[0].model_dump()
    assert "bubble_bbox" in dumped
    assert "bounding_box" not in dumped
    assert warnings == []


def test_validate_callouts_accepts_legacy_bounding_box():
    raw = [
        {
            "bubble_number": "3",
            "bounding_box": {"xmin": 185, "ymin": 412, "xmax": 230, "ymax": 458},
            "leader_line_status": "clear",
            "leader_endpoint": {"x": 200, "y": 500},
            "confidence_score": 0.95,
        }
    ]
    callouts, warnings = validate_callouts(raw, low_confidence_threshold=0.7)
    assert len(callouts) == 1
    assert callouts[0].bubble_bbox.xmax == 230
    assert warnings == []


def test_validate_callouts_unclear_leader_clears_endpoint():
    raw = [
        {
            "bubble_number": "7",
            "bubble_bbox": {"xmin": 520, "ymin": 220, "xmax": 565, "ymax": 265},
            "leader_endpoint": {"x": 600, "y": 300},
            "leader_line_status": "unclear",
            "location_description": None,
            "confidence_score": 0.88,
        }
    ]
    callouts, warnings = validate_callouts(raw, low_confidence_threshold=0.7)
    assert len(callouts) == 1
    assert callouts[0].leader_endpoint is None
    assert callouts[0].leader_line_status == "unclear"
    assert any("Unclear leader line" in w for w in warnings)


def test_validate_callouts_missing_leader_status():
    raw = [
        {
            "bubble_number": "9",
            "bubble_bbox": {"xmin": 100, "ymin": 100, "xmax": 140, "ymax": 140},
            "leader_endpoint": None,
            "leader_line_status": "missing",
            "confidence_score": 0.86,
        }
    ]
    callouts, warnings = validate_callouts(raw, low_confidence_threshold=0.7)
    assert len(callouts) == 1
    assert callouts[0].leader_endpoint is None
    assert callouts[0].leader_line_status == "missing"
    assert any("Missing endpoint" in w for w in warnings)


def test_validate_callouts_clear_without_endpoint_downgrades():
    raw = [
        {
            "bubble_number": "2",
            "bubble_bbox": {"xmin": 10, "ymin": 10, "xmax": 40, "ymax": 40},
            "leader_endpoint": None,
            "leader_line_status": "clear",
            "confidence_score": 0.9,
        }
    ]
    callouts, warnings = validate_callouts(raw, low_confidence_threshold=0.7)
    assert len(callouts) == 1
    assert callouts[0].leader_line_status == "missing"
    assert callouts[0].leader_endpoint is None
    assert any("Missing endpoint" in w for w in warnings)


def test_validate_callouts_skips_below_min_confidence():
    raw = [
        {
            "bubble_number": "3",
            "bubble_bbox": {"xmin": 0, "ymin": 0, "xmax": 10, "ymax": 10},
            "confidence_score": 0.84,
        }
    ]
    callouts, warnings = validate_callouts(raw, low_confidence_threshold=0.7)
    assert callouts == []
    assert any("below minimum" in w for w in warnings)


def test_validate_callouts_malformed_bbox_warning():
    raw = [{"bubble_number": "3", "confidence_score": 0.9}]
    callouts, warnings = validate_callouts(raw, low_confidence_threshold=0.7)
    assert callouts == []
    assert any("Malformed bubble_bbox" in w for w in warnings)


def test_validate_callouts_flags_duplicate_bubble_numbers():
    raw = [
        {
            "bubble_number": "3",
            "bubble_bbox": {"xmin": 0, "ymin": 0, "xmax": 10, "ymax": 10},
            "leader_line_status": "clear",
            "leader_endpoint": {"x": 20, "y": 20},
            "confidence_score": 0.9,
        },
        {
            "bubble_number": "3",
            "bubble_bbox": {"xmin": 20, "ymin": 20, "xmax": 30, "ymax": 30},
            "leader_line_status": "clear",
            "leader_endpoint": {"x": 40, "y": 40},
            "confidence_score": 0.9,
        },
    ]
    callouts, warnings = validate_callouts(raw, low_confidence_threshold=0.7)
    assert len(callouts) == 2
    assert any("Duplicate bubble number" in w for w in warnings)


def test_validate_callouts_normalizes_pixel_coordinates():
    raw = [
        {
            "bubble_number": "1",
            "bubble_bbox": {"xmin": 400, "ymin": 800, "xmax": 1200, "ymax": 1600},
            "leader_line_status": "clear",
            "leader_endpoint": {"x": 1600, "y": 2000},
            "confidence_score": 0.9,
        }
    ]
    callouts, _ = validate_callouts(
        raw, low_confidence_threshold=0.7, image_width=4000, image_height=4000
    )
    box = callouts[0].bubble_bbox
    assert box.xmin == 100.0
    assert box.ymin == 200.0
    assert box.xmax == 300.0
    assert box.ymax == 400.0
    assert callouts[0].leader_endpoint.x == 400.0
    assert callouts[0].leader_endpoint.y == 500.0


def test_validate_callouts_trusts_in_range_coordinates_as_already_normalized():
    raw = [
        {
            "bubble_number": "1",
            "bubble_bbox": {"xmin": 100, "ymin": 200, "xmax": 300, "ymax": 400},
            "leader_line_status": "clear",
            "leader_endpoint": {"x": 350, "y": 450},
            "confidence_score": 0.9,
        }
    ]
    callouts, _ = validate_callouts(
        raw, low_confidence_threshold=0.7, image_width=2000, image_height=1000
    )
    box = callouts[0].bubble_bbox
    assert box.xmin == 100.0
    assert box.ymin == 200.0
    assert box.xmax == 300.0
    assert box.ymax == 400.0


def test_build_components_matches_on_shared_number():
    from vision_extractor.models import BOMItem, BoundingBox, Callout

    bom_items = [
        BOMItem(
            item_number="3",
            description="Hexagon Head Bolt M8 x 25",
            quantity=6,
            confidence_score=0.9,
        )
    ]
    callouts = [
        Callout(
            bubble_number="3",
            bubble_bbox=BoundingBox(xmin=185, ymin=412, xmax=230, ymax=458),
            confidence_score=0.95,
            leader_line_status="missing",
        )
    ]
    components, warnings = build_components(bom_items, callouts)
    assert len(components) == 1
    assert components[0].id == "cmp_003"
    assert components[0].part_name == "Hexagon Head Bolt M8 x 25"
    assert components[0].bubble_number == "3"
    assert components[0].bounding_box.xmin == 185
    assert warnings == []


def test_build_components_part_name_from_description_only():
    from vision_extractor.models import BOMItem, BoundingBox, Callout

    bom_items = [
        BOMItem(
            item_number="1",
            part_name="Invented Name",  # must be ignored
            description="Hexagon Head Bolt M8 x 25",
            confidence_score=0.9,
        )
    ]
    callouts = [
        Callout(
            bubble_number="1",
            bubble_bbox=BoundingBox(xmin=0, ymin=0, xmax=10, ymax=10),
            confidence_score=0.9,
            leader_line_status="missing",
        )
    ]
    components, _ = build_components(bom_items, callouts)
    assert components[0].part_name == "Hexagon Head Bolt M8 x 25"


def test_build_components_exact_match_only_no_fuzzy():
    from vision_extractor.models import BOMItem, BoundingBox, Callout

    bom_items = [BOMItem(item_number="03", description="Plate", confidence_score=0.9)]
    callouts = [
        Callout(
            bubble_number="3",
            bubble_bbox=BoundingBox(xmin=0, ymin=0, xmax=10, ymax=10),
            confidence_score=0.9,
            leader_line_status="missing",
        )
    ]
    components, warnings = build_components(bom_items, callouts)
    assert components == []
    assert any("No callout detected." in w for w in warnings)
    assert any("Callout 3 has no matching BOM row." in w for w in warnings)


def test_build_components_orphan_callout_warning():
    from vision_extractor.models import BoundingBox, Callout

    callouts = [
        Callout(
            bubble_number="7",
            bubble_bbox=BoundingBox(xmin=0, ymin=0, xmax=10, ymax=10),
            confidence_score=0.9,
            leader_line_status="missing",
        )
    ]
    components, warnings = build_components([], callouts)
    assert components == []
    assert "Callout 7 has no matching BOM row." in warnings


def test_build_components_orphan_bom_warning():
    from vision_extractor.models import BOMItem

    bom_items = [BOMItem(item_number="99", description="Orphan", confidence_score=0.9)]
    components, warnings = build_components(bom_items, [])
    assert components == []
    assert "BOM item 99: No callout detected." in warnings


def test_validate_bom_items_strips_guessed_name_fields():
    raw = [
        {
            "item_number": "1",
            "description": "Bolt",
            "inferred_part_name": "Guessed Bolt",
            "visual_component_name": "Visual Bolt",
            "guessed_component": "Nope",
            "confidence_score": 0.9,
        }
    ]
    items, _ = validate_bom_items(raw, low_confidence_threshold=0.7)
    dumped = items[0].model_dump()
    assert "inferred_part_name" not in dumped
    assert items[0].part_name is None
    assert items[0].description == "Bolt"
