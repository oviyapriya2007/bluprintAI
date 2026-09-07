"""
reconcile.py -- Stage 5 of the BlueprintAI hybrid detection pipeline.

Pure Python, no LLM calls. Diffs deterministic BOM item numbers
(bom_extract.py's output) against classified balloon numbers
(classify.py's output) and reports matched / missing / extra / duplicate
identifiers.

Deliberately self-contained (it re-implements the small identifier
normalization rule rather than importing intelligence/normalization.py)
so it has no dependency on the rest of the repo and can be fed
hand-written fake data and unit-tested in complete isolation from
ingest/bom_extract/callout_detect/classify -- see tests/test_reconcile.py.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Any, Optional

logger = logging.getLogger(__name__)

_DIGIT_RUN = re.compile(r"\d+")


def normalize_item_number(raw: Any) -> Optional[str]:
    """Canonicalize an item/balloon number to a comparable string, or None
    if it can't be interpreted unambiguously (no digits, or more than one
    separate run of digits, e.g. "3-4"). Leading zeros are stripped so
    "3", "03", and 3 all normalize to "3"."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return str(raw)
    if isinstance(raw, float):
        return str(int(raw)) if raw.is_integer() else None
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        digit_runs = _DIGIT_RUN.findall(text)
        if len(digit_runs) != 1:
            return None
        return str(int(digit_runs[0]))
    return None


def reconcile(bom_items: list[dict], balloon_results: list[dict]) -> dict:
    """Diff BOM item numbers against classified balloon numbers.

    Parameters
    ----------
    bom_items:
        list of dicts with at least ``item_no`` (bom_extract.py's output
        shape: ``{item_no, description, qty, material}``).
    balloon_results:
        list of dicts (or dict-like objects, e.g.
        ``classify.ClassificationResult``) with ``crop_id``, ``is_balloon``,
        ``number``. Only entries with ``is_balloon`` truthy and a
        normalizable ``number`` participate in the diff.

    Returns
    -------
    dict: ``{"matched": [...], "missing": [...], "extra": [...], "duplicates": [...]}``

    - ``matched``: item numbers present in the BOM AND among valid
      balloons.
    - ``missing``: BOM item numbers with no corresponding balloon detected
      anywhere on the sheet.
    - ``extra``: balloon numbers detected on the sheet that don't
      correspond to any BOM row (possible false positive or missing BOM
      row).
    - ``duplicates``: balloon numbers that were detected/classified more
      than once (flagged for human review; may be a legitimate repeated
      callout or a detection artifact).
    """
    bom_by_number: dict[str, list[dict]] = defaultdict(list)
    for item in bom_items:
        item = _as_dict(item)
        key = normalize_item_number(item.get("item_no"))
        if key is not None:
            bom_by_number[key].append(item)

    balloons_by_number: dict[str, list[dict]] = defaultdict(list)
    for result in balloon_results:
        result = _as_dict(result)
        if not result.get("is_balloon"):
            continue
        key = normalize_item_number(result.get("number"))
        if key is not None:
            balloons_by_number[key].append(result)

    bom_keys = set(bom_by_number)
    balloon_keys = set(balloons_by_number)

    matched = [
        {
            "item_no": key,
            "bom_count": len(bom_by_number[key]),
            "balloon_count": len(balloons_by_number[key]),
            "crop_ids": [b.get("crop_id") for b in balloons_by_number[key]],
        }
        for key in sorted(bom_keys & balloon_keys, key=_sort_key)
    ]
    missing = [
        {"item_no": key, "bom_count": len(bom_by_number[key])}
        for key in sorted(bom_keys - balloon_keys, key=_sort_key)
    ]
    extra = [
        {
            "number": key,
            "balloon_count": len(balloons_by_number[key]),
            "crop_ids": [b.get("crop_id") for b in balloons_by_number[key]],
        }
        for key in sorted(balloon_keys - bom_keys, key=_sort_key)
    ]
    duplicates = [
        {
            "number": key,
            "count": len(balloons_by_number[key]),
            "crop_ids": [b.get("crop_id") for b in balloons_by_number[key]],
        }
        for key in sorted(balloon_keys, key=_sort_key)
        if len(balloons_by_number[key]) > 1
    ]

    logger.info(
        "[reconcile] reconciliation result: matched=%d missing=%d extra=%d duplicates=%d",
        len(matched),
        len(missing),
        len(extra),
        len(duplicates),
    )

    return {"matched": matched, "missing": missing, "extra": extra, "duplicates": duplicates}


def _as_dict(item: Any) -> dict:
    if isinstance(item, dict):
        return item
    if hasattr(item, "__dict__"):
        return vars(item)
    raise TypeError(f"reconcile: expected a dict-like item, got {type(item)!r}")


def _sort_key(key: str) -> tuple[int, Any]:
    try:
        return (0, int(key))
    except ValueError:
        return (1, key)
