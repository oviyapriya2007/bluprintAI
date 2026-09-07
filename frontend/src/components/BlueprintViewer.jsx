import BlueprintOverlay from "./BlueprintOverlay";

function BlueprintViewer({ blueprint, selectedPart }) {
  return (
    <div className="blueprint-container">

      <div className="blueprint-header">
        <h2>Blueprint</h2>
        <span>{blueprint.name}</span>
      </div>

      <div className="blueprint-image-container">

        <img
          src={blueprint.imageUrl}
          alt="Engineering blueprint"
          className="blueprint-image"
        />

        <BlueprintOverlay part={selectedPart} />

      </div>

    </div>
  );
}

export default BlueprintViewer;