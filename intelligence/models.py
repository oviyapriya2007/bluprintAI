"""Data models for the intelligence module.

These are the internal, JSON-serializable representations used across
reconciliation, validation, procurement, and export. Field names on
``Component`` that are part of the team's shared contract (``id``,
``item_number``, ``bubble_number``, ``part_number``, ``part_name``,
``quantity``, ``material_specification``, ``confidence_score``,
``bounding_box``) are never renamed -- see contracts/README.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


# Statuses a component's validation record can carry. Kept as a plain
# tuple (not an Enum) so the values serialize to JSON without conversion.
VALID_STATUSES = (
    "linked",
    "review_required",
    "missing_callout",
    "missing_bom_item",
    "invalid",
)

# How a component came to exist, decided during reconciliation. This is
# internal bookkeeping used by validation.py -- it is NOT part of the
# public contract and is intentionally left out of Component.to_dict().
LINK_STATUSES = ("matched", "bom_only", "callout_only", "ambiguous")


@dataclass
class Component:
    """A unified component record.

    Public/contract fields are serialized by ``to_dict()``. Everything
    below the "internal bookkeeping" marker exists to help validation.py
    explain *why* a component ended up the way it did, and is not part
    of the shared contract.
    """

    id: str
    item_number: Optional[str] = None
    bubble_number: Optional[str] = None
    part_number: Optional[str] = None
    part_name: Optional[str] = None
    description: str = ""
    quantity: Optional[int] = None
    material_specification: Optional[str] = None
    revision: str = ""
    location_description: str = ""
    bounding_box: Optional[dict] = None
    confidence_score: Optional[float] = None
    procurement_data: dict = field(default_factory=dict)

    # --- internal bookkeeping (excluded from to_dict) ---------------
    link_status: str = "matched"  # one of LINK_STATUSES
    duplicate_item_number: bool = False
    duplicate_bubble_number: bool = False
    ambiguous_item_number: bool = False
    ambiguous_bubble_number: bool = False
    raw_item_number: Any = None
    raw_bubble_number: Any = None
    bom_confidence: Optional[float] = None
    callout_confidence: Optional[float] = None

    def to_dict(self) -> dict:
        """Serialize only the fields defined by the shared contract."""
        return {
            "id": self.id,
            "item_number": self.item_number,
            "bubble_number": self.bubble_number,
            "part_number": self.part_number,
            "part_name": self.part_name,
            "description": self.description,
            "quantity": self.quantity,
            "material_specification": self.material_specification,
            "revision": self.revision,
            "location_description": self.location_description,
            "bounding_box": self.bounding_box,
            "confidence_score": self.confidence_score,
            "procurement_data": self.procurement_data,
        }


@dataclass
class ValidationIssue:
    type: str
    severity: str  # "info" | "warning" | "error"
    message: str

    def to_dict(self) -> dict:
        return {"type": self.type, "severity": self.severity, "message": self.message}


@dataclass
class ComponentValidation:
    component_id: str
    issues: list[ValidationIssue] = field(default_factory=list)
    status: str = "linked"

    def to_dict(self) -> dict:
        return {
            "component_id": self.component_id,
            "issues": [issue.to_dict() for issue in self.issues],
            "status": self.status,
        }
