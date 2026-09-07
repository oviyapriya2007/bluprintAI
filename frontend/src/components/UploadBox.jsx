import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { processDrawing, BlueprintApiError } from "../api/blueprintApi";

const ALLOWED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg"];
const MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024; // 20 MB, matches the upload hint text

// Purely a UX cue -- the backend runs one synchronous request, so these
// stages are not real server-reported progress, just a rotating status
// message so the UI never looks frozen during a real (sometimes slow)
// Gemini extraction call.
const PROCESSING_STAGES = [
  "Uploading drawing...",
  "Analyzing engineering drawing...",
  "Extracting BOM & callouts...",
  "Reconciling components...",
  "Building engineering workspace...",
];

function validateFile(file) {
  const extension = "." + (file.name.split(".").pop() || "").toLowerCase();
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    return `Unsupported file type "${extension}". Allowed: ${ALLOWED_EXTENSIONS.join(", ")}`;
  }
  if (file.size <= 0) {
    return "The selected file is empty.";
  }
  if (file.size > MAX_FILE_SIZE_BYTES) {
    return "File is too large. Maximum size is 20 MB.";
  }
  return null;
}

function UploadBox() {
  const navigate = useNavigate();
  const [status, setStatus] = useState("idle"); // idle | uploading | error
  const [error, setError] = useState(null);
  const [stageIndex, setStageIndex] = useState(0);
  const inputRef = useRef(null);

  useEffect(() => {
    if (status !== "uploading") return undefined;
    const interval = setInterval(() => {
      setStageIndex((index) => Math.min(index + 1, PROCESSING_STAGES.length - 1));
    }, 1800);
    return () => clearInterval(interval);
  }, [status]);

  const handleFileChange = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    const validationError = validateFile(file);
    if (validationError) {
      setStatus("error");
      setError(validationError);
      if (inputRef.current) inputRef.current.value = "";
      return;
    }

    setStatus("uploading");
    setStageIndex(0);
    setError(null);

    try {
      const workspace = await processDrawing(file);
      const imageUrl = file.type === "application/pdf" ? null : URL.createObjectURL(file);

      // Keep a JSON-serializable copy around so a page refresh on
      // /dashboard doesn't lose the BOM (the blob image URL can't survive
      // a reload, but the workspace data can).
      try {
        sessionStorage.setItem("blueprintai_workspace", JSON.stringify(workspace));
        sessionStorage.setItem("blueprintai_filename", file.name);
      } catch {
        /* sessionStorage unavailable (private mode, etc.) -- not fatal */
      }

      navigate("/dashboard", {
        state: { workspace, imageUrl, fileName: file.name, fileType: file.type },
      });
    } catch (err) {
      setStatus("error");
      setError(
        err instanceof BlueprintApiError
          ? err.message
          : "Something went wrong while processing the drawing."
      );
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  if (status === "uploading") {
    return (
      <div className="upload-box">
        <div className="upload-icon upload-spinner">⏳</div>
        <h2>Processing your drawing...</h2>
        <p>{PROCESSING_STAGES[stageIndex]}</p>
        <span className="upload-hint">This can take up to a minute for AI extraction.</span>
      </div>
    );
  }

  return (
    <div className="upload-box">
      <div className="upload-icon">📄</div>

      <h2>Upload your blueprint</h2>

      <p>
        Upload an engineering drawing or blueprint to analyze
        parts, quantities, and specifications.
      </p>

      <label className="upload-button">
        Choose File

        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg"
          hidden
          onChange={handleFileChange}
        />
      </label>

      <span className="upload-hint">
        PDF, PNG or JPG • Max 20 MB
      </span>

      {status === "error" && error && (
        <div className="upload-error" role="alert">
          <strong>Upload failed.</strong> {error}
        </div>
      )}
    </div>
  );
}

export default UploadBox;
