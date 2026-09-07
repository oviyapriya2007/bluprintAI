function StatusBadge({ status }) {
  const statusInfo = {
    matched: {
      label: "Matched",
      symbol: "✓",
    },
    warning: {
      label: "Warning",
      symbol: "⚠",
    },
    missing: {
      label: "Missing",
      symbol: "✕",
    },
  };

  const info = statusInfo[status] || statusInfo.warning;

  return (
    <span className={`status-badge ${status}`}>
      {info.symbol} {info.label}
    </span>
  );
}

export default StatusBadge;