"""Validation engine.

Turns the (already-reconciled) component list into a per-component
validation record plus a workspace-level summary. Nothing here mutates
components; this module only reads the bookkeeping fields reconciliation
attached to each ``Component`` (see models.py) and the contract fields.
"""

from __future__ import annotations

from .models import Component, ComponentValidation, ValidationIssue

# Confidence below this value gets flagged for human review. Configurable
# per call -- never hard-code a threshold anywhere else in this module.
DEFAULT_CONFIDENCE_THRESHOLD = 0.75


def _validate_component(
    component: Component, confidence_threshold: float
) -> ComponentValidation:
    issues: list[ValidationIssue] = []

    if component.ambiguous_item_number or component.ambiguous_bubble_number:
        raw = component.raw_item_number or component.raw_bubble_number
        issues.append(
            ValidationIssue(
                type="ambiguous_identifier",
                severity="error",
                message=(
                    f"Identifier '{raw}' could not be normalized to a single "
                    "unambiguous number and was not auto-matched."
                ),
            )
        )
        return ComponentValidation(component.id, issues, "invalid")

    if component.link_status == "bom_only":
        status = "missing_callout"
        issues.append(
            ValidationIssue(
                type="missing_callout",
                severity="error",
                message=(
                    f"BOM item {component.item_number} has no matching "
                    "drawing callout."
                ),
            )
        )
    elif component.link_status == "callout_only":
        status = "missing_bom_item"
        issues.append(
            ValidationIssue(
                type="missing_bom_item",
                severity="error",
                message=(
                    f"Drawing bubble {component.bubble_number} has no "
                    "matching BOM item."
                ),
            )
        )
    else:
        status = "linked"

    if component.duplicate_item_number:
        issues.append(
            ValidationIssue(
                type="duplicate_bom_item",
                severity="error",
                message=(
                    f"Item number {component.item_number} appears more than "
                    "once in the BOM."
                ),
            )
        )
    if component.duplicate_bubble_number:
        issues.append(
            ValidationIssue(
                type="duplicate_callout",
                severity="error",
                message=(
                    f"Bubble number {component.bubble_number} appears more "
                    "than once on the drawing."
                ),
            )
        )

    if component.confidence_score is None:
        issues.append(
            ValidationIssue(
                type="confidence_unavailable",
                severity="info",
                message="No confidence score was available from either the "
                "BOM or the drawing extraction.",
            )
        )
    elif component.confidence_score < confidence_threshold:
        issues.append(
            ValidationIssue(
                type="low_confidence",
                severity="warning",
                message=(
                    f"Combined confidence {component.confidence_score:.2f} is "
                    f"below the review threshold of {confidence_threshold:.2f}."
                ),
            )
        )

    # Missing-field checks only make sense where BOM data exists.
    if component.link_status in ("matched", "bom_only"):
        if not component.part_name:
            issues.append(
                ValidationIssue(
                    type="missing_field",
                    severity="warning",
                    message="Part name is missing.",
                )
            )
        if component.quantity is None:
            issues.append(
                ValidationIssue(
                    type="missing_field",
                    severity="warning",
                    message="Quantity is missing.",
                )
            )
        elif component.quantity <= 0:
            issues.append(
                ValidationIssue(
                    type="invalid_quantity",
                    severity="warning",
                    message=f"Quantity {component.quantity} is not a valid "
                    "positive count.",
                )
            )
        if not component.material_specification:
            issues.append(
                ValidationIssue(
                    type="missing_field",
                    severity="info",
                    message="Material specification is missing.",
                )
            )

    if status == "linked" and issues:
        status = "review_required"

    return ComponentValidation(component.id, issues, status)


def validate_workspace(
    components: list[Component],
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> dict:
    """Validate every component and produce a workspace-level summary.

    Returns a JSON-serializable dict shaped like::

        {"summary": {...}, "issues": [{"component_id", "issues", "status"}, ...]}
    """
    validations = [_validate_component(c, confidence_threshold) for c in components]

    matched = sum(1 for c in components if c.link_status == "matched")
    bom_only = sum(1 for c in components if c.link_status == "bom_only")
    callout_only = sum(1 for c in components if c.link_status == "callout_only")
    ambiguous_items = sum(1 for c in components if c.ambiguous_item_number)
    ambiguous_bubbles = sum(1 for c in components if c.ambiguous_bubble_number)

    status_counts: dict[str, int] = {}
    for v in validations:
        status_counts[v.status] = status_counts.get(v.status, 0) + 1

    low_confidence_items = sum(
        1 for v in validations if any(i.type == "low_confidence" for i in v.issues)
    )
    duplicate_bom_items = sum(1 for c in components if c.duplicate_item_number)
    duplicate_callouts = sum(1 for c in components if c.duplicate_bubble_number)

    summary = {
        "total_bom_items": matched + bom_only + ambiguous_items,
        "total_callouts": matched + callout_only + ambiguous_bubbles,
        "linked_items": matched,
        "missing_callouts": bom_only,
        "missing_bom_items": callout_only,
        "low_confidence_items": low_confidence_items,
        "duplicate_bom_items": duplicate_bom_items,
        "duplicate_callouts": duplicate_callouts,
        "ambiguous_identifiers": ambiguous_items + ambiguous_bubbles,
        "review_required_items": status_counts.get("review_required", 0),
        "invalid_items": status_counts.get("invalid", 0),
        "confidence_threshold": confidence_threshold,
    }

    return {"summary": summary, "issues": [v.to_dict() for v in validations]}
