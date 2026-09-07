"""Custom exceptions for the vision_extractor package."""


class VisionExtractionError(Exception):
    """Base error for any failure in the vision extraction pipeline."""


class GeminiAPIError(VisionExtractionError):
    """Raised when the Gemini API call itself fails (network, auth, quota, etc.)."""


class ClaudeAPIError(VisionExtractionError):
    """Raised when the Claude (Anthropic) API call itself fails (network, auth, quota, etc.)."""


class VisionConfigurationError(VisionExtractionError):
    """Raised when live mode is requested but Claude cannot be configured or initialized.

    Live mode must never silently fall back to mock data — callers should
    surface this error instead.
    """


class InvalidExtractionError(VisionExtractionError):
    """Raised when a vision model's response cannot be parsed/validated into the data contract."""
