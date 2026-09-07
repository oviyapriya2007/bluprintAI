"""vision_extractor: BlueprintAI's Vision AI Extraction module (Person 4).

Public API:

    from vision_extractor import VisionExtractor
    extractor = VisionExtractor()
    result = extractor.extract_from_image("drawing.png")
    result.model_dump()        # dict
    result.model_dump_json()   # JSON string
"""

import logging

from .exceptions import (
    ClaudeAPIError,
    GeminiAPIError,
    InvalidExtractionError,
    VisionConfigurationError,
    VisionExtractionError,
)
from .extractor import VisionExtractor
from .models import (
    BOMItem,
    BoundingBox,
    Callout,
    ExtractedComponent,
    ExtractionResult,
    LeaderEndpoint,
    LeaderLineStatus,
)

# Library convention: don't configure handlers, just avoid "no handler found" warnings.
logging.getLogger(__name__).addHandler(logging.NullHandler())

__all__ = [
    "VisionExtractor",
    "ExtractionResult",
    "BOMItem",
    "Callout",
    "ExtractedComponent",
    "BoundingBox",
    "LeaderEndpoint",
    "LeaderLineStatus",
    "VisionExtractionError",
    "VisionConfigurationError",
    "GeminiAPIError",
    "ClaudeAPIError",
    "InvalidExtractionError",
]

__version__ = "0.1.0"
