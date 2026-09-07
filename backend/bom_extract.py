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

Output shape: ``[{"item_no", "description", "qty", "material", "part_number"}, ...]``
(``part_number`` is additive on top of the spec's original four fields --
harmless to ignore, and lets callers wire it through to
intelligence's procurement lookup, which is keyed by part number).
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
    "part_number": ("part number", "part no", "part#", "p/n"),
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
    """OCR the page for a BOM table, preferring an OpenCV-detected ruled
    table region over the whole page. A full engineering-drawing sheet is
    cluttered (dimension callouts, numbered general notes, other tables
    like the title block) -- OCRing all of it risks picking up unrelated
    numbered text (e.g. "1. ALL DIMENSIONS ARE...") as if it were a BOM
    row, and column boundaries are far less reliable across a wide mix of
    text than within one isolated table. Try the highest-row-count grid
    region(s) first (most likely the actual parts list, vs. e.g. the
    smaller title-block metadata grid); whole-page OCR is the last resort,
    for genuinely borderless/gridless tables only."""
    from PIL import Image

    with Image.open(image_path) as full_image:
        full_image = full_image.convert("RGB")
        for region in _find_table_regions(image_path):
            crop = full_image.crop((region["xmin"], region["ymin"], region["xmax"], region["ymax"]))
            rows = _parse_ocr_table(crop)
            if rows:
                return rows
        return _parse_ocr_table(full_image)


_MAX_HEADER_SEARCH_ROWS = 3


def _parse_ocr_table(image) -> list[dict]:
    words = _ocr_words(image)
    if not words:
        return []
    text_rows = _words_to_text_rows(words)
    if len(text_rows) < 2:
        return []

    gap_threshold = _infer_gap_threshold(text_rows)
    span_rows = [_split_row_into_cell_spans(row, gap_threshold_px=gap_threshold) for row in text_rows]
    cell_rows = [[span["text"] for span in spans] for spans in span_rows]

    # The header isn't always row 0 -- many parts-list tables have a
    # merged title row ("PARTS LIST") spanning the whole table above the
    # real column headers. Search the first few rows for whichever one
    # actually matches known header keywords, rather than assuming row 0.
    mapping = None
    header_index = None
    for i, cells in enumerate(cell_rows[:_MAX_HEADER_SEARCH_ROWS]):
        candidate_mapping = _map_columns(cells)
        if candidate_mapping is not None:
            mapping, header_index = candidate_mapping, i
            break

    if mapping is None:
        # No confident header found at all (e.g. a borderless table with
        # no header row) -- assume the standard positional order and
        # treat every row as data.
        mapping = {name: i for i, name in enumerate(_POSITIONAL_FALLBACK_ORDER)}
        body_cell_rows, body_span_rows = cell_rows, span_rows
    else:
        body_cell_rows = cell_rows[header_index + 1 :]
        body_span_rows = span_rows[header_index + 1 :]

    body_cell_rows = _refine_numeric_columns(image, body_cell_rows, body_span_rows, mapping)
    return _rows_to_bom_dicts(body_cell_rows, mapping)


# General-purpose OCR frequently misreads an isolated, context-free
# single/double-digit number -- e.g. Tesseract reading a lone "2" in a
# narrow ITEM column as "p3" -- since there's no surrounding word to
# disambiguate against. item_no and qty cells are known (from the header)
# to be purely numeric, so re-OCRing just those cells with a digit-only
# character whitelist removes that ambiguity entirely, at the cost of a
# few extra, cheap Tesseract calls (no Claude/network cost involved).
_NUMERIC_REFINEMENT_FIELDS = ("item_no", "qty")
_CELL_CROP_PADDING_PX = 4
_DIGIT_ONLY_CONFIG = "--psm 8 -c tessedit_char_whitelist=0123456789"


def _refine_numeric_columns(
    image, cell_rows: list[list[str]], span_rows: list[list[dict]], mapping: dict[str, int]
) -> list[list[str]]:
    """Return a copy of ``cell_rows`` with the item_no/qty columns
    replaced by a digit-only re-OCR of each cell's own crop, whenever that
    re-OCR yields a non-empty digit string. Never raises: any failure
    (missing pytesseract, an empty crop) just keeps the original
    general-OCR text for that cell."""
    refined_rows = [list(row) for row in cell_rows]
    for field in _NUMERIC_REFINEMENT_FIELDS:
        col_index = mapping.get(field)
        if col_index is None:
            continue
        for row_index, spans in enumerate(span_rows):
            if col_index >= len(spans) or col_index >= len(refined_rows[row_index]):
                continue
            span = spans[col_index]
            if not span["text"]:
                continue
            digits = _ocr_digits_only(image, span)
            if digits:
                refined_rows[row_index][col_index] = digits
    return refined_rows


def _ocr_digits_only(image, span: dict) -> Optional[str]:
    try:
        import pytesseract
    except ImportError:
        return None

    width, height = image.size
    box = (
        max(0, span["left"] - _CELL_CROP_PADDING_PX),
        max(0, span["top"] - _CELL_CROP_PADDING_PX),
        min(width, span["right"] + _CELL_CROP_PADDING_PX),
        min(height, span["bottom"] + _CELL_CROP_PADDING_PX),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        return None

    try:
        text = pytesseract.image_to_string(image.crop(box), config=_DIGIT_ONLY_CONFIG)
    except Exception:  # noqa: BLE001 -- refinement is best-effort only
        return None
    digits = re.sub(r"\D", "", text)
    return digits or None


# Locating the ruled table region before OCR (rather than reading the whole
# page) is what "table-structure detection" means here. A real table's row
# dividers all span the *same* left/right table boundary -- e.g. a 7-row,
# 5-column parts list has ~10 horizontal rule lines that all start and end
# at (nearly) the same x-coordinates, however wide the individual columns
# are. Dimension lines, leader lines, and view borders elsewhere on the
# sheet essentially never share an x-extent with several other lines by
# coincidence. So: find long horizontal line segments, group the ones that
# share an x-extent, and the biggest group is the table -- far more
# reliable than clustering on line unions or intersections, which either
# fuse unrelated elements together (columns vary too much in width for one
# dilation kernel to bridge) or miss real corners lost to JPEG/compression
# noise entirely.
_MIN_TABLE_ROWS = 3
_MIN_TABLE_WIDTH_FRACTION = 0.08
_MIN_TABLE_HEIGHT_FRACTION = 0.02
_SEGMENT_EXTENT_TOLERANCE_PX = 15


def _find_table_regions(image_path: str) -> list[dict]:
    """Detect ruled-table regions on a raster page. Returns
    ``[{"xmin","ymin","xmax","ymax","row_count"}, ...]`` sorted by
    row_count (really: matching-divider count) descending. Never raises:
    a missing OpenCV import, an unreadable image, or no matching group of
    dividers all just return an empty list, and the caller falls back to
    whole-page OCR."""
    try:
        import cv2
    except ImportError:
        return []

    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return []
    height, width = image.shape

    thresh = cv2.adaptiveThreshold(
        image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 15
    )
    horiz_len = max(15, width // 40)
    horiz_lines = cv2.morphologyEx(
        thresh, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (horiz_len, 1))
    )

    contours, _ = cv2.findContours(horiz_lines, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    segments = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if w < width * _MIN_TABLE_WIDTH_FRACTION:
            continue
        segments.append((x, y, w, h))

    return _group_segments_into_table_regions(segments, page_width=width, page_height=height)


def _group_segments_into_table_regions(
    segments: list[tuple[int, int, int, int]], *, page_width: int, page_height: int
) -> list[dict]:
    """Group horizontal line segments that share an x-extent (within
    _SEGMENT_EXTENT_TOLERANCE_PX), and turn each sufficiently large group
    into a candidate table region. Pure function of already-detected
    segments -- no OpenCV/image I/O -- so it's unit-testable directly."""
    groups: list[list[tuple[int, int, int, int]]] = []
    for seg in segments:
        x, y, w, h = seg
        x_end = x + w
        for group in groups:
            gx, gy, gw, gh = group[0]
            if abs(x - gx) <= _SEGMENT_EXTENT_TOLERANCE_PX and abs(x_end - (gx + gw)) <= _SEGMENT_EXTENT_TOLERANCE_PX:
                group.append(seg)
                break
        else:
            groups.append([seg])

    regions = []
    for group in groups:
        if len(group) < _MIN_TABLE_ROWS:
            continue
        xs = [g[0] for g in group]
        x_ends = [g[0] + g[2] for g in group]
        ys = [g[1] for g in group]
        y_ends = [g[1] + g[3] for g in group]
        xmin, ymin, xmax, ymax = min(xs), min(ys), max(x_ends), max(y_ends)
        if (ymax - ymin) < page_height * _MIN_TABLE_HEIGHT_FRACTION:
            continue
        regions.append({"xmin": xmin, "ymin": ymin, "xmax": xmax, "ymax": ymax, "row_count": len(group)})

    regions.sort(key=lambda r: r["row_count"], reverse=True)
    return regions


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


def _ocr_words(image) -> list[dict]:
    """Run Tesseract word-box OCR on an already-open PIL Image (a whole
    page, or a table-region crop -- see _extract_from_raster_ocr). Returns
    a list of ``{"text", "left", "top", "width", "height"}`` dicts,
    pixel-space relative to whatever image was passed in.

    Never raises: a missing ``pytesseract`` package or missing system
    Tesseract binary both degrade to an empty result (logged once, at
    warning level, by the caller's try/except in ``extract_bom``).
    """
    import pytesseract

    data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)

    words = []
    for i, text in enumerate(data.get("text", [])):
        text = text.strip()
        if not text:
            continue
        if not any(ch.isalnum() for ch in text):
            # Pure-punctuation "words" are almost always OCR misreading a
            # ruled table's own grid lines as stray characters (e.g. "|"
            # for a vertical rule) -- never real BOM content, and their
            # tiny gaps to neighboring real words would otherwise skew
            # _infer_gap_threshold toward a much-too-small threshold.
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
    borderless OCR'd tables into columns. Text only; see
    _split_row_into_cell_spans for the bbox-carrying version used to
    re-crop a specific column (e.g. for digit-only re-OCR)."""
    return [span["text"] for span in _split_row_into_cell_spans(row_words, gap_threshold_px)]


def _split_row_into_cell_spans(row_words: list[dict], gap_threshold_px: int = 25) -> list[dict]:
    """Like _split_row_into_cells, but returns each cell's pixel bounding
    box (the union of the word boxes grouped into it) alongside its text."""
    if not row_words:
        return []
    cells: list[dict] = []
    current_words = [row_words[0]]

    for word in row_words[1:]:
        prev = current_words[-1]
        gap = word["left"] - (prev["left"] + prev["width"])
        if gap > gap_threshold_px:
            cells.append(_cell_span(current_words))
            current_words = [word]
        else:
            current_words.append(word)
    cells.append(_cell_span(current_words))
    return cells


def _cell_span(words: list[dict]) -> dict:
    return {
        "text": " ".join(w["text"] for w in words),
        "left": min(w["left"] for w in words),
        "top": min(w["top"] for w in words),
        "right": max(w["left"] + w["width"] for w in words),
        "bottom": max(w["top"] + w["height"] for w in words),
    }


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
                "part_number": _clean_cell(_get_cell(row, mapping.get("part_number"))) or None,
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
