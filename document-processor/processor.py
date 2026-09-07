"""
Main orchestration for BlueprintAI document preprocessing (Person 3).

Flow:
  Validate -> Detect type -> PDF/raster load -> Normalize ->
  Optional region isolation -> Metadata -> ProcessedDocument

No Gemini, FastAPI, database, BOM extraction, or AI logic.
"""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

try:
    from .config import DEFAULT_CONFIG
    from .exceptions import (
        CorruptImageError,
        DocumentProcessorError,
        ImageProcessingError,
        InvalidPDFError,
        PopplerError,
        UnsupportedFormatError,
    )
    from .image_utils import (
        isolate_regions,
        load_image,
        normalize_resolution,
        pdf_to_images,
    )
    from .models import (
        BoundingRegion,
        ProcessedDocument,
        ProcessedPage,
        ProcessingError,
    )
    from .validators import validate_file
except ImportError:  # flat imports when run from document-processor/
    from config import DEFAULT_CONFIG
    from exceptions import (
        CorruptImageError,
        DocumentProcessorError,
        ImageProcessingError,
        InvalidPDFError,
        PopplerError,
        UnsupportedFormatError,
    )
    from image_utils import (
        isolate_regions,
        load_image,
        normalize_resolution,
        pdf_to_images,
    )
    from models import (
        BoundingRegion,
        ProcessedDocument,
        ProcessedPage,
        ProcessingError,
    )
    from validators import validate_file

logger = logging.getLogger(__name__)

_PACKAGE_ROOT = Path(__file__).resolve().parent


def process_document(
    file_path: str,
    isolate_regions_enabled: bool = False,
) -> ProcessedDocument:
    """
    Preprocess an engineering drawing into Person 3 ``ProcessedDocument`` metadata.

    Logs concise step status only (never file contents). Failures return
    ``status="failed"`` with a readable error code/message.
    """
    source = Path(file_path)
    original_filename = source.name
    document_id = _new_document_id(DEFAULT_CONFIG.ensure_output_dir())
    doc_dir = DEFAULT_CONFIG.output_dir / document_id
    file_type = _suffix_type(source)

    logger.info("[%s] input file: %s", document_id, original_filename)

    # --- 1. Validate file ----------------------------------------------------
    logger.info("[%s] file validation: checking", document_id)
    validation = validate_file(file_path)
    if not validation["valid"]:
        message = validation["error"] or "Validation failed"
        code = _validation_error_code(message)
        logger.error("[%s] file validation: failed - %s", document_id, message)
        logger.error("[%s] failure", document_id)
        return _failed_document(
            document_id=document_id,
            original_filename=original_filename,
            file_type=validation.get("file_type") or file_type,
            errors=[
                ProcessingError(code=code, message=message, field="file_path")
            ],
        )
    logger.info("[%s] file validation: ok", document_id)

    # --- 2. Detect type ------------------------------------------------------
    file_type = validation["file_type"] or file_type
    logger.info("[%s] detected type: %s", document_id, file_type)

    try:
        doc_dir.mkdir(parents=True, exist_ok=True)
        logger.info("[%s] output directory: %s", document_id, _public_path(doc_dir))

        # --- 3. Load / convert pages ----------------------------------------
        if file_type == "pdf":
            logger.info(
                "[%s] PDF conversion: starting (dpi=%s)",
                document_id,
                DEFAULT_CONFIG.dpi,
            )
            page_sources = _convert_pdf_pages(file_path, doc_dir, document_id)
        else:
            logger.info("[%s] raster load: starting (%s)", document_id, file_type)
            page_sources = _load_raster_page(file_path, document_id)

        if not page_sources:
            raise InvalidPDFError("No pages produced from input document")

        logger.info("[%s] pages generated: %s", document_id, len(page_sources))

        # --- 4-6. Normalize, optional isolate, metadata ---------------------
        pages: list[ProcessedPage] = []
        page_errors: list[ProcessingError] = []

        for page_number, source_image in enumerate(page_sources, start=1):
            page_id = f"page_{page_number:03d}"
            try:
                page = _process_single_page(
                    document_id=document_id,
                    doc_dir=doc_dir,
                    page_id=page_id,
                    page_number=page_number,
                    source_image_path=source_image,
                    isolate_regions_enabled=isolate_regions_enabled,
                )
                pages.append(page)
            except DocumentProcessorError as exc:
                logger.error(
                    "[%s] %s failed: %s",
                    document_id,
                    page_id,
                    exc.message,
                )
                page_errors.append(
                    ProcessingError(
                        code=exc.code,
                        message=f"{page_id}: {exc.message}",
                        field="page",
                        page_number=page_number,
                    )
                )
            except (OSError, ValueError) as exc:
                message = f"{page_id}: image-processing error - {exc}"
                logger.error("[%s] %s", document_id, message)
                page_errors.append(
                    ProcessingError(
                        code=ImageProcessingError.code,
                        message=message,
                        field="page",
                        page_number=page_number,
                    )
                )

        if not pages:
            logger.error("[%s] failure: no pages processed", document_id)
            return _failed_document(
                document_id=document_id,
                original_filename=original_filename,
                file_type=file_type,
                errors=page_errors
                or [
                    ProcessingError(
                        code="NO_PAGES",
                        message="No pages were successfully processed",
                    )
                ],
            )

        status: str = "processed" if not page_errors else "partial"
        logger.info(
            "[%s] completion: status=%s pages=%s",
            document_id,
            status,
            len(pages),
        )
        return ProcessedDocument(
            document_id=document_id,
            original_filename=original_filename,
            file_type=file_type,
            page_count=len(pages),
            pages=pages,
            status=status,  # type: ignore[arg-type]
            errors=page_errors,
        )

    except DocumentProcessorError as exc:
        logger.error("[%s] failure: %s - %s", document_id, exc.code, exc.message)
        return _failed_document(
            document_id=document_id,
            original_filename=original_filename,
            file_type=file_type,
            errors=[
                ProcessingError(
                    code=exc.code,
                    message=exc.message,
                    field="file_path",
                )
            ],
        )
    except FileNotFoundError as exc:
        logger.error("[%s] failure: %s", document_id, exc)
        return _failed_document(
            document_id=document_id,
            original_filename=original_filename,
            file_type=file_type,
            errors=[
                ProcessingError(
                    code="FILE_NOT_FOUND",
                    message=str(exc),
                    field="file_path",
                )
            ],
        )
    except Exception as exc:  # noqa: BLE001 — never crash the caller
        logger.exception("[%s] failure: unexpected error", document_id)
        return _failed_document(
            document_id=document_id,
            original_filename=original_filename,
            file_type=file_type,
            errors=[
                ProcessingError(
                    code="UNEXPECTED_ERROR",
                    message=f"Unexpected error while processing document: {exc}",
                    field="file_path",
                )
            ],
        )


