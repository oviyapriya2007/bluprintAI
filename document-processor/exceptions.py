"""
Readable exceptions for BlueprintAI Person 3 document preprocessing.

Do not include file contents in messages — paths and short reasons only.
"""

from __future__ import annotations


class DocumentProcessorError(Exception):
    """Base error for Person 3 preprocessing failures."""

    code: str = "PROCESSING_FAILED"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class UnsupportedFormatError(DocumentProcessorError):
    """File extension or format is not supported."""

    code = "UNSUPPORTED_FORMAT"


class CorruptImageError(DocumentProcessorError):
    """PNG/JPEG exists but cannot be decoded as a valid image."""

    code = "CORRUPT_IMAGE"


class InvalidPDFError(DocumentProcessorError):
    """PDF is missing, empty, malformed, or unreadable."""

    code = "INVALID_PDF"


class PopplerError(DocumentProcessorError):
    """pdf2image / Poppler conversion failed (missing binary, timeout, etc.)."""

    code = "POPPLER_ERROR"


class ImageProcessingError(DocumentProcessorError):
    """Resize, crop, save, or other image-processing step failed."""

    code = "IMAGE_PROCESSING_ERROR"


# Backward-compatible aliases used by older call sites
class PDFConversionError(PopplerError):
    """Alias: PDF rasterization failure."""

    code = "PDF_CONVERSION_ERROR"


class ImageLoadError(ImageProcessingError):
    """Alias: image load / normalize failure."""

    code = "IMAGE_LOAD_ERROR"
