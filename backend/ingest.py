"""
ingest.py -- Stage 1 of the BlueprintAI hybrid detection pipeline.

Normalizes an uploaded engineering drawing (PDF or raster image) into one
or more full-resolution page images ready for downstream deterministic
extraction (bom_extract.py) and callout detection (callout_detect.py).

Reuses the existing, independently-tested document-processor package
(Person 3) for PDF rasterization (pdf2image/Poppler, 300+ DPI) and raster
loading rather than reimplementing it. That package's directory is named
``document-processor`` (a hyphen), which Python cannot import as a normal
dotted package, so it's added to sys.path and imported flat -- exactly the
fallback import style document-processor's own modules already support
(see the try/except ImportError blocks in processor.py / image_utils.py).
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DOC_PROCESSOR_DIR = _REPO_ROOT / "document-processor"


def _bootstrap_document_processor():
    if str(_DOC_PROCESSOR_DIR) not in sys.path:
        sys.path.insert(0, str(_DOC_PROCESSOR_DIR))
    import image_utils as dp_image_utils  # type: ignore
    import processor as dp_processor  # type: ignore

    return dp_processor, dp_image_utils


_dp_processor, _dp_image_utils = _bootstrap_document_processor()

# Re-exported so the hybrid pipeline's entry point is literally the same
# function document-processor already exposed (same signature, same
# accepted inputs: PDF / PNG / JPEG file paths).
process_document = _dp_processor.process_document


@dataclass
class IngestedPage:
    page_id: str
    page_number: int
    image_path: str
    width: int
    height: int
    # Isolated crops (only populated when isolate_regions_enabled=True and
    # document-processor managed to find them) -- bom_extract.py prefers
    # title_block_region for its raster-OCR fallback, callout_detect.py
    # prefers drawing_region, so each stage sees a tighter, higher-effective-
    # resolution crop instead of the whole sheet. Both fall back to the
    # full page (image_path) when a region wasn't isolated.
    title_block_region_path: Optional[str] = None
    drawing_region_path: Optional[str] = None
    # Normalized (0-1000) placement of each crop on the full page, as a
    # plain {"xmin","ymin","xmax","ymax"} dict -- needed to remap
    # crop-pixel coordinates (e.g. callout_detect.py's bboxes) back to
    # full-page space. None when the corresponding *_region_path is None.
    title_block_region: Optional[dict] = None
    drawing_region: Optional[dict] = None


@dataclass
class IngestedDocument:
    document_id: str
    original_filename: str
    file_type: str
    status: str
    pages: list[IngestedPage] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)


def ingest(file_path: str, isolate_regions_enabled: bool = False) -> IngestedDocument:
    """Normalize a PDF/PNG/JPEG upload into full-resolution page images.

    Thin wrapper around ``document_processor.process_document`` (PDF -> 300+
    DPI raster via Poppler, image -> upright RGB load, EXIF-corrected). The
    existing entry point's accepted inputs are unchanged.
    """
    logger.info("[ingest] input received: %s", file_path)

    doc = process_document(file_path, isolate_regions_enabled=isolate_regions_enabled)

    pages = [
        IngestedPage(
            page_id=p.page_id,
            page_number=p.page_number,
            image_path=_resolve_page_path(p.image_path),
            width=p.width,
            height=p.height,
            title_block_region_path=_resolve_optional_page_path(p.title_block_region_path),
            drawing_region_path=_resolve_optional_page_path(p.drawing_region_path),
            title_block_region=p.title_block_region.model_dump() if p.title_block_region else None,
            drawing_region=p.drawing_region.model_dump() if p.drawing_region else None,
        )
        for p in doc.pages
    ]

    logger.info(
        "[ingest] normalized %s: file_type=%s pages=%d status=%s",
        doc.document_id,
        doc.file_type,
        len(pages),
        doc.status,
    )

    return IngestedDocument(
        document_id=doc.document_id,
        original_filename=doc.original_filename,
        file_type=doc.file_type,
        status=doc.status,
        pages=pages,
        errors=[e.model_dump() for e in doc.errors],
    )


def _resolve_page_path(image_path: str) -> str:
    """document_processor returns paths relative to its own package root
    (see processor._public_path) -- resolve them to absolute paths here so
    every other backend/ stage can treat page paths as opaque, absolute
    file locations."""
    candidate = Path(image_path)
    if candidate.is_absolute():
        return str(candidate)
    return str((_DOC_PROCESSOR_DIR / image_path).resolve())


def _resolve_optional_page_path(image_path: Optional[str]) -> Optional[str]:
    if not image_path:
        return None
    return _resolve_page_path(image_path)
