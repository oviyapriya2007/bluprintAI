import BomRow from "./BomRow";

function BomTable({ parts, selectedPart, onSelect }) {
  return (
    <div className="bom-container">
      <div className="bom-header">
        <h2>Bill of Materials</h2>

        <span>{parts.length} part{parts.length === 1 ? "" : "s"} detected</span>
      </div>

      {parts.length === 0 ? (
        <p className="validation-empty bom-empty">
          No components were detected in this drawing.
        </p>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Part</th>
                <th>Confidence</th>
                <th>Status</th>
              </tr>
            </thead>

            <tbody>
              {parts.map((part) => (
                <BomRow
                  key={part.id}
                  part={part}
                  onSelect={onSelect}
                  isSelected={selectedPart?.id === part.id}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default BomTable;
