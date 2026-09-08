import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { TransformWrapper, TransformComponent } from "react-zoom-pan-pinch";
import BlueprintOverlay from "./BlueprintOverlay";

// scale=1 is "the blueprint exactly as it currently appears" (the image
// rendered at the container's own width, same as before this feature
// existed) -- MAX_SCALE is how far a user (or a click-to-zoom) can zoom in
// from that baseline. Matches the spec's own suggested 1-5 range, widened
// slightly so a tiny balloon on a large sheet still has headroom.
const MIN_SCALE = 1;
const MAX_SCALE = 6;
// A selected component should read clearly without dominating the sheet --
// aim for it occupying roughly this fraction of the visible viewport.
const TARGET_OCCUPANCY = 0.35;
const ZOOM_ANIMATION_MS = 450;

/**
 * Blueprint image + zoom/pan viewer. Renders exactly like a plain <img>
 * until a BOM row is selected; clicking a row (or a callout) smoothly
 * zooms/pans to center that component, using the *same* bounding_box data
 * BlueprintOverlay already renders from -- no separate coordinate system.
 */
function BlueprintViewer({ blueprint, parts, selectedPart, onSelect }) {
  const isPdf = blueprint.fileType === "application/pdf";

  const transformRef = useRef(null);
  const viewportRef = useRef(null);
  const [canvasWidth, setCanvasWidth] = useState(null);
  // Pure derived value, not state: "selected but no known location" is
  // fully determined by props on every render, no effect needed for it.
  const locationUnavailable = Boolean(selectedPart) && !selectedPart.bounding_box;

  // The image renders at the viewport's own width (height auto, preserving
  // aspect ratio) -- identical to the old plain <img style="width:100%">
  // behavior, just measured in JS instead of expressed as a CSS percentage,
  // because react-zoom-pan-pinch's content box shrink-wraps to its
  // children rather than filling its parent. Re-measures on resize so the
  // feature keeps working when the window/card is resized.
  useLayoutEffect(() => {
    const el = viewportRef.current;
    if (!el) return;

    const measure = () => setCanvasWidth(el.clientWidth || null);
    measure();

    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Zoom to the selected component whenever selection changes. Does
  // nothing (leaves the current view alone) if there's nothing selected,
  // if it has no known blueprint location, or before the canvas has been
  // measured yet.
  useEffect(() => {
    if (!selectedPart || !selectedPart.bounding_box) return;

    const transform = transformRef.current;
    const viewport = viewportRef.current;
    if (!transform || !viewport) return;

    const node = document.getElementById(`blueprint-callout-${selectedPart.id}`);
    if (!node) return;

    const currentScale = transform.state.scale || 1;
    const rect = node.getBoundingClientRect();
    // Convert the callout's current on-screen size back to "scale 1"
    // content-space size, then find the scale that would make it fill the
    // viewport -- same logic react-zoom-pan-pinch's own zoomToElement uses
    // internally -- and back off to our target occupancy fraction rather
    // than filling the whole viewport (too extreme a zoom for a balloon).
    const nodeWidth = rect.width / currentScale;
    const nodeHeight = rect.height / currentScale;
    if (!nodeWidth || !nodeHeight) return;

    const fitScale = Math.min(viewport.clientWidth / nodeWidth, viewport.clientHeight / nodeHeight);
    const targetScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, fitScale * TARGET_OCCUPANCY));

    transform.zoomToElement(node, targetScale, ZOOM_ANIMATION_MS, "easeOut");
  }, [selectedPart]);

  const handleReset = () => {
    transformRef.current?.resetTransform(ZOOM_ANIMATION_MS, "easeOut");
    onSelect(null);
  };

  const handleZoomIn = () => transformRef.current?.zoomIn(0.5, 200);
  const handleZoomOut = () => transformRef.current?.zoomOut(0.5, 200);

  const showViewer = blueprint.imageUrl && !isPdf;

  return (
    <div className="blueprint-container">
      <div className="blueprint-header">
        <h2>Blueprint</h2>
        <span>{blueprint.name}</span>
      </div>

      {showViewer && (
        <div className="blueprint-toolbar">
          <span className="blueprint-location-hint">
            {locationUnavailable ? "Blueprint location unavailable" : ""}
          </span>
          <div className="blueprint-zoom-controls">
            <button type="button" onClick={handleZoomOut} aria-label="Zoom out">
              −
            </button>
            <button type="button" onClick={handleZoomIn} aria-label="Zoom in">
              +
            </button>
            <button type="button" className="reset-view-button" onClick={handleReset}>
              Reset View
            </button>
          </div>
        </div>
      )}

      <div className="blueprint-image-container" ref={viewportRef}>
        {showViewer ? (
          canvasWidth && (
            <TransformWrapper
              ref={transformRef}
              minScale={MIN_SCALE}
              maxScale={MAX_SCALE}
              initialScale={MIN_SCALE}
              wheel={{ step: 0.2 }}
              doubleClick={{ mode: "zoomIn" }}
            >
              <TransformComponent wrapperStyle={{ width: "100%", height: "100%" }}>
                <div className="blueprint-canvas" style={{ width: canvasWidth }}>
                  <img
                    src={blueprint.imageUrl}
                    alt="Engineering blueprint"
                    className="blueprint-image"
                    style={{ width: canvasWidth, height: "auto" }}
                    draggable={false}
                  />
                  <BlueprintOverlay parts={parts} selectedPart={selectedPart} onSelect={onSelect} />
                </div>
              </TransformComponent>
            </TransformWrapper>
          )
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
