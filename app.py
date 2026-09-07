"""BlueprintAI backend API.

Minimal FastAPI wrapper around ``run_pipeline`` (see run_pipeline.py for
the actual document-processor -> vision-extractor -> intelligence wiring).
This file adds no business logic of its own -- it only accepts an upload,
hands the saved file to the pipeline, and returns the workspace JSON.

Run locally:

    .venv\\Scripts\\uvicorn app:app --reload --port 8000

Endpoints:

    GET  /health        -> liveness + which stages are ready
    POST /process       -> upload a drawing, get back the workspace JSON
    POST /export/excel  -> workspace JSON in, .xlsx file out
    POST /export/csv    -> workspace JSON in, .csv file out
"""

from __future__ import annotations

import io
import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from run_pipeline import run_pipeline  # also bootstraps sys.path for processor/vision_extractor

logger = logging.getLogger("blueprintai.api")

app = FastAPI(
    title="BlueprintAI API",
    description="Engineering drawing -> BOM/callout reconciliation -> workspace JSON.",
    version="1.0.0",
)

# The frontend's own origin(s) -- see frontend/vite.config.js (Vite's default
# dev port is 5173; 127.0.0.1 and localhost are distinct origins to browsers,
# so both are listed). Override/extend via FRONTEND_ORIGINS (comma-separated)
# for a non-default dev port instead of widening this to "*".
_DEFAULT_FRONTEND_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
_extra_origins = [o.strip() for o in os.getenv("FRONTEND_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEFAULT_FRONTEND_ORIGINS + _extra_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg"}


@app.get("/health")
def health() -> dict:
    """Liveness check, plus whether each pipeline stage is importable and
    whether vision-extractor has a real Gemini key configured (mock vs live)."""
    stage_status: dict[str, str] = {}

    try:
        from processor import process_document  # noqa: F401

        stage_status["document_processor"] = "ok"
    except Exception as exc:  # noqa: BLE001
        stage_status["document_processor"] = f"error: {exc}"

    vision_mode = "unknown"
    try:
        from vision_extractor import VisionExtractor
        from vision_extractor.config import get_settings

        stage_status["vision_extractor"] = "ok"
        vision_mode = "mock" if get_settings().use_mock else "live"
    except Exception as exc:  # noqa: BLE001
        stage_status["vision_extractor"] = f"error: {exc}"

    try:
        from intelligence import build_workspace  # noqa: F401

        stage_status["intelligence"] = "ok"
    except Exception as exc:  # noqa: BLE001
        stage_status["intelligence"] = f"error: {exc}"

    overall_ok = all(status == "ok" for status in stage_status.values())

    return {
        "status": "ok" if overall_ok else "degraded",
        "stages": stage_status,
        "vision_extraction_mode": vision_mode,
    }


@app.post("/process")
async def process(file: UploadFile = File(...)) -> JSONResponse:
    """Accept one engineering drawing (PDF/PNG/JPEG) and return the full
    workspace JSON: reconciled components, validation issues, procurement
    estimates, and pipeline metadata.

    Returns HTTP 422 (with the same JSON body) if the pipeline could not
    produce any usable result -- e.g. an unsupported/corrupt file. Never
    raises an unhandled exception for a bad upload.
    """
    original_name = file.filename or "upload"
    suffix = Path(original_name).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{suffix or '(none)'}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_SUFFIXES))}"
            ),
        )

    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = Path(tmp.name)
    finally:
        await file.close()

    try:
        workspace = run_pipeline(str(tmp_path))
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    workspace["metadata"]["original_filename"] = original_name
    status_code = 422 if workspace["metadata"]["pipeline_status"] == "failed" else 200
    return JSONResponse(content=workspace, status_code=status_code)


def _export_response(workspace: dict, suffix: str, media_type: str, filename: str) -> StreamingResponse:
    """Shared implementation for the two export endpoints below: write the
    workspace to a temp file via the existing intelligence export functions,
    stream it back, then delete the temp file. No new export logic -- this
    only wires the frontend to intelligence/export.py, which already does
    the real work."""
    if not isinstance(workspace, dict) or "components" not in workspace:
        raise HTTPException(status_code=400, detail="Request body must be a workspace JSON object.")

    from intelligence import export_to_csv, export_to_excel

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp_path = Path(tmp.name)
    try:
        if suffix == ".csv":
            export_to_csv(workspace, str(tmp_path))
        else:
            export_to_excel(workspace, str(tmp_path))
        data = tmp_path.read_bytes()
    except Exception as exc:  # noqa: BLE001 -- never leak a stack trace to the client
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}") from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    return StreamingResponse(
        io.BytesIO(data),
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.post("/export/excel")
async def export_excel(workspace: dict) -> StreamingResponse:
    """Accept a workspace JSON (as returned by /process) and return a
    3-sheet Excel workbook, generated by intelligence.export_to_excel."""
    return _export_response(
        workspace,
        ".xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "BlueprintAI_BOM.xlsx",
    )


@app.post("/export/csv")
async def export_csv(workspace: dict) -> StreamingResponse:
    """Accept a workspace JSON (as returned by /process) and return the
    flattened CSV, generated by intelligence.export_to_csv."""
    return _export_response(workspace, ".csv", "text/csv", "BlueprintAI_BOM.csv")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