def _process_single_page(
    *,
    document_id: str,
    doc_dir: Path,
    page_id: str,
    page_number: int,
    source_image_path: str,
    isolate_regions_enabled: bool,
) -> ProcessedPage:
    """Normalize one page image and optionally isolate regions."""
    normalized_path = doc_dir / f"{page_id}.png"

    logger.info("[%s] resizing: %s", document_id, page_id)
    try:
        norm = normalize_resolution(
            source_image_path,
            str(normalized_path),
            max_dimension=DEFAULT_CONFIG.max_dimension,
            min_dimension=DEFAULT_CONFIG.min_dimension,
        )
    except DocumentProcessorError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImageProcessingError(
            f"Resizing failed for {page_id}: {exc}"
        ) from exc

    logger.info(
        "[%s] image dimensions: %s %sx%s -> %sx%s (resized=%s)",
        document_id,
        page_id,
        norm["original_width"],
        norm["original_height"],
        norm["processed_width"],
        norm["processed_height"],
        norm["resized"],
    )

    drawing_region_path: str | None = None
    title_block_region_path: str | None = None
    drawing_region: BoundingRegion | None = None
    title_block_region: BoundingRegion | None = None

    if isolate_regions_enabled:
        logger.info("[%s] region isolation: %s", document_id, page_id)
        regions_dir = doc_dir / f"{page_id}_regions"
        try:
            isolated = isolate_regions(
                str(normalized_path),
                str(regions_dir),
                mode="manual",
            )
        except DocumentProcessorError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ImageProcessingError(
                f"Region isolation failed for {page_id}: {exc}"
            ) from exc

        drawing_region_path = _public_path(Path(isolated["drawing_region"]))
        title_block_region_path = _public_path(Path(isolated["title_block_region"]))
        drawing_region = BoundingRegion(**isolated["regions"]["drawing"])
        title_block_region = BoundingRegion(**isolated["regions"]["title_block"])
        logger.info("[%s] region isolation: done (%s)", document_id, page_id)

    return ProcessedPage(
        page_id=page_id,
        page_number=page_number,
        image_path=_public_path(normalized_path),
        width=norm["processed_width"],
        height=norm["processed_height"],
        drawing_region_path=drawing_region_path,
        title_block_region_path=title_block_region_path,
        drawing_region=drawing_region,
        title_block_region=title_block_region,
    )


