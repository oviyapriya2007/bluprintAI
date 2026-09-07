function severityIcon(severity) {
  if (severity === "error") return "✕";
  if (severity === "warning") return "⚠";
  return "ℹ";
}

// issues: flattened list from utils/adaptWorkspace.js#flattenValidationIssues
// -- every {type, severity, message} comes straight from the backend's
// intelligence.validate_workspace() output.
function ValidationPanel({ issues }) {
  return (
    <div className="validation-panel">
      <div className="validation-header">
        <h2>Validation Issues</h2>
        <span>{issues.length} issue{issues.length === 1 ? "" : "s"}</span>
      </div>

      {issues.length === 0 ? (
        <p className="validation-empty">
          No validation issues. Every component linked cleanly.
        </p>
      ) : (
        <ul className="validation-list">
          {issues.map((issue, index) => (
            <li
              key={`${issue.componentId}-${index}`}
              className={`validation-item severity-${issue.severity}`}
            >
              <span className="validation-icon">{severityIcon(issue.severity)}</span>
              <div>
                <strong>
                  {issue.itemNumber
                    ? `Item ${issue.itemNumber}`
                    : issue.bubbleNumber
                      ? `Bubble ${issue.bubbleNumber}`
                      : issue.componentId}
                  {issue.partName ? ` — ${issue.partName}` : ""}
                </strong>
                <p>{issue.message}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default ValidationPanel;
