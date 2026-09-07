import BlueprintOverlay from "./BlueprintOverlay";

function BlueprintViewer({ blueprint, parts, selectedPart, onSelect }) {
  const isPdf = blueprint.fileType === "application/pdf";

  return (
    <div className="blueprint-container">

      <div className="blueprint-header">
        <h2>Blueprint</h2>
        <span>{blueprint.name}</span>
      </div>

      <div className="blueprint-image-container">
        {blueprint.imageUrl && !isPdf ? (
          <>
            <img
              src={blueprint.imageUrl}
              alt="Engineering blueprint"
              className="blueprint-image"
            />
            <BlueprintOverlay parts={parts} selectedPart={selectedPart} onSelect={onSelect} />
          </>
        ) : (
          <div className="blueprint-preview-unavailable">
            {isPdf
              ? "Preview isn't available for PDF drawings yet — the BOM and validation below are still generated from the real backend result."
              : "No drawing preview available."}
          </div>
        )}
      </div>

    </div>
  );
}

export default BlueprintViewer;
