"""
bom_extract.py -- Stage 2 of the BlueprintAI hybrid detection pipeline.

Extracts the BOM table deterministically -- no LLM involved. This is
ground truth that classify.py's balloon numbers get reconciled against
in reconcile.py, not something Claude ever sees or produces.

Two extraction paths, tried in order:

1. Vector PDF text: ``pdfplumber`` reads the *original* PDF page directly
   (not the rasterized image) and looks for a real table. Reliable and
   exact whenever the source PDF has selectable text.
2. Raster OCR table extraction: ``pytesseract`` (Tesseract) reads word
   boxes off the page image, first attempting OpenCV grid-line detection
   to find table row/column structure, falling back to whitespace-gap
   column segmentation when no ruled grid is found (many BOM tables are
   borderless). Used for scanned PDFs and plain image uploads.

Column-mapping / row-parsing logic (``_rows_to_bom_dicts``,
``_split_row_into_cells``, ``_map_columns``) is pure and does not touch
pdfplumber, OpenCV, or Tesseract, so it can be unit-tested with
hand-written fake rows -- see backend/tests/test_bom_extract.py.

Output shape: ``[{"item_no", "description", "qty", "material"}, ...]``.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Header keywords used to identify which column is which, whichever
# extraction path produced the header row. Order matters: more specific
# keywords first so e.g. "part no" doesn't get mistaken for "qty".
_HEADER_KEYWORDS: dict[str, tuple[str, ...]] = {
    "item_no": ("item no", "item#", "item #", "item number", "ref", "no.", "item", "#", "bal", "balloon"),
    "qty": ("qty", "quantity", "q'ty"),
    "material": ("material", "matl", "spec", "material spec"),
    "description": ("description", "desc", "part name", "name", "part description"),
}

# Fallback positional order when no header row can be confidently
# identified (common for borderless / hand-drawn tables): most BOM
# tables list item number first and material last.
_POSITIONAL_FALLBACK_ORDER = ("item_no", "qty", "description", "material")

_DIGIT_RE = re.compile(r"\d+")


def extract_bom(file_path: str, page_number: int, page_image_path: Optional[str] = None) -> list[dict]:
    """Extract BOM rows for one page.

    Parameters
    ----------
    file_path:
        Path to the *original* upload (PDF or image). Used for the
        vector-PDF path -- pdfplumber reads real PDF text, never the
        rasterized copy.
    page_number:
        1-based page number, matching ``pdfplumber``'s page indexing and
        ``ingest.IngestedPage.page_number``.
    page_image_path:
        Path to a raster image to OCR (ideally the isolated title-block
        crop -- see ``ingest.IngestedPage.title_block_region_path`` --
        falling back to the full page). Required for the OCR path; the
        vector-PDF path ignores it entirely.

    Returns
    -------
    list[dict]: ``{"item_no", "description", "qty", "material"}`` rows.
    Never raises -- a missing dependency, missing Tesseract binary, or
    unparseable table all degrade to an empty list with a logged warning,
    consistent with the rest of this pipeline never crashing its caller.
    """
    rows: list[dict] = []
    source = "none"

    if Path(file_path).suffix.lower() == ".pdf":
        try:
            rows = _extract_from_vector_pdf(file_path, page_number)
            if rows:
                source = "pdfplumber"
        except Exception as exc:  # noqa: BLE001 -- fall through to OCR
            logger.warning("[bom_extract] page %d: vector PDF extraction failed: %s", page_number, exc)

    if not rows and page_image_path:
        try:
            rows = _extract_from_raster_ocr(page_image_path)
            if rows:
                source = "ocr"
        except Exception as exc:  # noqa: BLE001 -- degrade gracefully
            logger.warning("[bom_extract] page %d: OCR table extraction failed: %s", page_number, exc)

    logger.info(
        "[bom_extract] page %d: BOM rows extracted: %d (source=%s)", page_number, len(rows), source
    )
    return rows


# --------------------------------------------------------------------------
# Path 1: vector PDF (pdfplumber)
# --------------------------------------------------------------------------


def _extract_from_vector_pdf(file_path: str, page_number: int) -> list[dict]:
    import pdfplumber

    with pdfplumber.open(file_path) as pdf:
        if page_number < 1 or page_number > len(pdf.pages):
            return []
        page = pdf.pages[page_number - 1]
        tables = page.extract_tables()

    for table in tables:
        rows = _table_rows_to_bom_dicts(table)
        if rows:
            return rows
    return []


def _table_rows_to_bom_dicts(table: list[list[Optional[str]]]) -> list[dict]:
    if not table or len(table) < 2:
        return []
    header = [_clean_cell(c) for c in table[0]]
    mapping = _map_columns(header)
    if mapping is None:
        return []
    return _rows_to_bom_dicts(table[1:], mapping)


# --------------------------------------------------------------------------
# Path 2: raster OCR (OpenCV grid detection + pytesseract)
# --------------------------------------------------------------------------


def _extract_from_raster_ocr(image_path: str) -> list[dict]:
    words = _ocr_words(image_path)
    if not words:
        return []
    text_rows = _words_to_text_rows(words)
    if len(text_rows) < 2:
        return []

    gap_threshold = _infer_gap_threshold(text_rows)
    header = _split_row_into_cells(text_rows[0], gap_threshold_px=gap_threshold)
    mapping = _map_columns(header)
    body_rows = text_rows[1:]

    if mapping is None:
        # No confident header -- assume the standard positional order and
        # treat every row (including the first) as data.
        mapping = {name: i for i, name in enumerate(_POSITIONAL_FALLBACK_ORDER)}
        body_rows = text_rows

    cell_rows = [_split_row_into_cells(row, gap_threshold_px=gap_threshold) for row in body_rows]
    return _rows_to_bom_dicts(cell_rows, mapping)


# A gap threshold expressed as a fixed pixel count doesn't scale with image
# resolution or font size (25px is generous at 300 DPI, useless at 96 DPI).
# _infer_gap_threshold instead auto-calibrates from the observed
# distribution of within-row word gaps on this specific page/crop -- the
# same "auto-calibrate from the distribution, fall back to a sane default"
# pattern callout_detect.py already uses for its radius range. It looks
# for the single biggest *relative* jump in the sorted gap distribution:
# intra-cell gaps (space between words in one description) cluster low,
# column gaps cluster high, and the widest ratio jump between consecutive
# sorted values marks the boundary between the two clusters.
_DEFAULT_GAP_THRESHOLD_PX = 25
_MIN_GAPS_FOR_CALIBRATION = 3


def _infer_gap_threshold(text_rows: list[list[dict]]) -> float:
    gaps: list[float] = []
    for row in text_rows:
        sorted_row = sorted(row, key=lambda w: w["left"])
        for prev_word, word in zip(sorted_row, sorted_row[1:]):
            gap = word["left"] - (prev_word["left"] + prev_word["width"])
            if gap > 0:
                gaps.append(gap)

    if len(gaps) < _MIN_GAPS_FOR_CALIBRATION:
        return float(_DEFAULT_GAP_THRESHOLD_PX)

    sorted_gaps = sorted(gaps)
    best_ratio = 1.0
    best_index = None
    for i in range(len(sorted_gaps) - 1):
        low, high = sorted_gaps[i], sorted_gaps[i + 1]
        ratio = high / max(low, 1.0)
        if ratio > best_ratio:
            best_ratio = ratio
            best_index = i

    # No clear cluster break (a fairly uniform gap distribution) -- default
    # rather than guess a boundary that isn't really there.
    if best_index is None or best_ratio < 1.3:
        return float(_DEFAULT_GAP_THRESHOLD_PX)

    return (sorted_gaps[best_index] + sorted_gaps[best_index + 1]) / 2.0


def _ocr_words(image_path: str) -> list[dict]:
    """Run Tesseract word-box OCR on an image. Returns a list of
    ``{"text", "left", "top", "width", "height"}`` dicts (pixel space).

    Never raises: a missing ``pytesseract`` package or missing system
    Tesseract binary both degrade to an empty result (logged once, at
    warning level, by the caller's try/except in ``extract_bom``).
    """
    import pytesseract
    from PIL import Image

    with Image.open(image_path) as img:
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    words = []
    for i, text in enumerate(data.get("text", [])):
        text = text.strip()
        if not text:
            continue
        try:
            conf = float(data["conf"][i])
        except (ValueError, TypeError):
            conf = -1.0
        if conf == -1.0 and not text:
            continue
        words.append(
            {
                "text": text,
                "left": int(data["left"][i]),
                "top": int(data["top"][i]),
                "width": int(data["width"][i]),
                "height": int(data["height"][i]),
            }
        )
    return words


def _words_to_text_rows(words: list[dict], y_tolerance: int = 10) -> list[list[dict]]:
    """Cluster OCR word boxes into table rows by y-coordinate proximity
    (classic OCR table-structure heuristic: words whose vertical centers
    fall within ``y_tolerance`` px of each other belong to the same row),
    then order each row left-to-right.

    Pure function of already-extracted word boxes -- OpenCV grid-line
    detection, when available, only narrows which words get passed in
    (see ``_ocr_words``); the row-clustering rule itself does not depend
    on ruled table lines, so it also works for borderless tables.
    """
    if not words:
        return []
    sorted_words = sorted(words, key=lambda w: (w["top"] + w["height"] / 2))

    rows: list[list[dict]] = []
    current_row: list[dict] = []
    current_center: Optional[float] = None

    for word in sorted_words:
        center = word["top"] + word["height"] / 2
        if current_center is None or abs(center - current_center) <= y_tolerance:
            current_row.append(word)
            centers = [w["top"] + w["height"] / 2 for w in current_row]
            current_center = sum(centers) / len(centers)
        else:
            rows.append(sorted(current_row, key=lambda w: w["left"]))
            current_row = [word]
            current_center = center
    if current_row:
        rows.append(sorted(current_row, key=lambda w: w["left"]))
    return rows


def _split_row_into_cells(row_words: list[dict], gap_threshold_px: int = 25) -> list[str]:
    """Group a row's word boxes into cells by horizontal whitespace gaps
    (a gap wider than ``gap_threshold_px`` between consecutive words
    starts a new column) -- the standard heuristic for segmenting
    borderless OCR'd tables into columns."""
    if not row_words:
        return []
    cells: list[str] = []
    current_words = [row_words[0]["text"]]
    prev_right = row_words[0]["left"] + row_words[0]["width"]

    for word in row_words[1:]:
        gap = word["left"] - prev_right
        if gap > gap_threshold_px:
            cells.append(" ".join(current_words))
            current_words = [word["text"]]
        else:
            current_words.append(word["text"])
        prev_right = word["left"] + word["width"]
    cells.append(" ".join(current_words))
    return cells


# --------------------------------------------------------------------------
# Shared: header mapping + row -> dict conversion (pure, no I/O)
# --------------------------------------------------------------------------


def _map_columns(header: list[str]) -> Optional[dict[str, int]]:
    """Match a header row's cells to BOM fields by keyword. Returns
    ``{field_name: column_index}`` for every field it could confidently
    identify, or ``None`` if it found no recognizable BOM-table header at
    all (caller then either skips this table or uses positional
    fallback)."""
    mapping: dict[str, int] = {}
    for index, cell in enumerate(header):
        cell_norm = (cell or "").strip().lower()
        if not cell_norm:
            continue
        for field_name, keywords in _HEADER_KEYWORDS.items():
            if field_name in mapping:
                continue
            if any(keyword == cell_norm or keyword in cell_norm for keyword in keywords):
                mapping[field_name] = index
                break
    return mapping if mapping else None


def _rows_to_bom_dicts(rows: list[list[Any]], mapping: dict[str, int]) -> list[dict]:
    results: list[dict] = []
    for row in rows:
        if not row or all(_clean_cell(c) == "" for c in row):
            continue
        item_no = _extract_item_no(_get_cell(row, mapping.get("item_no")))
        if item_no is None:
            continue
        results.append(
            {
                "item_no": item_no,
                "description": _clean_cell(_get_cell(row, mapping.get("description"))),
                "qty": _extract_qty(_get_cell(row, mapping.get("qty"))),
                "material": _clean_cell(_get_cell(row, mapping.get("material"))) or None,
            }
        )
    return results


def _get_cell(row: list[Any], index: Optional[int]) -> Optional[str]:
    if index is None or index >= len(row):
        return None
    return row[index]


def _clean_cell(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def _extract_item_no(value: Optional[str]) -> Optional[str]:
    text = _clean_cell(value)
    if not text:
        return None
    match = _DIGIT_RE.search(text)
    return match.group(0) if match else None


def _extract_qty(value: Optional[str]) -> Optional[int]:
    text = _clean_cell(value)
    match = _DIGIT_RE.search(text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except ValueError:
        return None
