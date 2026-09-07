"""
pipeline.py -- orchestrates the BlueprintAI hybrid detection pipeline.

    ingest.py         (Stage 1: normalize PDF/image -> page images)
        |
    bom_extract.py     (Stage 2: deterministic BOM table -- ground truth)
        |
    callout_detect.py  (Stage 3: OpenCV balloon candidates + coordinates)
        |
    classify.py         (Stage 4: ONLY stage that calls Claude -- narrow
        |                 "is this a balloon, what number" per crop)
    reconcile.py         (Stage 5: pure-Python diff, for traceability)
        |
    intelligence.build_workspace(...)  (unchanged -- reuses the existing,
                                         already-tested validation/
                                         procurement/export logic so the
                                         external API contract is identical
                                         to the legacy vision-only pipeline)

``run_hybrid_pipeline`` is the single entry point run_pipeline.py calls
when PIPELINE_MODE=hybrid (the default -- see config.py). Its return
shape matches run_pipeline.run_pipeline()'s legacy-path shape field for
field, so app.py's /process route needs no changes.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parent.parent
_INTELLIGENCE_DIR = _REPO_ROOT / "intelligence"
if str(_REPO_ROOT) not in sys.path:
    # intelligence/ is a normal (non-hyphenated) package importable as
    # `intelligence.xxx` as long as the repo root is on sys.path.
    sys.path.insert(0, str(_REPO_ROOT))

if __package__:
    # Imported as backend.pipeline (the normal case). Branching on
    # __package__ rather than try/except ImportError matters here: ingest.py
    # imports document-processor at module load time, so a genuinely missing
    # third-party dependency (e.g. pdf2image) raises ModuleNotFoundError
    # *from inside* `from .ingest import ...` -- catching ImportError broadly
    # would swallow that real error and misreport it as "no module named
    # ingest" from the flat-import fallback below, hiding the actual cause.
    from . import bom_extract, callout_detect, classify, reconcile
    from .config import get_settings
    from .ingest import IngestedPage, ingest
else:  # flat imports when run as a standalone script from backend/
    import bom_extract
    import callout_detect
    import classify
    import reconcile
    from config import get_settings
    from ingest import IngestedPage, ingest

from intelligence import build_workspace  # noqa: E402 -- after sys.path bootstrap

_EMPTY_VALIDATION_SUMMARY = {
    "total_bom_items": 0,
    "total_callouts": 0,
    "linked_items": 0,
    "missing_callouts": 0,
    "missing_bom_items": 0,
    "low_confidence_items": 0,
    "duplicate_bom_items": 0,
    "duplicate_callouts": 0,
    "ambiguous_identifiers": 0,
    "review_required_items": 0,
    "invalid_items": 0,
    "confidence_threshold": None,
}


def _empty_workspace(pipeline_status: str, stage: str, message: str, **extra_metadata) -> dict:
    """Same JSON shape as run_pipeline._empty_workspace -- duplicated
    (not imported) so backend/pipeline.py has no dependency on
    run_pipeline.py and can be exercised in isolation (see spec: "each
    stage should be testable independently")."""
    return {
        "components": [],
        "validation": {"summary": dict(_EMPTY_VALIDATION_SUMMARY), "issues": []},
        "procurement_summary": {
            "currency": "USD",
            "estimated_total_cost_usd": 0.0,
            "items_with_price": 0,
            "items_without_price": 0,
        },
        "metadata": {
            "pipeline_status": pipeline_status,
            "pipeline_errors": [{"stage": stage, "message": message}],
            "pipeline_mode": "hybrid",
            "extraction_source": extra_metadata.pop("extraction_source", None),
            "using_mock_vision_extraction": extra_metadata.pop(
                "using_mock_vision_extraction", False
            ),
            **extra_metadata,
        },
    }


def _bbox_px_to_full_page_norm(
    bbox_px: dict,
    *,
    crop_origin_x_px: float,
    crop_origin_y_px: float,
    full_page_width_px: float,
    full_page_height_px: float,
) -> dict:
    """Convert a callout_detect.py pixel bbox (relative to whatever image
    it was actually run on -- a drawing-region crop, or the full page) to
    full-page normalized 0-1000, the coordinate system the frontend
    expects (see contracts/README.md and BlueprintOverlay.jsx)."""

    def _axis(value_px: float, origin_px: float, page_size_px: float) -> float:
        page_px = origin_px + value_px
        return max(0.0, min(1000.0, (page_px / page_size_px) * 1000.0))

    return {
        "xmin": _axis(bbox_px["xmin"], crop_origin_x_px, full_page_width_px),
        "ymin": _axis(bbox_px["ymin"], crop_origin_y_px, full_page_height_px),
        "xmax": _axis(bbox_px["xmax"], crop_origin_x_px, full_page_width_px),
        "ymax": _axis(bbox_px["ymax"], crop_origin_y_px, full_page_height_px),
    }


def _bom_row_to_bom_data(row: dict) -> dict:
    """bom_extract.py's ``{item_no, description, qty, material}`` ->
    intelligence's ``{item_number, quantity, material_specification,
    description, ...}`` contract shape (contracts/README.md)."""
    return {
        "item_number": row.get("item_no"),
        "part_number": None,
        "part_name": None,
        "description": row.get("description") or "",
        "quantity": row.get("qty"),
        "material_specification": row.get("material"),
        "confidence_score": None,
    }


def _classification_to_callout_data(
    result, candidate, *, region_origin_px: tuple[float, float], full_page_size_px: tuple[float, float]
) -> Optional[dict]:
    """classify.ClassificationResult + callout_detect.CalloutCandidate ->
    intelligence's callout_data contract shape. Returns None for
    non-balloons (nothing to reconcile against)."""
    if not result.is_balloon or result.number is None:
        return None
    crop_origin_x, crop_origin_y = region_origin_px
    full_page_width, full_page_height = full_page_size_px
    bbox_norm = _bbox_px_to_full_page_norm(
        candidate.bbox,
        crop_origin_x_px=crop_origin_x,
        crop_origin_y_px=crop_origin_y,
        full_page_width_px=full_page_width,
        full_page_height_px=full_page_height,
    )
    return {
        "bubble_number": str(result.number),
        "location_description": "",
        "bounding_box": bbox_norm,
        "confidence_score": result.confidence,
    }


def _crop_origin_px(page: IngestedPage, used_drawing_region: bool) -> tuple[float, float]:
    """Pixel-space origin, on the full page, of whichever image
    callout_detect.py actually ran on."""
    if not used_drawing_region or page.drawing_region is None:
        return (0.0, 0.0)
    region = page.drawing_region
    return (
        (region["xmin"] / 1000.0) * page.width,
        (region["ymin"] / 1000.0) * page.height,
    )


def run_hybrid_pipeline(
    file_path: str,
    *,
    procurement_data: Optional[dict] = None,
    confidence_threshold: Optional[float] = None,
) -> dict:
    """Run the hybrid detection pipeline on one engineering drawing.

    Deterministic CV/OCR (bom_extract, callout_detect) + narrowly-scoped
    Claude classification (classify) + pure-Python reconciliation
    (reconcile) -> intelligence.build_workspace(...) for the same
    validation/procurement/export logic the legacy pipeline already used.

    Never raises -- mirrors run_pipeline.run_pipeline()'s contract: any
    failure produces a valid (possibly empty) workspace with the failure
    explained in ``metadata.pipeline_errors``.
    """
    if not file_path or not isinstance(file_path, str):
        return _empty_workspace(
            "failed", "input", f"file_path must be a non-empty string, got: {file_path!r}"
        )

    settings = get_settings()

    # --- Stage 1: Ingest -----------------------------------------------
    try:
        doc = ingest(file_path, isolate_regions_enabled=True)
    except Exception as exc:  # noqa: BLE001 -- never let an upstream bug crash the caller
        return _empty_workspace(
            "failed",
            "document_processing",
            f"Unexpected error: {exc}",
            original_filename=Path(file_path).name,
        )

    if doc.status == "failed" or not doc.pages:
        messages = [f"[{e.get('code')}] {e.get('message')}" for e in doc.errors] or [
            "Document processing produced no pages"
        ]
        return _empty_workspace(
            "failed",
            "document_processing",
            "; ".join(messages),
            document_id=doc.document_id,
            original_filename=doc.original_filename,
        )

    all_bom_data: list[dict] = []
    all_callout_data: list[dict] = []
    raw_bom_rows: list[dict] = []
    raw_balloon_results: list[dict] = []
    pipeline_errors: list[dict] = []
    total_candidates = 0
    total_balloons = 0

    for page in doc.pages:
        # --- Stage 2: deterministic BOM extraction ----------------------
        bom_image_target = page.title_block_region_path or page.image_path
        try:
            bom_rows = bom_extract.extract_bom(file_path, page.page_number, bom_image_target)
        except Exception as exc:  # noqa: BLE001
            pipeline_errors.append(
                {"stage": "bom_extract", "message": f"{page.page_id}: {exc}"}
            )
            bom_rows = []
        raw_bom_rows.extend(bom_rows)
        all_bom_data.extend(_bom_row_to_bom_data(row) for row in bom_rows)

        # --- Stage 3: OpenCV callout candidate detection -----------------
        used_drawing_region = bool(page.drawing_region_path)
        callout_image_target = page.drawing_region_path or page.image_path
        try:
            candidates = callout_detect.detect_callouts(callout_image_target, page_id=page.page_id)
        except Exception as exc:  # noqa: BLE001
            pipeline_errors.append(
                {"stage": "callout_detect", "message": f"{page.page_id}: {exc}"}
            )
            candidates = []
        total_candidates += len(candidates)

        # --- Stage 4: Claude classifies each crop (only stage that calls
        # the API; never sees the full page, never returns coordinates) --
        try:
            classifications = classify.classify_candidates(candidates)
        except Exception as exc:  # noqa: BLE001
            pipeline_errors.append({"stage": "classify", "message": f"{page.page_id}: {exc}"})
            classifications = []

        crop_origin_px = _crop_origin_px(page, used_drawing_region)
        by_crop_id = {c.crop_id: c for c in candidates}
        for result in classifications:
            candidate = by_crop_id.get(result.crop_id)
            if candidate is None:
                continue
            raw_balloon_results.append(
                {
                    "crop_id": result.crop_id,
                    "is_balloon": result.is_balloon,
                    "number": result.number,
                    "confidence": result.confidence,
                }
            )
            if result.is_balloon:
                total_balloons += 1
            callout_row = _classification_to_callout_data(
                result,
                candidate,
                region_origin_px=crop_origin_px,
                full_page_size_px=(page.width, page.height),
            )
            if callout_row is not None:
                all_callout_data.append(callout_row)

    # --- Stage 5: pure-Python reconciliation (traceability only -- the
    # actual component list the frontend consumes comes from
    # intelligence.build_workspace below, which reconciles the same data
    # via its own, already-tested reconcile_bom_and_callouts) -----------
    hybrid_reconciliation = reconcile.reconcile(raw_bom_rows, raw_balloon_results)

    if not all_bom_data and not all_callout_data:
        pipeline_errors.append(
            {"stage": "hybrid_pipeline", "message": "No BOM items or callouts were extracted"}
        )

    # --- intelligence: reconciliation, validation, procurement ----------
    build_kwargs = {}
    if confidence_threshold is not None:
        build_kwargs["confidence_threshold"] = confidence_threshold

    try:
        workspace = build_workspace(
            bom_data=all_bom_data,
            callout_data=all_callout_data,
            procurement_data=procurement_data,
            **build_kwargs,
        )
    except Exception as exc:  # noqa: BLE001 -- last-resort guard
        return _empty_workspace(
            "failed",
            "intelligence",
            f"Unexpected error: {exc}",
            document_id=doc.document_id,
            original_filename=doc.original_filename,
        )

    status = "ok" if not pipeline_errors else "partial"
    workspace["metadata"].update(
        {
            "pipeline_status": status,
            "pipeline_errors": pipeline_errors,
            "pipeline_mode": "hybrid",
            "document_id": doc.document_id,
            "original_filename": doc.original_filename,
            "pages_processed": len(doc.pages),
            "drawing_number": None,
            "revision": None,
            "extraction_source": "hybrid_cv_ocr_claude",
            "using_mock_vision_extraction": settings.use_mock_classify,
            "extraction_warnings": [],
            "hybrid_stage_counts": {
                "bom_rows_extracted": len(raw_bom_rows),
                "callout_candidates_detected": total_candidates,
                "classified_as_balloons": total_balloons,
            },
            "hybrid_reconciliation": hybrid_reconciliation,
        }
    )

    logger.info(
        "[pipeline] %s: reconciliation result: %s",
        doc.document_id,
        {k: len(v) for k, v in hybrid_reconciliation.items()},
    )
    return workspace
