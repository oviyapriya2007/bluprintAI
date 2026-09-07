/**
 * Client for the BlueprintAI backend (../../../app.py).
 *
 * The backend base URL comes from VITE_API_URL (see .env / .env.example) --
 * never hardcode localhost URLs elsewhere in the app. Falls back to
 * http://localhost:8000 so the app still works with zero setup.
 */

const RAW_API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
export const API_URL = RAW_API_URL.replace(/\/+$/, "");

const PROCESS_TIMEOUT_MS = 120_000; // real Gemini extraction can take a while

export class BlueprintApiError extends Error {
  constructor(message, { status, workspace } = {}) {
    super(message);
    this.name = "BlueprintApiError";
    this.status = status;
    // When the backend could still produce a (failed) workspace, we keep it
    // around so the UI can show *why*, not just that something went wrong.
    this.workspace = workspace;
  }
}

/**
 * Upload one engineering drawing and return the backend's real workspace
 * JSON (see contracts/README.md / intelligence/README.md for the shape).
 *
 * Throws BlueprintApiError with a user-safe message for every failure mode:
 * backend unreachable, request timeout, unsupported file, or a pipeline
 * failure (corrupt/unreadable drawing, empty extraction, etc).
 */
export async function processDrawing(file, { signal } = {}) {
  if (!file) {
    throw new BlueprintApiError("No file selected.");
  }

  const formData = new FormData();
  formData.append("file", file);

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), PROCESS_TIMEOUT_MS);
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", () => controller.abort());
  }

  let response;
  try {
    response = await fetch(`${API_URL}/process`, {
      method: "POST",
      body: formData,
      signal: controller.signal,
    });
  } catch (error) {
    if (error.name === "AbortError") {
      throw new BlueprintApiError(
        "The request timed out. The backend may be unavailable, or the drawing is taking too long to process."
      );
    }
    throw new BlueprintApiError(
      `Could not reach the BlueprintAI backend at ${API_URL}. Make sure it is running.`
    );
  } finally {
    clearTimeout(timeoutId);
  }

  let body;
  try {
    body = await response.json();
  } catch {
    throw new BlueprintApiError(
      "The backend returned an invalid response.",
      { status: response.status }
    );
  }

  if (!response.ok) {
    // FastAPI's own validation errors (e.g. bad file type) come back as
    // {"detail": "..."}; a pipeline failure comes back as a full (failed)
    // workspace with metadata.pipeline_errors.
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : body?.metadata?.pipeline_errors?.map((e) => e.message).join("; ") ||
          "Processing failed.";
    throw new BlueprintApiError(detail, { status: response.status, workspace: body });
  }

  if (body?.metadata?.pipeline_status === "failed") {
    const detail =
      body.metadata.pipeline_errors?.map((e) => e.message).join("; ") ||
      "Processing failed.";
    throw new BlueprintApiError(detail, { status: response.status, workspace: body });
  }

  return body;
}

/**
 * Request a generated export file (Excel or CSV) for an already-processed
 * workspace and return it as a Blob ready to hand to the browser's download
 * mechanism. `format` is "excel" or "csv".
 */
export async function exportWorkspace(workspace, format) {
  const path = format === "csv" ? "/export/csv" : "/export/excel";

  let response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(workspace),
    });
  } catch {
    throw new BlueprintApiError(
      `Could not reach the BlueprintAI backend at ${API_URL}. Make sure it is running.`
    );
  }

  if (!response.ok) {
    let detail = "Export failed.";
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* response wasn't JSON; keep the generic message */
    }
    throw new BlueprintApiError(detail, { status: response.status });
  }

  return response.blob();
}

export async function checkHealth() {
  const response = await fetch(`${API_URL}/health`);
  if (!response.ok) {
    throw new BlueprintApiError("Backend health check failed.", { status: response.status });
  }
  return response.json();
}
