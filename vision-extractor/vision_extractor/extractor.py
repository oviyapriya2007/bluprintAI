"""Public extraction service: image -> ExtractionResult.

This is the main entry point other team members should use:

    from vision_extractor import VisionExtractor
    extractor = VisionExtractor()
    result = extractor.extract_from_image("drawing.png")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

from PIL import Image

from .claude_client import ClaudeVisionClient
from .config import Settings, get_settings
from .exceptions import ClaudeAPIError, InvalidExtractionError, VisionExtractionError
from .mock_data import build_mock_extraction_result
from .models import ExtractionResult
from .prompts import BOM_EXTRACTION_PROMPT, CALLOUT_DETECTION_PROMPT
from .utils import get_image_dimensions, load_image
from .validator import build_components, parse_json_response, validate_bom_items, validate_callouts

logger = logging.getLogger(__name__)


class VisionExtractor:
    """Orchestrates BOM extraction + callout detection for a single drawing image."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self._client: Optional[ClaudeVisionClient] = None

        if not self._settings.use_mock:
            try:
                self._client = ClaudeVisionClient(
                    api_key=self._settings.anthropic_api_key,
                    model=self._settings.anthropic_model,
                )
            except ClaudeAPIError as exc:
                logger.warning(
                    "Falling back to mock mode: could not initialize Claude client (%s)", exc
                )
                self._client = None

        logger.info(
            "VisionExtractor initialized (mock=%s, model=%s)",
            self._client is None,
            self._settings.anthropic_model,
        )

    @property
    def using_mock(self) -> bool:
        return self._client is None

    def extract_from_image(self, image: Union[str, Path, Image.Image]) -> ExtractionResult:
        """Run full extraction (BOM + callouts) on an image path or PIL Image.

        Always returns an ExtractionResult, even on partial or total failure —
        errors are surfaced via extraction_warnings rather than raised, so one
        bad drawing never crashes a batch/demo. Falls back to deterministic
        mock data if mock mode is enabled or the Claude call fails outright.
        """
        try:
            pil_image, source_label = self._load_input_image(image)
        except (FileNotFoundError, ValueError) as exc:
            logger.error("Could not load image: %s", exc)
            result = build_mock_extraction_result()
            result.extraction_warnings.insert(0, f"Failed to load image ({exc}); returned mock data")
            return result

        width, height = get_image_dimensions(pil_image)
        logger.info("Image received: %s (%dx%d)", source_label, width, height)

        if self.using_mock:
            logger.info("USE_MOCK enabled or no Claude client available; returning mock extraction")
            return build_mock_extraction_result()

        return self._extract_with_claude(pil_image, width, height)

    def _load_input_image(self, image: Union[str, Path, Image.Image]) -> tuple[Image.Image, str]:
        if isinstance(image, Image.Image):
            return image.convert("RGB"), "<in-memory PIL.Image>"
        return load_image(image), str(image)

    def _extract_with_claude(
        self, image: Image.Image, width: int, height: int
    ) -> ExtractionResult:
        warnings: list[str] = []
        threshold = self._settings.low_confidence_threshold

        bom_items, drawing_number, revision = self._run_bom_extraction(image, warnings)
        callouts = self._run_callout_detection(image, width, height, warnings, threshold)

        # bom_items already validated inside _run_bom_extraction; re-derive
        # warnings for low confidence there too.
        components = build_components(bom_items, callouts)

        logger.info(
            "Extraction completed: %d BOM items, %d callouts, %d matched components, %d warnings",
            len(bom_items),
            len(callouts),
            len(components),
            len(warnings),
        )

        return ExtractionResult(
            drawing_number=drawing_number,
            revision=revision,
            bom_items=bom_items,
            callouts=callouts,
            components=components,
            extraction_warnings=warnings,
        )

    def _run_bom_extraction(self, image: Image.Image, warnings: list[str]):
        threshold = self._settings.low_confidence_threshold
        try:
            logger.info("Starting BOM extraction request")
            raw_text = self._client.extract_bom(image, BOM_EXTRACTION_PROMPT)
            parsed = parse_json_response(raw_text)
        except (ClaudeAPIError, InvalidExtractionError) as exc:
            warnings.append(f"BOM extraction failed: {exc}")
            logger.error("BOM extraction failed: %s", exc)
            return [], None, None

        raw_items = parsed.get("bom_items", [])
        if not isinstance(raw_items, list):
            warnings.append("BOM response 'bom_items' was not a list; treated as empty")
            raw_items = []

        bom_items, bom_warnings = validate_bom_items(raw_items, threshold)
        warnings.extend(bom_warnings)

        drawing_number = parsed.get("drawing_number")
        revision = parsed.get("revision")
        return bom_items, drawing_number, revision

    def _run_callout_detection(
        self,
        image: Image.Image,
        width: int,
        height: int,
        warnings: list[str],
        threshold: float,
    ):
        try:
            logger.info("Starting callout detection request")
            raw_text = self._client.detect_callouts(image, CALLOUT_DETECTION_PROMPT)
            parsed = parse_json_response(raw_text)
        except (ClaudeAPIError, InvalidExtractionError) as exc:
            warnings.append(f"Callout detection failed: {exc}")
            logger.error("Callout detection failed: %s", exc)
            return []

        raw_callouts = parsed.get("callouts", [])
        if not isinstance(raw_callouts, list):
            warnings.append("Callout response 'callouts' was not a list; treated as empty")
            raw_callouts = []

        callouts, callout_warnings = validate_callouts(
            raw_callouts, threshold, image_width=width, image_height=height
        )
        warnings.extend(callout_warnings)
        return callouts
