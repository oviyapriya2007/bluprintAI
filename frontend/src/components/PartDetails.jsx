import StatusBadge from "./StatusBadge";

function PartDetails({ part }) {
  if (!part) {
    return (
      <div className="part-details empty-details">
        <h2>Part Details</h2>
        <p>Select a part from the BOM table to view its details.</p>
      </div>
    );
  }

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
          <span>Bubble Number</span>
          <strong>#{part.bubble_number}</strong>
        </div>

        <div className="detail-item">
          <span>Quantity</span>
          <strong>{part.quantity}</strong>
        </div>

        <div className="detail-item">
          <span>Material</span>
          <strong>{part.material_specification}</strong>
        </div>

        <div className="detail-item">
          <span>Confidence</span>
          <strong>
            {Math.round(part.confidence_score * 100)}%
          </strong>
        </div>
      </div>
    </div>
  );
}

export default PartDetails;