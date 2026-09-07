function BlueprintOverlay({ part }) {
  if (!part) {
    return null;
  }

  const { xmin, ymin, xmax, ymax } = part.bounding_box;

  const left = xmin / 10;
  const top = ymin / 10;
  const width = (xmax - xmin) / 10;
  const height = (ymax - ymin) / 10;

  return (
    <div
      className="blueprint-overlay"
      style={{
        left: `${left}%`,
        top: `${top}%`,
        width: `${width}%`,
        height: `${height}%`,
      }}
    >
      <span>{part.bubble_number}</span>
    </div>
  );
}

export default BlueprintOverlay;