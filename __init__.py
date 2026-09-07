"""
BlueprintAI document-processor package.

Handles validation and preprocessing of engineering drawing inputs
(PDF / PNG / JPEG) before any downstream AI or extraction stages.
"""

try:
    from .validators import validate_file
    from .models import (
        BoundingRegion,
        ProcessedPage,
        ProcessedDocument,
        ProcessingError,
    )
except ImportError:
    from validators import validate_file
    from models import (
        BoundingRegion,
        ProcessedPage,
        ProcessedDocument,
        ProcessingError,
    )

__all__ = [
    "validate_file",
    "BoundingRegion",
    "ProcessedPage",
    "ProcessedDocument",
    "ProcessingError",
]

__version__ = "0.1.0"
