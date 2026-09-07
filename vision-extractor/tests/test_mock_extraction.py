import json
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from vision_extractor import VisionExtractor
from vision_extractor.confidence import (
    clamp_confidence,
    is_low_confidence,
    is_valid_confidence,
    low_confidence_warning,
)
from vision_extractor.config import Settings
from vision_extractor.exceptions import ClaudeAPIError, VisionConfigurationError
from vision_extractor.mock_data import build_mock_extraction_result
from vision_extractor.models import ExtractionResult


def _mock_settings(**overrides) -> Settings:
    defaults = dict(
        anthropic_api_key=None,
        anthropic_model="claude-sonnet-5",
        gemini_api_key=None,
        gemini_model="gemini-3.6-flash",
        use_mock=False,
        low_confidence_threshold=0.70,
    )
    defaults.update(overrides)
    return Settings(**defaults)


def test_mock_data_matches_shared_contract():
    result = build_mock_extraction_result()
    assert result.drawing_number == "ASM-001"
    assert result.revision == "B"
    assert len(result.bom_items) == 5
    assert len(result.callouts) == 5
    assert len(result.components) == 5
    assert result.extraction_source == "mock"

    component = result.components[2]  # item 3, per the shared contract example
    assert component.item_number == "3"
    assert component.bubble_number == "3"
    assert component.part_number == "FB-M8-001"
    assert component.part_name == result.bom_items[2].description
    assert component.bounding_box.xmin == 185
    assert component.bounding_box.ymax == 458


def test_mock_data_includes_low_confidence_warning():
    result = build_mock_extraction_result()
    assert any("Low confidence" in w for w in result.extraction_warnings)


def test_mock_data_is_json_serializable():
    result = build_mock_extraction_result()
    payload = json.loads(result.model_dump_json())
    assert payload["drawing_number"] == "ASM-001"
    assert payload["extraction_source"] == "mock"
    assert isinstance(payload["components"], list)


def test_use_mock_true_returns_mock(monkeypatch):
    """USE_MOCK=true is explicit development mode and returns canned mock data."""
    monkeypatch.setenv("USE_MOCK", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    extractor = VisionExtractor()
    assert extractor.using_mock is True
    assert extractor.extraction_source == "mock"

    result = extractor.extract_from_image("examples/sample_input/nonexistent_placeholder.png")
    assert result.extraction_source == "mock"
    assert len(result.bom_items) == 5
    assert result.drawing_number == "ASM-001"


def test_use_mock_false_missing_key_does_not_return_mock(monkeypatch):
    """Live mode with no API key must raise — never substitute mock data."""
    monkeypatch.setenv("USE_MOCK", "false")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(VisionConfigurationError, match="ANTHROPIC_API_KEY"):
        VisionExtractor()


def test_claude_init_failure_does_not_return_mock():
    """Claude client initialization failure must raise, not fall back to mock."""
    settings = _mock_settings(use_mock=False, anthropic_api_key="sk-test-key")

    with patch(
        "vision_extractor.extractor.ClaudeVisionClient",
        side_effect=ClaudeAPIError("SDK boom"),
    ):
        with pytest.raises(VisionConfigurationError, match="Failed to initialize"):
            VisionExtractor(settings=settings)


def test_use_mock_false_valid_config_uses_claude():
    """USE_MOCK=false with a working Claude client must tag results as claude."""
    settings = _mock_settings(use_mock=False, anthropic_api_key="sk-test-key")
    fake_client = MagicMock()
    fake_client.extract_bom.return_value = json.dumps(
        {
            "drawing_number": "LIVE-001",
            "revision": "A",
            "bom_items": [
                {
                    "item_number": "1",
                    "part_number": "P-1",
                    "description": "Live part",
                    "quantity": 1,
                    "material": "Steel",
                    "confidence_score": 0.95,
                }
            ],
        }
    )
    fake_client.detect_callouts.return_value = json.dumps({"callouts": []})

    with patch(
        "vision_extractor.extractor.ClaudeVisionClient",
        return_value=fake_client,
    ):
        extractor = VisionExtractor(settings=settings)
        assert extractor.using_mock is False
        assert extractor.extraction_source == "claude"

        image = Image.new("RGB", (100, 100), color="white")
        result = extractor.extract_from_image(image)

    assert isinstance(result, ExtractionResult)
    assert result.extraction_source == "claude"
    assert result.drawing_number == "LIVE-001"
    assert len(result.bom_items) == 1
    assert result.bom_items[0].part_number == "P-1"
    # Must not be the canned mock drawing / 5-row set
    assert result.drawing_number != "ASM-001"
    assert len(result.bom_items) != 5 or result.bom_items[0].part_number != "FB-M8-001"
    fake_client.extract_bom.assert_called_once()
    fake_client.detect_callouts.assert_called_once()


def test_claude_request_failure_does_not_return_mock():
    """Claude request failures yield empty results + warnings, still source=claude."""
    settings = _mock_settings(use_mock=False, anthropic_api_key="sk-test-key")
    fake_client = MagicMock()
    fake_client.extract_bom.side_effect = ClaudeAPIError("quota exceeded")
    fake_client.detect_callouts.side_effect = ClaudeAPIError("quota exceeded")

    with patch(
        "vision_extractor.extractor.ClaudeVisionClient",
        return_value=fake_client,
    ):
        extractor = VisionExtractor(settings=settings)
        image = Image.new("RGB", (80, 80), color="white")
        result = extractor.extract_from_image(image)

    assert result.extraction_source == "claude"
    assert result.bom_items == []
    assert result.callouts == []
    assert result.components == []
    assert any("BOM extraction failed" in w for w in result.extraction_warnings)
    assert any("Callout detection failed" in w for w in result.extraction_warnings)
    # Explicitly not mock
    assert result.drawing_number != "ASM-001"


def test_live_image_load_failure_raises():
    settings = _mock_settings(use_mock=False, anthropic_api_key="sk-test-key")

    with patch(
        "vision_extractor.extractor.ClaudeVisionClient",
        return_value=MagicMock(),
    ):
        extractor = VisionExtractor(settings=settings)
        with pytest.raises(VisionConfigurationError, match="Failed to load image"):
            extractor.extract_from_image("definitely/missing/drawing.png")


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