def _convert_pdf_pages(
    file_path: str,
    doc_dir: Path,
    document_id: str,
) -> list[str]:
    """Rasterize every PDF page into a private subfolder (upload untouched)."""
    raw_dir = doc_dir / "_pdf_raw"
    try:
        pages = pdf_to_images(
            file_path,
            str(raw_dir),
            dpi=DEFAULT_CONFIG.dpi,
        )
    except (PopplerError, InvalidPDFError, ImageProcessingError):
        raise
    except Exception as exc:  # noqa: BLE001
        raise PopplerError(f"pdf2image/Poppler failed: {exc}") from exc

    logger.info("[%s] PDF conversion: ok (%s pages)", document_id, len(pages))
    for page in pages:
        logger.info(
            "[%s] page image: page_%03d %sx%s",
            document_id,
            page["page_number"],
            page["width"],
            page["height"],
        )
    return [page["image_path"] for page in pages]


def _load_raster_page(file_path: str, document_id: str) -> list[str]:
    """Load a single PNG/JPEG via load_image (may write a normalized RGB copy)."""
    try:
        loaded = load_image(file_path)
    except (UnsupportedFormatError, CorruptImageError, ImageProcessingError):
        raise
    except Exception as exc:  # noqa: BLE001
        raise ImageProcessingError(f"Failed to load raster image: {exc}") from exc

    logger.info(
        "[%s] image dimensions: source %sx%s (%s)",
        document_id,
        loaded["width"],
        loaded["height"],
        loaded["format"],
    )
    return [loaded["image_path"]]


def _validation_error_code(message: str) -> str:
    """Map validator text to a stable error code (no file contents logged)."""
    lower = message.lower()
    if "unsupported file type" in lower:
        return UnsupportedFormatError.code
    if "empty" in lower:
        return "EMPTY_FILE"
    if "does not exist" in lower:
        return "FILE_NOT_FOUND"
    if "not a valid pdf" in lower or "not a pdf" in lower:
        return InvalidPDFError.code
    if "not a png" in lower or "not a jpeg" in lower or "valid" in lower:
        return CorruptImageError.code
    return "VALIDATION_FAILED"


def _new_document_id(output_root: Path) -> str:
    """Generate a unique document_id whose folder does not yet exist."""
    for _ in range(16):
        candidate = f"doc_{uuid4().hex[:8]}"
        if not (output_root / candidate).exists():
            return candidate
    return f"doc_{uuid4().hex}"


def _suffix_type(path: Path) -> str:
    return path.suffix.lower().lstrip(".") or "unknown"


def _public_path(path: Path) -> str:
    """Prefer a stable path relative to the document-processor package root."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(_PACKAGE_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def _failed_document(
    *,
    document_id: str,
    original_filename: str,
    file_type: str,
    errors: list[ProcessingError],
) -> ProcessedDocument:
    return ProcessedDocument(
        document_id=document_id,
        original_filename=original_filename,
        file_type=file_type if file_type else "unknown",
        page_count=0,
        pages=[],
        status="failed",
        errors=errors,
    )


def _print_status(doc: ProcessedDocument) -> None:
    """Print a short human-readable processing summary."""
    print()
    print("=== BlueprintAI document-processor ===")
    print(f"document_id : {doc.document_id}")
    print(f"filename    : {doc.original_filename}")
    print(f"file_type   : {doc.file_type}")
    print(f"page_count  : {doc.page_count}")
    print(f"status      : {doc.status}")
    if doc.errors:
        print("errors:")
        for err in doc.errors:
            page = f" (page {err.page_number})" if err.page_number else ""
            print(f"  - [{err.code}]{page} {err.message}")
    for page in doc.pages:
        print(
            f"  {page.page_id}: {page.width}x{page.height} -> {page.image_path}"
        )
    print("=====================================")
    print()


def main(argv: list[str] | None = None) -> int:
    """
    CLI entrypoint:

      python processor.py samples/sample.pdf
      python processor.py samples/sample.pdf --isolate-regions
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="BlueprintAI Person 3 - preprocess engineering drawings.",
    )
    parser.add_argument(
        "file_path",
        help="Path to a PDF, PNG, or JPEG drawing",
    )
    parser.add_argument(
        "--isolate-regions",
        action="store_true",
        help="Crop drawing / title-block regions for each page",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show detailed processing logs",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    result = process_document(
        args.file_path,
        isolate_regions_enabled=args.isolate_regions,
    )
    _print_status(result)
    print(result.model_dump_json(indent=2))

    return 0 if result.status != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
