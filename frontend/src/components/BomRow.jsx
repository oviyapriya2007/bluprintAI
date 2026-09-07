import StatusBadge from "./StatusBadge";

function BomRow({ part, onSelect, isSelected }) {
  const confidencePct =
    part.confidence_score === null || part.confidence_score === undefined
      ? null
      : Math.round(part.confidence_score * 100);

  return (
    <tr
      className={isSelected ? "selected-row" : ""}
      onClick={() => onSelect(part)}
    >
      <td>{part.bubble_number ?? part.item_number ?? "—"}</td>

      <td>
        <strong>{part.part_name}</strong>
      </td>

      <td>{confidencePct === null ? "—" : `${confidencePct}%`}</td>

      <td>
        <StatusBadge status={part.status} />
      </td>
    </tr>
  );
}

export default BomRow;
