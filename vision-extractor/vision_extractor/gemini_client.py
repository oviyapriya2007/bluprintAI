"""Thin, isolated client around the Gemini multimodal API.

All Gemini SDK specifics live here so the rest of the package (extractor,
validator, etc.) never imports `google.genai` directly. If the SDK changes
or is swapped out later, only this file should need to change.

The `google-genai` package is imported lazily inside methods so that the
whole vision_extractor package remains importable (and mock mode fully
usable) even when the SDK isn't installed.
"""

from __future__ import annotations

import logging
from typing import Any

from PIL import Image

from .exceptions import GeminiAPIError

logger = logging.getLogger(__name__)


class GeminiVisionClient:
    """Wraps Gemini multimodal calls for BOM extraction, callout detection,
    and drawing metadata extraction."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise GeminiAPIError("GeminiVisionClient requires a non-empty api_key")
        self._model = model
        try:
            from google import genai
        except ImportError as exc:
            raise GeminiAPIError(
                "google-genai SDK is not installed. Run `pip install google-genai` "
                "or enable USE_MOCK=true to run without it."
            ) from exc
        self._client = genai.Client(api_key=api_key)

    def _generate_json(self, image: Image.Image, prompt: str) -> str:
        """Send an image + prompt to Gemini and return the raw text response.

        Raises GeminiAPIError on any transport/SDK failure. Does not attempt
        to parse or validate the response — that's the caller's job.
        """
        try:
            from google.genai import types

            response = self._client.models.generate_content(
                model=self._model,
                contents=[image, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                ),
            )
        except Exception as exc:  # SDK raises various transport/auth errors
            raise GeminiAPIError(f"Gemini request failed: {exc}") from exc

        text = getattr(response, "text", None)
        if not text:
            raise GeminiAPIError("Gemini returned an empty response")
        return text

    def extract_bom(self, image: Image.Image, prompt: str) -> str:
        """Run the BOM extraction prompt against an image. Returns raw JSON text."""
        logger.info("Sending BOM extraction request to Gemini model=%s", self._model)
        text = self._generate_json(image, prompt)
        logger.info("Received BOM extraction response (%d chars)", len(text))
        return text

    def detect_callouts(self, image: Image.Image, prompt: str) -> str:
        """Run the callout detection prompt against an image. Returns raw JSON text."""
        logger.info("Sending callout detection request to Gemini model=%s", self._model)
        text = self._generate_json(image, prompt)
        logger.info("Received callout detection response (%d chars)", len(text))
        return text

    def extract_drawing_metadata(self, image: Image.Image, prompt: str) -> str:
        """Run the drawing metadata prompt against an image. Returns raw JSON text."""
        logger.info("Sending drawing metadata request to Gemini model=%s", self._model)
        text = self._generate_json(image, prompt)
        logger.info("Received drawing metadata response (%d chars)", len(text))
        return text
