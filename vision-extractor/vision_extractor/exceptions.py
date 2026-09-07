"""Custom exceptions for the vision_extractor package."""


class VisionExtractionError(Exception):
    """Base error for any failure in the vision extraction pipeline."""


class GeminiAPIError(VisionExtractionError):
    """Raised when the Gemini API call itself fails (network, auth, quota, etc.)."""


class InvalidExtractionError(VisionExtractionError):
    """Raised when a Gemini response cannot be parsed/validated into the data contract."""
