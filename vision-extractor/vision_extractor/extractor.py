"""Public extraction service: image -> ExtractionResult.

This is the main entry point other team members should use:

    from vision_extractor import VisionExtractor
    extractor = VisionExtractor()
    result = extractor.extract_from_image("drawing.png")

Mock data is returned ONLY when USE_MOCK=true (explicit development mode).
Live mode (USE_MOCK=false) never substitutes mock results.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

from PIL import Image

from .claude_client import ClaudeVisionClient
from .config import Settings, get_settings
from .diagnostics import LiveVisionDiagnostics
from .exceptions import ClaudeAPIError, InvalidExtractionError, VisionConfigurationError
from .mock_data import build_mock_extraction_result
from .models import Callout, ExtractionResult
from .prompts import BOM_EXTRACTION_PROMPT, CALLOUT_DETECTION_PROMPT
from .tiling import (
    deduplicate_callouts,
    remap_callout_to_page,
    split_into_tiles,
)
from .utils import get_image_dimensions, load_image
from .validator import build_components, parse_json_response, validate_bom_items, validate_callouts
from .verification import verify_callouts

logger = logging.getLogger(__name__)

# Reminds Claude that tile crops are local coordinate systems.
_TILE_CALLOUT_PROMPT_PREFIX = (
    "This image is a cropped TILE of a larger engineering drawing. "
    "Detect callouts only within this crop. Report ALL coordinates relative "
    "to THIS tile image (0–1000), not the full page.\n\n"
)


class VisionExtractor:
    """Orchestrates BOM extraction + callout detection for a single drawing image."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self._client: Optional[ClaudeVisionClient] = None
        self._init_error: Optional[str] = None
        # Temporary live-mode diagnostics sink (set by run_pipeline); never
        # affects extraction results — only records intermediates for debug dumps.
        self._diagnostics: Optional[LiveVisionDiagnostics] = None

        if self._settings.use_mock:
            logger.info(
                "VisionExtractor initialized in explicit mock mode "
                "(USE_MOCK=true; model=%s)",
                self._settings.anthropic_model,
            )
            return

        if not self._settings.anthropic_api_key:
            raise VisionConfigurationError(
                "Live vision extraction requires ANTHROPIC_API_KEY. "
                "Set the key in vision-extractor/.env, or set USE_MOCK=true "
                "for explicit development mock data."
            )

        try:
            self._client = ClaudeVisionClient(
                api_key=self._settings.anthropic_api_key,
                model=self._settings.anthropic_model,
            )
        except ClaudeAPIError as exc:
            self._init_error = str(exc)
            raise VisionConfigurationError(
                f"Failed to initialize Claude vision client: {exc}"
            ) from exc

        logger.info(
            "VisionExtractor initialized (source=claude, model=%s, "
            "callout_tiling=%s, callout_verify=%s)",
            self._settings.anthropic_model,
            self._settings.callout_tiling_enabled,
            self._settings.callout_verification_enabled,
        )

    @property
    def using_mock(self) -> bool:
        """True only when USE_MOCK=true (never inferred from a missing client)."""
        return self._settings.use_mock

    @property
    def extraction_source(self) -> str:
        return "mock" if self.using_mock else "claude"

    def extract_from_image(self, image: Union[str, Path, Image.Image]) -> ExtractionResult:
        """Run full extraction (BOM + callouts) on an image path or PIL Image.

        Mock mode (USE_MOCK=true): returns canned mock data with
        ``extraction_source="mock"``.

        Live mode (USE_MOCK=false): never returns mock data. Image-load and
        configuration failures raise. Claude request failures yield empty
        BOM/callout lists plus ``extraction_warnings``, still tagged
        ``extraction_source="claude"``.
        """
        if self.using_mock:
            logger.info("USE_MOCK=true; returning explicit mock extraction")
            result = build_mock_extraction_result()
            result.extraction_source = "mock"
            return result

        if self._client is None:
            raise VisionConfigurationError(
                self._init_error
                or "Claude vision client is not initialized for live extraction."
            )

        try:
            pil_image, source_label = self._load_input_image(image)
        except (FileNotFoundError, ValueError) as exc:
            logger.error("Could not load image: %s", exc)
            raise VisionConfigurationError(f"Failed to load image: {exc}") from exc

        width, height = get_image_dimensions(pil_image)
        logger.info("Image received: %s (%dx%d)", source_label, width, height)
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

        # BOM always runs on the full image — tiling/verification are callout-only.
        bom_items, drawing_number, revision = self._run_bom_extraction(image, warnings)
        callouts = self._run_callout_detection(image, width, height, warnings, threshold)
        callouts = self._maybe_verify_callouts(image, callouts, warnings)

        components, component_warnings = build_components(bom_items, callouts)
        warnings.extend(component_warnings)
        if self._diagnostics is not None:
            self._diagnostics.extend_warnings(list(component_warnings))

        logger.info(
            "Extraction completed (source=claude): %d BOM items, %d callouts, "
            "%d matched components, %d warnings",
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
            extraction_source="claude",
        )

    def _run_bom_extraction(self, image: Image.Image, warnings: list[str]):
        threshold = self._settings.low_confidence_threshold
        diag = self._diagnostics
        raw_text: Optional[str] = None
        try:
            logger.info("Starting BOM extraction request")
            raw_text = self._client.extract_bom(image, BOM_EXTRACTION_PROMPT)
            if diag is not None:
                diag.record_bom_raw(raw_text)
            parsed = parse_json_response(raw_text)
            if diag is not None:
                diag.record_bom_parsed(parsed)
        except (ClaudeAPIError, InvalidExtractionError) as exc:
            warnings.append(f"BOM extraction failed: {exc}")
            logger.error("BOM extraction failed: %s", exc)
            if diag is not None:
                if raw_text is not None:
                    diag.record_bom_raw(raw_text)
                diag.record_bom_parsed(None, error=str(exc))
                diag.record_bom_validated(0)
            return [], None, None

        raw_items = parsed.get("bom_items", [])
        if not isinstance(raw_items, list):
            warnings.append("BOM response 'bom_items' was not a list; treated as empty")
            raw_items = []

        bom_items, bom_warnings = validate_bom_items(raw_items, threshold)
        warnings.extend(bom_warnings)
        if diag is not None:
            diag.record_bom_validated(len(bom_items))
            diag.extend_warnings(list(bom_warnings))

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
    ) -> list[Callout]:
        if self._settings.callout_tiling_enabled:
            return self._run_tiled_callout_detection(image, width, height, warnings, threshold)
        return self._run_single_callout_detection(image, width, height, warnings, threshold)

    def _run_single_callout_detection(
        self,
        image: Image.Image,
        width: int,
        height: int,
        warnings: list[str],
        threshold: float,
    ) -> list[Callout]:
        diag = self._diagnostics
        raw_text: Optional[str] = None
        try:
            logger.info("Starting callout detection request (full image)")
            raw_text = self._client.detect_callouts(image, CALLOUT_DETECTION_PROMPT)
            if diag is not None:
                diag.record_callout_raw(raw_text)
            parsed = parse_json_response(raw_text)
            if diag is not None:
                diag.record_callout_parsed(parsed)
        except (ClaudeAPIError, InvalidExtractionError) as exc:
            warnings.append(f"Callout detection failed: {exc}")
            logger.error("Callout detection failed: %s", exc)
            if diag is not None:
                if raw_text is not None:
                    diag.record_callout_raw(raw_text)
                diag.record_callout_parsed(None, error=str(exc))
                diag.record_callout_validated(0)
            return []

        raw_callouts = parsed.get("callouts", [])
        if not isinstance(raw_callouts, list):
            warnings.append("Callout response 'callouts' was not a list; treated as empty")
            raw_callouts = []

        callouts, callout_warnings = validate_callouts(
            raw_callouts, threshold, image_width=width, image_height=height
        )
        warnings.extend(callout_warnings)
        if diag is not None:
            diag.record_callout_validated(len(callouts))
            diag.extend_warnings(list(callout_warnings))
        return callouts

    def _run_tiled_callout_detection(
        self,
        image: Image.Image,
        width: int,
        height: int,
        warnings: list[str],
        threshold: float,
    ) -> list[Callout]:
        """Detect callouts on overlapping tiles, remap to page coords, dedupe."""
        settings = self._settings
        diag = self._diagnostics
        tiles = split_into_tiles(
            image,
            grid_rows=settings.callout_tile_grid_rows,
            grid_cols=settings.callout_tile_grid_cols,
            overlap_fraction=settings.callout_tile_overlap,
        )
        warnings.append(
            f"Callout tiling enabled: {settings.callout_tile_grid_rows}x"
            f"{settings.callout_tile_grid_cols} grid, "
            f"overlap={settings.callout_tile_overlap:.0%}, {len(tiles)} tiles"
        )

        prompt = _TILE_CALLOUT_PROMPT_PREFIX + CALLOUT_DETECTION_PROMPT
        remapped: list[Callout] = []
        tile_validation_warnings: list[str] = []

        for tile in tiles:
            raw_text: Optional[str] = None
            try:
                logger.info(
                    "Callout detection on %s (%dx%d px at %d,%d)",
                    tile.label,
                    tile.width,
                    tile.height,
                    tile.x0,
                    tile.y0,
                )
                raw_text = self._client.detect_callouts(tile.image, prompt)
                if diag is not None:
                    diag.record_callout_raw(raw_text)
                parsed = parse_json_response(raw_text)
                if diag is not None:
                    diag.record_callout_parsed(parsed)
            except (ClaudeAPIError, InvalidExtractionError) as exc:
                warnings.append(f"Callout detection failed on {tile.label}: {exc}")
                logger.error("Callout detection failed on %s: %s", tile.label, exc)
                if diag is not None:
                    if raw_text is not None:
                        diag.record_callout_raw(raw_text)
                    diag.record_callout_parsed(None, error=f"{tile.label}: {exc}")
                continue

            raw_callouts = parsed.get("callouts", [])
            if not isinstance(raw_callouts, list):
                warnings.append(
                    f"Callout response on {tile.label} 'callouts' was not a list; treated as empty"
                )
                raw_callouts = []

            tile_callouts, tile_warnings = validate_callouts(
                raw_callouts,
                threshold,
                image_width=tile.width,
                image_height=tile.height,
            )
            for warning in tile_warnings:
                msg = f"{tile.label}: {warning}"
                warnings.append(msg)
                tile_validation_warnings.append(msg)

            for callout in tile_callouts:
                remapped.append(
                    remap_callout_to_page(callout, tile, page_width=width, page_height=height)
                )

        deduped, dedupe_warnings = deduplicate_callouts(
            remapped, iou_threshold=settings.callout_dedupe_iou
        )
        warnings.extend(dedupe_warnings)

        if diag is not None:
            diag.record_callout_validated(len(deduped))
            diag.extend_warnings(tile_validation_warnings)
            diag.extend_warnings(list(dedupe_warnings))

        logger.info(
            "Tiled callout detection: %d raw across tiles -> %d after dedupe",
            len(remapped),
            len(deduped),
        )
        return deduped

    def _maybe_verify_callouts(
        self,
        image: Image.Image,
        callouts: list[Callout],
        warnings: list[str],
    ) -> list[Callout]:
        if not self._settings.callout_verification_enabled:
            return callouts
        if not callouts:
            return callouts

        warnings.append(
            f"Callout verification enabled: checking {len(callouts)} detection(s)"
        )
        verified, verify_warnings = verify_callouts(self._client, image, callouts)
        warnings.extend(verify_warnings)
        logger.info(
            "Callout verification: %d in -> %d kept",
            len(callouts),
            len(verified),
        )
        return verified
