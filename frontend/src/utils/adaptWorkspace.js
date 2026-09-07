/**
 * Adapts the backend's real workspace JSON (components / validation /
 * procurement_summary / metadata -- see contracts/README.md) into the
 * plain "part" shape the existing UI components already expect
 * ({id, bubble_number, part_name, quantity, ..., status, bounding_box}).
 *
 * This is presentation-layer reshaping only -- every value originates from
 * the backend response. No business logic (matching, validation status,
 * confidence, or pricing) is computed here; it only re-labels the backend's
 * own `status` into the three buckets the existing StatusBadge component
 * already knows about.
 */

const STATUS_TO_BADGE = {
  linked: "matched",
  review_required: "warning",
  missing_callout: "missing",
  missing_bom_item: "missing",
  invalid: "missing",
};

function validationRecordFor(workspace, componentId) {
  const issues = workspace?.validation?.issues || [];
  return issues.find((record) => record.component_id === componentId);
}

/** One entry per backend component, in the shape BomTable/BomRow/PartDetails/BlueprintOverlay expect. */
export function adaptWorkspaceToParts(workspace) {
  const components = workspace?.components || [];

  return components.map((component) => {
    const record = validationRecordFor(workspace, component.id);
    const backendStatus = record?.status || "linked";

    return {
      id: component.id,
      item_number: component.item_number,
      bubble_number: component.bubble_number,
      part_number: component.part_number,
      part_name: component.part_name || "(unidentified part)",
      description: component.description,
      quantity: component.quantity,
      material_specification: component.material_specification,
      revision: component.revision,
      location_description: component.location_description,
      confidence_score: component.confidence_score,
      bounding_box: component.bounding_box,
      procurement: component.procurement_data,
      backendStatus,
      status: STATUS_TO_BADGE[backendStatus] || "warning",
      issues: record?.issues || [],
    };
  });
}

/** Counts derived from the backend's own per-component status -- not re-decided here. */
export function computeStats(workspace) {
  const parts = adaptWorkspaceToParts(workspace);
  return {
    total: parts.length,
    matched: parts.filter((p) => p.status === "matched").length,
    warnings: parts.filter((p) => p.status === "warning").length,
    missing: parts.filter((p) => p.status === "missing").length,
  };
}

/** Flat list of every validation issue across all components, backend messages verbatim. */
export function flattenValidationIssues(workspace) {
  const parts = adaptWorkspaceToParts(workspace);
  const flat = [];
  for (const part of parts) {
    for (const issue of part.issues) {
      flat.push({
        ...issue,
        componentId: part.id,
        status: part.backendStatus,
        itemNumber: part.item_number,
        bubbleNumber: part.bubble_number,
        partName: part.part_name,
      });
    }
  }
  return flat;
}
