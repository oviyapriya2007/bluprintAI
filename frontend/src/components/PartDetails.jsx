import StatusBadge from "./StatusBadge";

function formatCurrency(value) {
  if (value === null || value === undefined) return "—";
  return `₹${Number(value).toFixed(2)}`;
}

function PartDetails({ part }) {
  if (!part) {
    return (
      <div className="part-details empty-details">
        <h2>Part Details</h2>
        <p>Select a part from the BOM table to view its details.</p>
      </div>
    );
  }

  const confidencePct =
    part.confidence_score === null || part.confidence_score === undefined
      ? null
      : Math.round(part.confidence_score * 100);
  const reviewRequired = part.backendStatus === "review_required";

  return (
    <div className="part-details">
      <div className="part-details-header">
        <div>
          <span className="details-label">Selected Part</span>
          <h2>{part.part_name}</h2>
        </div>

        <StatusBadge status={part.status} />
      </div>

      <div className="details-grid">
        <div className="detail-item">
          <span>Item Number</span>
          <strong>{part.item_number ?? "—"}</strong>
        </div>

        <div className="detail-item">
          <span>Bubble Number</span>
          <strong>{part.bubble_number ? `#${part.bubble_number}` : "—"}</strong>
        </div>

        <div className="detail-item">
          <span>Part Number</span>
          <strong>{part.part_number ?? "—"}</strong>
        </div>

        <div className="detail-item">
          <span>Quantity</span>
          <strong>{part.quantity ?? "—"}</strong>
        </div>

        <div className="detail-item">
          <span>Material</span>
          <strong>{part.material_specification ?? "—"}</strong>
        </div>

        <div className="detail-item">
          <span>Confidence</span>
          <strong>
            {confidencePct === null ? "—" : `${confidencePct}%`}
            {reviewRequired && <span className="review-required-flag"> Review Required</span>}
          </strong>
        </div>
      </div>

      {part.issues.length > 0 && (
        <div className="part-issues">
          <span className="details-label">Issues</span>
          <ul>
            {part.issues.map((issue, index) => (
              <li key={index} className={`severity-${issue.severity}`}>
                {issue.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {part.procurement && (
        <div className="part-procurement">
          <span className="details-label">Procurement</span>
          <div className="details-grid">
            <div className="detail-item">
              <span>Unit Cost (₹)</span>
              <strong>{formatCurrency(part.procurement.estimated_unit_cost_usd)}</strong>
            </div>
            <div className="detail-item">
              <span>Estimated Total (₹)</span>
              <strong>{formatCurrency(part.procurement.estimated_total_cost_usd)}</strong>
            </div>
            <div className="detail-item">
              <span>Supplier</span>
              <strong>{part.procurement.supplier_source ?? "—"}</strong>
            </div>
            <div className="detail-item">
              <span>Stock Status</span>
              <strong>{part.procurement.stock_status ?? "—"}</strong>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default PartDetails;
