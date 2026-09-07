import pytest
from pydantic import ValidationError

from vision_extractor.models import BOMItem, BoundingBox, Callout, ExtractedComponent, ExtractionResult


def test_bounding_box_valid():
    box = BoundingBox(xmin=185, ymin=412, xmax=230, ymax=458)
    assert box.xmin == 185
    assert box.xmax == 230


def test_bounding_box_rejects_out_of_range():
    with pytest.raises(ValidationError):
        BoundingBox(xmin=-5, ymin=0, xmax=100, ymax=100)
    with pytest.raises(ValidationError):
        BoundingBox(xmin=0, ymin=0, xmax=1200, ymax=100)


def test_bounding_box_rejects_inverted_ordering():
    with pytest.raises(ValidationError):
        BoundingBox(xmin=200, ymin=0, xmax=100, ymax=100)
    with pytest.raises(ValidationError):
        BoundingBox(xmin=0, ymin=200, xmax=100, ymax=100)


def test_bom_item_optional_fields_default_none():
    item = BOMItem(item_number="1", confidence_score=0.9)
    assert item.part_number is None
    assert item.part_name is None
    assert item.quantity is None


def test_bom_item_rejects_negative_quantity():
    with pytest.raises(ValidationError):
        BOMItem(item_number="1", quantity=-3, confidence_score=0.9)


def test_bom_item_rejects_confidence_out_of_range():
    with pytest.raises(ValidationError):
        BOMItem(item_number="1", confidence_score=1.5)


def test_callout_requires_bounding_box():
    box = BoundingBox(xmin=0, ymin=0, xmax=10, ymax=10)
    callout = Callout(bubble_number="3", bounding_box=box, confidence_score=0.8)
    assert callout.bubble_number == "3"


def test_extracted_component_full_contract_shape():
    box = BoundingBox(xmin=185, ymin=412, xmax=230, ymax=458)
    component = ExtractedComponent(
        id="cmp_003",
        item_number="3",
        bubble_number="3",
        part_number="FB-M8-001",
        part_name="Hexagonal Flange Bolt M8",
        quantity=6,
        material_specification="Grade 8.8 Carbon Steel",
        confidence_score=0.97,
        bounding_box=box,
    )
    dumped = component.model_dump()
    assert dumped["id"] == "cmp_003"
    assert dumped["bounding_box"]["xmax"] == 230


def test_extraction_result_defaults_to_empty_lists():
    result = ExtractionResult()
    assert result.bom_items == []
    assert result.callouts == []
    assert result.components == []
    assert result.extraction_warnings == []
