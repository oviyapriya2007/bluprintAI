function BomRow({ part, onSelect, isSelected }) {
  return (
    <tr
      className={isSelected ? "selected-row" : ""}
      onClick={() => onSelect(part)}
    >
      <td>{part.bubble_number}</td>

      <td>
        <strong>{part.part_name}</strong>
      </td>
    </tr>
  );
}

export default BomRow;