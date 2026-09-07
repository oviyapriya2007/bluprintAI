"""High-level public entry point: ``build_workspace``.

This is the single function the rest of the team (Persons 1 & 2) should
need. It wires reconciliation -> procurement -> validation together and
returns a plain, JSON-serializable dict.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .procurement import calculate_procurement
from .reconciliation import reconcile_bom_and_callouts
from .validation import DEFAULT_CONFIDENCE_THRESHOLD, validate_workspace

SCHEMA_VERSION = "1.0"


def build_workspace(
    bom_data: list[dict],
    callout_data: list[dict],
    procurement_data: Optional[dict[str, dict]] = None,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> dict:
    """Run the full BOM/callout -> workspace pipeline.

    Args:
        bom_data: list of BOM row dicts (see contracts/README.md).
        callout_data: list of drawing callout dicts.
        procurement_data: optional catalog overrides, keyed by part
            number, merged on top of the built-in mock catalog.
        confidence_threshold: components with combined confidence below
            this value are flagged ``low_confidence`` / ``review_required``.

    Returns:
        A JSON-serializable dict::

            {
              "components": [...],
              "validation": {"summary": {...}, "issues": [...]},
              "procurement_summary": {...},
              "metadata": {...},
            }
    """
    reconciliation = reconcile_bom_and_callouts(bom_data, callout_data)
    procurement_summary = calculate_procurement(reconciliation.components, procurement_data)
    validation = validate_workspace(reconciliation.components, confidence_threshold)

    metadata = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": "intelligence (Person 5) module",
        "total_components": len(reconciliation.components),
        "confidence_threshold": confidence_threshold,
        "duplicate_item_numbers": reconciliation.duplicate_item_numbers,
        "duplicate_bubble_numbers": reconciliation.duplicate_bubble_numbers,
        "ambiguous_bom_identifiers": reconciliation.ambiguous_bom_identifiers,
        "ambiguous_callout_identifiers": reconciliation.ambiguous_callout_identifiers,
    }

    return {
        "components": [c.to_dict() for c in reconciliation.components],
        "validation": validation,
        "procurement_summary": procurement_summary,
        "metadata": metadata,
    }
