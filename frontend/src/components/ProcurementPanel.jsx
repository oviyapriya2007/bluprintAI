function formatCurrency(value) {
  if (value === null || value === undefined) return "—";
  return `₹${Number(value).toFixed(2)}`;
}

// parts: adapted components (utils/adaptWorkspace.js), each carrying the
// backend's real procurement_data. summary: workspace.procurement_summary.
function ProcurementPanel({ parts, summary }) {
  const pricedParts = parts.filter((part) => part.procurement);

  return (
    <div className="procurement-panel">
      <div className="procurement-header">
        <h2>Procurement Estimate</h2>
        {summary && (
          <span>{formatCurrency(summary.estimated_total_cost_usd)} estimated total</span>
        )}
      </div>

      {summary?.note && <p className="procurement-note">{summary.note}</p>}

      {pricedParts.length === 0 ? (
        <p className="validation-empty">No procurement data available.</p>
      ) : (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>Part</th>
                <th>Qty</th>
                <th>Unit Cost (₹)</th>
                <th>Est. Total (₹)</th>
                <th>Supplier</th>
              </tr>
            </thead>
            <tbody>
              {pricedParts.map((part) => (
                <tr key={part.id}>
                  <td>{part.part_name}</td>
                  <td>{part.quantity ?? "—"}</td>
                  <td>{formatCurrency(part.procurement?.estimated_unit_cost_usd)}</td>
                  <td>{formatCurrency(part.procurement?.estimated_total_cost_usd)}</td>
                  <td>{part.procurement?.supplier_source || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default ProcurementPanel;
