"""Deterministic BOM <-> drawing-callout reconciliation.

No AI calls happen here. Matching is purely rule-based:
``normalize_identifier(bubble_number) == normalize_identifier(item_number)``.
See normalization.py for exactly what "normalize" means.

Nothing observed on input is silently dropped. Every BOM row and every
callout ends up represented by exactly one Component in the output,
even when it could not be linked -- unmatched/duplicate/ambiguous rows
just carry a ``link_status`` other than ``"matched"`` (see models.py)
so validation.py can flag them appropriately.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .models import Component
from .normalization import normalize_identifier

REQUIRED_BOUNDING_BOX_KEYS = ("xmin", "ymin", "xmax", "ymax")


@dataclass
class ReconciliationResult:
    components: list[Component] = field(default_factory=list)
    duplicate_item_numbers: list[str] = field(default_factory=list)
    duplicate_bubble_numbers: list[str] = field(default_factory=list)
    ambiguous_bom_identifiers: list[Any] = field(default_factory=list)
    ambiguous_callout_identifiers: list[Any] = field(default_factory=list)
    unmatched_bom_items: list[dict] = field(default_factory=list)
    unmatched_callouts: list[dict] = field(default_factory=list)


def _safe_int(value: Any) -> Optional[int]:
    """Best-effort int conversion that never raises. Preserves intent
    (a bad quantity should be flagged, not crash the whole pipeline)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            return None
    return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _normalize_bounding_box(bbox: Any) -> Optional[dict]:
    """Pass drawing coordinates through unchanged (per the project's
    normalized-coordinate contract) but validate shape defensively so a
    malformed callout can't crash export/UI code downstream."""
    if not isinstance(bbox, dict):
        return None
    if not all(key in bbox for key in REQUIRED_BOUNDING_BOX_KEYS):
        return None
    coords = {key: _safe_float(bbox.get(key)) for key in REQUIRED_BOUNDING_BOX_KEYS}
    if any(value is None for value in coords.values()):
        return None
    return coords


def _combine_confidence(
    bom_confidence: Optional[float], callout_confidence: Optional[float]
) -> Optional[float]:
    """Conservative combined confidence: if both sources are present,
    take the *lower* one (a single weak signal should pull the combined
    score down, not get averaged away). If only one source exists, use
    it as-is. If neither exists, return None -- callers must flag this
    as ``confidence_unavailable`` rather than inventing a score."""
    if bom_confidence is not None and callout_confidence is not None:
        return min(bom_confidence, callout_confidence)
    if bom_confidence is not None:
        return bom_confidence
    if callout_confidence is not None:
        return callout_confidence
    return None


def _index_by_identifier(
    rows: list[dict], id_field: str
) -> tuple[dict[str, list[dict]], list[dict]]:
    """Group rows by normalized identifier. Rows whose identifier can't
    be normalized are returned separately (ambiguous) rather than
    grouped under a fake key."""
    grouped: dict[str, list[dict]] = {}
    ambiguous: list[dict] = []
    for row in rows:
        key = normalize_identifier(row.get(id_field))
        if key is None:
            ambiguous.append(row)
        else:
            grouped.setdefault(key, []).append(row)
    return grouped, ambiguous


def _sort_key(key: str) -> tuple[int, Any]:
    try:
        return (0, int(key))
    except ValueError:
        return (1, key)


