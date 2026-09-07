"""vision_extractor: BlueprintAI's Vision AI Extraction module (Person 4).

Public API:

    from vision_extractor import VisionExtractor
    extractor = VisionExtractor()
    result = extractor.extract_from_image("drawing.png")
    result.model_dump()        # dict
    result.model_dump_json()   # JSON string
"""

import logging

from .exceptions import GeminiAPIError, InvalidExtractionError, VisionExtractionError
from .extractor import VisionExtractor
from .models import BOMItem, BoundingBox, Callout, ExtractedComponent, ExtractionResult

# Library convention: don't configure handlers, just avoid "no handler found" warnings.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "VisionExtractor",
    "ExtractionResult",
    "BOMItem",
    "Callout",
    "ExtractedComponent",
    "BoundingBox",
    "VisionExtractionError",
    "GeminiAPIError",
    "InvalidExtractionError",
]

__version__ = "0.1.0"
