import json

from vision_extractor import VisionExtractor
from vision_extractor.confidence import (
    clamp_confidence,
    is_low_confidence,
    is_valid_confidence,
    low_confidence_warning,
)
from vision_extractor.mock_data import build_mock_extraction_result


def test_mock_data_matches_shared_contract():
    result = build_mock_extraction_result()
    assert result.drawing_number == "ASM-001"
    assert result.revision == "B"
    assert len(result.bom_items) == 5
    assert len(result.callouts) == 5
    assert len(result.components) == 5

    component = result.components[2]  # item 3, per the shared contract example
    assert component.item_number == "3"
    assert component.bubble_number == "3"
    assert component.part_number == "FB-M8-001"
    assert component.bounding_box.xmin == 185
    assert component.bounding_box.ymax == 458


def test_mock_data_includes_low_confidence_warning():
    result = build_mock_extraction_result()
    assert any("Low confidence" in w for w in result.extraction_warnings)


def test_mock_data_is_json_serializable():
    result = build_mock_extraction_result()
    payload = json.loads(result.model_dump_json())
    assert payload["drawing_number"] == "ASM-001"
    assert isinstance(payload["components"], list)


def test_vision_extractor_uses_mock_when_env_forces_it(monkeypatch):
    monkeypatch.setenv("USE_MOCK", "true")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    extractor = VisionExtractor()
    assert extractor.using_mock is True

    result = extractor.extract_from_image("examples/sample_input/nonexistent_placeholder.png")
    # falls back to mock even for a missing file, without raising
    assert len(result.bom_items) >= 1


def test_vision_extractor_defaults_to_mock_without_api_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("USE_MOCK", raising=False)
    extractor = VisionExtractor()
    assert extractor.using_mock is True


# --- confidence helper tests ---


def test_clamp_confidence_within_range():
    assert clamp_confidence(0.5) == 0.5


def test_clamp_confidence_clamps_high_and_low():
    assert clamp_confidence(1.7) == 1.0
    assert clamp_confidence(-0.3) == 0.0


def test_clamp_confidence_handles_none():
    assert clamp_confidence(None) == 0.0


def test_is_valid_confidence():
    assert is_valid_confidence(0.5) is True
    assert is_valid_confidence(1.5) is False
    assert is_valid_confidence("high") is False


def test_is_low_confidence():
    assert is_low_confidence(0.5, threshold=0.7) is True
    assert is_low_confidence(0.9, threshold=0.7) is False


def test_low_confidence_warning_message_format():
    msg = low_confidence_warning("BOM item", "12", 0.55)
    assert "item 12" in msg or "BOM item 12" in msg
    assert "0.55" in msg