def reconcile_bom_and_callouts(
    bom_data: list[dict], callout_data: list[dict]
) -> ReconciliationResult:
    """Match BOM rows to drawing callouts by identifier and build the
    unified component list.

    ``bom_data`` and ``callout_data`` are plain lists of dicts (as
    produced by Person 4's extraction JSON / the shared sample data).
    This function never mutates its inputs.
    """
    if not isinstance(bom_data, list):
        raise TypeError("bom_data must be a list of dicts")
    if not isinstance(callout_data, list):
        raise TypeError("callout_data must be a list of dicts")

    result = ReconciliationResult()

    bom_by_key, bom_ambiguous = _index_by_identifier(bom_data, "item_number")
    callout_by_key, callout_ambiguous = _index_by_identifier(
        callout_data, "bubble_number"
    )

    result.ambiguous_bom_identifiers = [row.get("item_number") for row in bom_ambiguous]
    result.ambiguous_callout_identifiers = [
        row.get("bubble_number") for row in callout_ambiguous
    ]
    result.duplicate_item_numbers = sorted(
        (key for key, rows in bom_by_key.items() if len(rows) > 1), key=_sort_key
    )
    result.duplicate_bubble_numbers = sorted(
        (key for key, rows in callout_by_key.items() if len(rows) > 1), key=_sort_key
    )

    # Pending: entries created for keys shared by both sides, then
    # unmatched leftovers, so we can order the final component list
    # in a stable, reproducible way (matched-by-key, then bom-only,
    # then callout-only, then ambiguous).
    matched_entries: list[tuple[str, dict, Optional[dict]]] = []
    bom_only_entries: list[tuple[str, dict]] = []
    callout_only_entries: list[tuple[str, dict]] = []

    all_keys = set(bom_by_key) | set(callout_by_key)
    for key in sorted(all_keys, key=_sort_key):
        bom_rows = bom_by_key.get(key, [])
        callout_rows = callout_by_key.get(key, [])

        if bom_rows and callout_rows:
            # Duplicates on either side are paired by original order --
            # a documented, deterministic convention (not a guess about
            # which physical part is "really" which).
            pair_count = min(len(bom_rows), len(callout_rows))
            for i in range(pair_count):
                matched_entries.append((key, bom_rows[i], callout_rows[i]))
            for extra_bom in bom_rows[pair_count:]:
                bom_only_entries.append((key, extra_bom))
                result.unmatched_bom_items.append(extra_bom)
            for extra_callout in callout_rows[pair_count:]:
                callout_only_entries.append((key, extra_callout))
                result.unmatched_callouts.append(extra_callout)
        elif bom_rows:
            for row in bom_rows:
                bom_only_entries.append((key, row))
                result.unmatched_bom_items.append(row)
        else:
            for row in callout_rows:
                callout_only_entries.append((key, row))
                result.unmatched_callouts.append(row)

    result.unmatched_bom_items.extend(bom_ambiguous)
    result.unmatched_callouts.extend(callout_ambiguous)

    counter = 0

    def next_id() -> str:
        nonlocal counter
        counter += 1
        return f"cmp_{counter:03d}"

    def build_component(
        key: Optional[str],
        bom_row: Optional[dict],
        callout_row: Optional[dict],
        link_status: str,
        ambiguous_item: bool = False,
        ambiguous_bubble: bool = False,
    ) -> Component:
        bom_row = bom_row or {}
        callout_row = callout_row or {}

        raw_item_number = bom_row.get("item_number")
        raw_bubble_number = callout_row.get("bubble_number")

        bom_confidence = _safe_float(bom_row.get("confidence_score"))
        callout_confidence = _safe_float(callout_row.get("confidence_score"))

        return Component(
            id=next_id(),
            item_number=(
                normalize_identifier(raw_item_number) if bom_row else None
            ),
            bubble_number=(
                normalize_identifier(raw_bubble_number) if callout_row else None
            ),
            part_number=bom_row.get("part_number"),
            part_name=bom_row.get("part_name"),
            description=bom_row.get("description", "") or "",
            quantity=_safe_int(bom_row.get("quantity")),
            material_specification=bom_row.get("material_specification"),
            revision=bom_row.get("revision", "") or "",
            location_description=callout_row.get("location_description", "") or "",
            bounding_box=_normalize_bounding_box(callout_row.get("bounding_box")),
            confidence_score=_combine_confidence(bom_confidence, callout_confidence),
            procurement_data={},
            link_status=link_status,
            duplicate_item_number=key in result.duplicate_item_numbers if key else False,
            duplicate_bubble_number=key in result.duplicate_bubble_numbers if key else False,
            ambiguous_item_number=ambiguous_item,
            ambiguous_bubble_number=ambiguous_bubble,
            raw_item_number=raw_item_number,
            raw_bubble_number=raw_bubble_number,
            bom_confidence=bom_confidence,
            callout_confidence=callout_confidence,
        )

    for key, bom_row, callout_row in matched_entries:
        result.components.append(build_component(key, bom_row, callout_row, "matched"))

    for key, bom_row in bom_only_entries:
        result.components.append(build_component(key, bom_row, None, "bom_only"))

    for key, callout_row in callout_only_entries:
        result.components.append(build_component(key, None, callout_row, "callout_only"))

    for bom_row in bom_ambiguous:
        result.components.append(
            build_component(None, bom_row, None, "ambiguous", ambiguous_item=True)
        )

    for callout_row in callout_ambiguous:
        result.components.append(
            build_component(None, None, callout_row, "ambiguous", ambiguous_bubble=True)
        )

    return result
