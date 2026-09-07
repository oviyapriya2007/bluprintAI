"""BlueprintAI end-to-end backend pipeline entry point.

Not owned by a single person's module -- lives at the project root and
wires the three backend stages together without modifying any of them:

    document-processor (Person 3)
            |  ProcessedDocument (page images + metadata)
            v
    vision-extractor (Person 4)
            |  BOM items + drawing callouts
            v
    intelligence (Person 5)
            |  reconciliation -> validation -> procurement
            v
    workspace JSON  (ready for the UI / Excel / CSV export)

Usage
-----
As a library::

    from run_pipeline import run_pipeline
    workspace = run_pipeline("path/to/drawing.pdf")

From the command line::

    .venv\\Scripts\\python.exe run_pipeline.py path/to/drawing.png
    .venv\\Scripts\\python.exe run_pipeline.py path/to/drawing.pdf --excel out.xlsx --csv out.csv

`document-processor` and `vision-extractor` use hyphenated directory names,
which are not valid Python package names, so their code is not written to
be imported as `document_processor.xxx` / normal dotted packages. Both
modules already support being imported "flat" (see the `except ImportError`
fallback in document-processor/processor.py, and vision-extractor's inner
`vision_extractor/` package). This file adds each directory to `sys.path`
at runtime -- the smallest change that lets both be imported without
touching a single line of either module.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_ROOT = Path(__file__).resolve().parent
_DOCUMENT_PROCESSOR_DIR = _ROOT / "document-processor"
_VISION_EXTRACTOR_DIR = _ROOT / "vision-extractor"

for _dir in (_DOCUMENT_PROCESSOR_DIR, _VISION_EXTRACTOR_DIR):
    _dir_str = str(_dir)
    if _dir.is_dir() and _dir_str not in sys.path:
        sys.path.insert(0, _dir_str)

from intelligence import build_workspace  # noqa: E402 (path bootstrap must run first)

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
    """A JSON-serializable, correctly-shaped workspace for a hard failure.

    Every module in this pipeline is designed to never crash its caller on
    bad input -- a bad drawing should produce a clear, inspectable result,
    not an exception the UI has to catch. This keeps that promise at the
    top level too.
    """
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
            **extra_metadata,
        },
    }


def _resolve_page_path(relative_path: Optional[str]) -> Optional[Path]:
    """Resolve a Person-3-reported page/region path (relative to the
    document-processor package root -- see processor.py's ``_public_path``)
    to an absolute Path, or None if the region wasn't produced."""
    if not relative_path:
        return None
    return _DOCUMENT_PROCESSOR_DIR / relative_path


def _remap_bbox_to_full_page(bbox: dict, region) -> dict:
    """Remap a bounding box that Gemini reported normalized (0-1000) to an
    isolated *crop* back into the full page's own 0-1000 normalized space.

    vision-extractor always normalizes coordinates to the image it was
    actually shown (see vision-extractor/README.md's coordinate-system
    section). When that image is a drawing-region crop rather than the
    whole page, a callout's raw coordinates are relative to the crop, not
    the page -- ``region`` (the crop's own 0-1000 full-page-relative
    position, from document-processor's ProcessedPage.drawing_region) is
    what lets us convert one into the other.
    """
    region_w = region.xmax - region.xmin
    region_h = region.ymax - region.ymin
    return {
        "xmin": region.xmin + (bbox["xmin"] / 1000) * region_w,
        "ymin": region.ymin + (bbox["ymin"] / 1000) * region_h,
        "xmax": region.xmin + (bbox["xmax"] / 1000) * region_w,
        "ymax": region.ymin + (bbox["ymax"] / 1000) * region_h,
    }


def run_pipeline(
    file_path: str,
    *,
    isolate_regions: bool = True,
    procurement_data: Optional[dict] = None,
    confidence_threshold: Optional[float] = None,
) -> dict:
    """Run the full backend pipeline on one engineering drawing.

    Document Processor -> Vision Extractor -> Intelligence (reconciliation,
    validation, procurement) -> workspace JSON.

    Parameters
    ----------
    file_path:
        Path to a PDF, PNG, or JPEG engineering drawing.
    isolate_regions:
        Forwarded to Person 3's ``process_document`` (crops drawing /
        title-block regions per page). On by default: when both crops are
        produced, BOM extraction runs against the title-block crop and
        callout detection runs against the drawing-region crop instead of
        the whole page, so the (usually small) BOM table isn't shrunk into
        illegibility alongside the rest of a large-format sheet. Costs one
        extra pair of Gemini calls per page (extract_from_image() is called
        twice instead of once); falls back to the single-whole-page call
        automatically for any page where region isolation didn't produce
        both crops.
    procurement_data:
        Optional catalog overrides forwarded to Person 5's
        ``build_workspace``.
    confidence_threshold:
        Optional override for the low-confidence review threshold.

    Returns
    -------
    dict
        The same shape as ``intelligence.build_workspace(...)`` --
        ``{"components", "validation", "procurement_summary", "metadata"}``
        -- with ``metadata`` additionally carrying pipeline-level fields:
        ``pipeline_status`` (``"ok"`` | ``"partial"`` | ``"failed"``),
        ``pipeline_errors``, ``document_id``, ``original_filename``,
        ``pages_processed``, ``drawing_number``, ``revision``,
        ``using_mock_vision_extraction``, and ``extraction_warnings``.

    Never raises. A missing/corrupt/unsupported file, empty extraction, or
    an unexpected error in either upstream stage all produce a valid
    (possibly empty) workspace with the failure explained in
    ``metadata.pipeline_errors`` -- never an exception.
    """
    if not file_path or not isinstance(file_path, str):
        return _empty_workspace(
            "failed", "input", f"file_path must be a non-empty string, got: {file_path!r}"
        )

    try:
        from processor import process_document
    except ImportError as exc:
        return _empty_workspace(
            "failed", "document_processing", f"Could not import document-processor: {exc}"
        )

    try:
        from vision_extractor import VisionExtractor
    except ImportError as exc:
        return _empty_workspace(
            "failed", "vision_extraction", f"Could not import vision-extractor: {exc}"
        )

    # --- Stage 1: Document Processing (Person 3) ----------------------------
    try:
        processed_doc = process_document(file_path, isolate_regions_enabled=isolate_regions)
    except Exception as exc:  # noqa: BLE001 -- never let an upstream bug crash the caller
        return _empty_workspace(
            "failed",
            "document_processing",
            f"Unexpected error: {exc}",
            original_filename=Path(file_path).name,
        )

    if processed_doc.status == "failed" or not processed_doc.pages:
        messages = [f"[{e.code}] {e.message}" for e in processed_doc.errors] or [
            "Document processing produced no pages"
        ]
        return _empty_workspace(
            "failed",
            "document_processing",
            "; ".join(messages),
            document_id=processed_doc.document_id,
            original_filename=processed_doc.original_filename,
        )

    # --- Stage 2: Vision Extraction (Person 4) ------------------------------
    extractor = VisionExtractor()
    all_bom_items: list[dict] = []
    all_callouts: list[dict] = []
    extraction_warnings: list[str] = []
    pipeline_errors: list[dict] = []
    drawing_number: Optional[str] = None
    revision: Optional[str] = None

    for page in processed_doc.pages:
        title_block_path = _resolve_page_path(page.title_block_region_path)
        drawing_region_path = _resolve_page_path(page.drawing_region_path)

        if title_block_path and drawing_region_path:
            # Isolated regions available: route BOM extraction to the
            # title-block crop and callout detection to the drawing-region
            # crop, so each Gemini call sees its target content at a much
            # higher effective resolution than a single downscaled full page.
            try:
                title_result = extractor.extract_from_image(str(title_block_path))
                title_data = title_result.model_dump()
                all_bom_items.extend(title_data["bom_items"])
                extraction_warnings.extend(
                    f"{page.page_id} (title block): {warning}"
                    for warning in title_data["extraction_warnings"]
                )
                drawing_number = drawing_number or title_data.get("drawing_number")
                revision = revision or title_data.get("revision")
            except Exception as exc:  # noqa: BLE001 -- never trust an upstream call blindly
                pipeline_errors.append(
                    {
                        "stage": "vision_extraction",
                        "message": f"{page.page_id} title-block extraction failed: {exc}",
                    }
                )

            try:
                drawing_result = extractor.extract_from_image(str(drawing_region_path))
                drawing_data = drawing_result.model_dump()
                callouts = drawing_data["callouts"]
                # Mock mode ignores whatever image it's given and always
                # returns the same canned, already-full-page-relative
                # coordinates -- remapping those would corrupt them. Only
                # real Gemini output is genuinely crop-relative.
                if not extractor.using_mock and page.drawing_region is not None:
                    for callout in callouts:
                        if callout.get("bounding_box"):
                            callout["bounding_box"] = _remap_bbox_to_full_page(
                                callout["bounding_box"], page.drawing_region
                            )
                all_callouts.extend(callouts)
                extraction_warnings.extend(
                    f"{page.page_id} (drawing region): {warning}"
                    for warning in drawing_data["extraction_warnings"]
                )
            except Exception as exc:  # noqa: BLE001
                pipeline_errors.append(
                    {
                        "stage": "vision_extraction",
                        "message": f"{page.page_id} drawing-region extraction failed: {exc}",
                    }
                )
            continue

        # Fallback: no isolated regions for this page -- extract from the
        # whole normalized page image, as before.
        image_path = _DOCUMENT_PROCESSOR_DIR / page.image_path
        try:
            result = extractor.extract_from_image(str(image_path))
        except Exception as exc:  # noqa: BLE001
            pipeline_errors.append(
                {"stage": "vision_extraction", "message": f"{page.page_id}: {exc}"}
            )
            continue

        data = result.model_dump()
        all_bom_items.extend(data["bom_items"])
        all_callouts.extend(data["callouts"])
        extraction_warnings.extend(
            f"{page.page_id}: {warning}" for warning in data["extraction_warnings"]
        )
        drawing_number = drawing_number or data.get("drawing_number")
        revision = revision or data.get("revision")

    if not all_bom_items and not all_callouts:
        pipeline_errors.append(
            {"stage": "vision_extraction", "message": "No BOM items or callouts were extracted"}
        )

    # --- Stage 3: Intelligence -- reconciliation, validation, procurement --
    build_kwargs = {}
    if confidence_threshold is not None:
        build_kwargs["confidence_threshold"] = confidence_threshold

    try:
        workspace = build_workspace(
            bom_data=all_bom_items,
            callout_data=all_callouts,
            procurement_data=procurement_data,
            **build_kwargs,
        )
    except Exception as exc:  # noqa: BLE001 -- last-resort guard; intelligence validates its own input
        return _empty_workspace(
            "failed",
            "intelligence",
            f"Unexpected error: {exc}",
            document_id=processed_doc.document_id,
            original_filename=processed_doc.original_filename,
        )

    status = "ok" if not pipeline_errors else "partial"
    workspace["metadata"].update(
        {
            "pipeline_status": status,
            "pipeline_errors": pipeline_errors,
            "document_id": processed_doc.document_id,
            "original_filename": processed_doc.original_filename,
            "pages_processed": len(processed_doc.pages),
            "drawing_number": drawing_number,
            "revision": revision,
            "using_mock_vision_extraction": extractor.using_mock,
            "extraction_warnings": extraction_warnings,
        }
    )
    return workspace


def main(argv: Optional[list[str]] = None) -> int:
    """CLI: run the pipeline on one drawing and print a summary + workspace JSON."""
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description="BlueprintAI end-to-end pipeline: drawing -> workspace JSON.",
    )
    parser.add_argument("file_path", help="Path to a PDF, PNG, or JPEG engineering drawing")
    parser.add_argument(
        "--no-isolate-regions",
        dest="isolate_regions",
        action="store_false",
        default=True,
        help="Disable title-block/drawing-region cropping; extract from the whole page instead",
    )
    parser.add_argument("--excel", metavar="PATH", help="Also write an Excel workbook to PATH")
    parser.add_argument("--csv", metavar="PATH", help="Also write a CSV file to PATH")
    parser.add_argument(
        "--json-only", action="store_true", help="Print only the workspace JSON (no summary)"
    )
    args = parser.parse_args(argv)

    workspace = run_pipeline(args.file_path, isolate_regions=args.isolate_regions)
    metadata = workspace["metadata"]

    if not args.json_only:
        print()
        print("=== BlueprintAI pipeline ===")
        print(f"pipeline_status : {metadata.get('pipeline_status')}")
        print(f"document_id     : {metadata.get('document_id')}")
        print(f"drawing_number  : {metadata.get('drawing_number')}")
        print(f"components      : {len(workspace['components'])}")
        print(f"validation      : {workspace['validation']['summary']}")
        print(f"procurement     : {workspace['procurement_summary']}")
        if metadata.get("pipeline_errors"):
            print("pipeline_errors :")
            for err in metadata["pipeline_errors"]:
                print(f"  - [{err['stage']}] {err['message']}")
        print("=============================")
        print()

    if args.excel:
        from intelligence import export_to_excel

        export_to_excel(workspace, args.excel)
        if not args.json_only:
            print(f"Excel written to {args.excel}")

    if args.csv:
        from intelligence import export_to_csv

        export_to_csv(workspace, args.csv)
        if not args.json_only:
            print(f"CSV written to {args.csv}")

    print(json.dumps(workspace, indent=2))
    return 0 if metadata.get("pipeline_status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
