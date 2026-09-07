"""Custom exceptions for the vision_extractor package."""


class VisionExtractionError(Exception):
    """Base error for any failure in the vision extraction pipeline."""


class GeminiAPIError(VisionExtractionError):
    """Raised when the Gemini API call itself fails (network, auth, quota, etc.)."""


class ClaudeAPIError(VisionExtractionError):
    """Raised when the Claude (Anthropic) API call itself fails (network, auth, quota, etc.)."""


class InvalidExtractionError(VisionExtractionError):
    """Raised when a vision model's response cannot be parsed/validated into the data contract."""
