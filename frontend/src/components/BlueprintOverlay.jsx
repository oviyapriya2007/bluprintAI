// Renders one clickable region per component that has a real bounding_box
// (backend normalized 0-1000 coordinates -> percentage, per the project's
// coordinate contract -- xmin/10 == percent-from-left, etc). Clicking a
// callout selects its BOM row; the currently selected part is highlighted.
function BlueprintOverlay({ parts, selectedPart, onSelect }) {
  const located = parts.filter((part) => part.bounding_box);

  return (
    <>
      {located.map((part) => {
        const { xmin, ymin, xmax, ymax } = part.bounding_box;
        const isSelected = selectedPart?.id === part.id;

        return (
          <div
            key={part.id}
            className={`blueprint-overlay ${isSelected ? "selected" : "unselected"}`}
            style={{
              left: `${xmin / 10}%`,
              top: `${ymin / 10}%`,
              width: `${(xmax - xmin) / 10}%`,
              height: `${(ymax - ymin) / 10}%`,
            }}
            onClick={() => onSelect(part)}
            role="button"
            aria-label={`Select component at bubble ${part.bubble_number ?? part.item_number}`}
          >
            <span>{part.bubble_number ?? part.item_number}</span>
          </div>
        );
      })}
    </>
  );
}

export default BlueprintOverlay;
