"""Thin, isolated wrapper around the Anthropic Claude API.

Mirrors gemini_client.py's public interface exactly (extract_bom,
detect_callouts, extract_drawing_metadata -> raw JSON text) so extractor.py
can swap providers by only changing which client class it instantiates.
Nothing else in the package should import `anthropic` directly.

The `anthropic` package is imported lazily inside __init__ so the whole
vision_extractor package remains importable (and mock mode fully usable)
even when the SDK isn't installed.
"""

from __future__ import annotations

import base64
import io
import logging

from PIL import Image

from .exceptions import ClaudeAPIError

logger = logging.getLogger(__name__)

# Generous enough for a BOM/callout list on a dense sheet without being
# unbounded; Claude stops early on shorter responses regardless.
_MAX_OUTPUT_TOKENS = 8192


class ClaudeVisionClient:
    """Wraps Claude multimodal calls for BOM extraction, callout detection,
    and drawing metadata extraction."""

    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise ClaudeAPIError("ClaudeVisionClient requires a non-empty api_key")
        self._model = model
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ClaudeAPIError(
                "anthropic SDK is not installed. Run `pip install anthropic` "
                "or enable USE_MOCK=true to run without it."
            ) from exc
        self._client = Anthropic(api_key=api_key)

    @staticmethod
    def _encode_image(image: Image.Image) -> tuple[str, str]:
        """Encode a PIL image as base64 PNG (lossless -- preserves small
        BOM-table text legibility). Returns (media_type, base64_data)."""
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, format="PNG")
        data = base64.standard_b64encode(buffer.getvalue()).decode("ascii")
        return "image/png", data

    def _generate_json(self, image: Image.Image, prompt: str) -> str:
        """Send an image + prompt to Claude and return raw JSON text.

        Relies on the prompt's own "return ONLY valid JSON" instruction
        (see prompts.py) plus the existing parse_json_response()'s
        markdown-fence stripping in validator.py to handle whatever Claude
        actually returns -- no provider-specific response munging here.

        Note: an assistant-turn "{" prefill (the usual Anthropic technique
        for forcing JSON-only output) was tried and removed -- newer Claude
        models (e.g. claude-sonnet-5) reject it outright with a 400
        "This model does not support assistant message prefill" error, so
        prompt-only instruction is what this integration relies on instead.

        Raises ClaudeAPIError on any transport/SDK failure.
        """
        media_type, image_data = self._encode_image(image)

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=_MAX_OUTPUT_TOKENS,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    },
                ],
            )
        except Exception as exc:  # noqa: BLE001 -- SDK raises various transport/auth errors
            raise ClaudeAPIError(f"Claude request failed: {exc}") from exc

        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        if not text:
            raise ClaudeAPIError("Claude returned an empty response")

        return text

    def extract_bom(self, image: Image.Image, prompt: str) -> str:
        """Run the BOM extraction prompt against an image. Returns raw JSON text."""
        logger.info("Sending BOM extraction request to Claude model=%s", self._model)
        text = self._generate_json(image, prompt)
        logger.info("Received BOM extraction response (%d chars)", len(text))
        return text

    def detect_callouts(self, image: Image.Image, prompt: str) -> str:
        """Run the callout detection prompt against an image. Returns raw JSON text."""
        logger.info("Sending callout detection request to Claude model=%s", self._model)
        text = self._generate_json(image, prompt)
        logger.info("Received callout detection response (%d chars)", len(text))
        return text

    def extract_drawing_metadata(self, image: Image.Image, prompt: str) -> str:
        """Run the drawing metadata prompt against an image. Returns raw JSON text."""
        logger.info("Sending drawing metadata request to Claude model=%s", self._model)
        text = self._generate_json(image, prompt)
        logger.info("Received drawing metadata response (%d chars)", len(text))
        return text
