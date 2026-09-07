"""
File validation for BlueprintAI document preprocessing (Person 3).

Accepts only: .pdf, .png, .jpg, .jpeg
Deterministic checks only — no AI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PIL import Image, UnidentifiedImageError

# Allowed extensions → normalized file_type label
SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".png": "png",
    ".jpg": "jpg",
    ".jpeg": "jpeg",
}

_PDF_MAGIC = b"%PDF"


def _result(
    *,
    valid: bool,
    file_type: Optional[str],
    file_size_bytes: Optional[int],
    error: Optional[str],
) -> dict[str, Any]:
    """Build the standard validation response dict."""
    return {
        "valid": valid,
        "file_type": file_type,
        "file_size_bytes": file_size_bytes,
        "error": error,
    }


def _can_read_pdf(path: Path) -> Optional[str]:
    """
    Verify a PDF can be opened and looks like a PDF.

    Returns an error message on failure, or None on success.
    """
    try:
        with path.open("rb") as fh:
            header = fh.read(8)
            if not header:
                return "File could not be read (no data returned)."
            if not header.startswith(_PDF_MAGIC):
                return "File extension is .pdf but content is not a valid PDF."
            # Confirm the rest of the file is readable
            while fh.read(1024 * 64):
                pass
    except OSError as exc:
        return f"File could not be opened or read: {exc}"
    return None


def _can_read_image(path: Path, expected: str) -> Optional[str]:
    """
    Verify an image can be opened with Pillow and matches PNG/JPEG.

    Returns an error message on failure, or None on success.
    """
    try:
        with Image.open(path) as img:
            img.verify()  # lightweight integrity check
        # verify() may leave the handle in a bad state; reopen for format check
        with Image.open(path) as img:
            fmt = (img.format or "").upper()
            if expected == "png" and fmt != "PNG":
                return f"File extension is .{expected} but content is not a PNG."
            if expected in ("jpg", "jpeg") and fmt not in ("JPEG", "JPG"):
                return f"File extension is .{expected} but content is not a JPEG."
            # Force a full decode to ensure pixels are readable
            img.load()
    except UnidentifiedImageError:
        return f"File could not be opened as a valid {expected.upper()} image."
    except OSError as exc:
        return f"File could not be opened or read: {exc}"
    except Exception as exc:  # noqa: BLE001 — surface as readable validation error
        return f"File could not be opened or read: {exc}"
    return None


def validate_file(file_path: str) -> dict:
    """
    Validate an input drawing file for BlueprintAI preprocessing.

    Checks (in order):
      1. File exists
      2. File is not empty
      3. Extension is supported (.pdf, .png, .jpg, .jpeg)
      4. File can actually be opened / read as that type

    Returns
    -------
    dict
        {
          "valid": bool,
          "file_type": "pdf" | "png" | "jpg" | "jpeg" | None,
          "file_size_bytes": int | None,
          "error": str | None,
        }
    """
    path = Path(file_path)

    # 1. Exists
    if not path.exists():
        return _result(
            valid=False,
            file_type=None,
            file_size_bytes=None,
            error=f"File does not exist: {file_path}",
        )

    if not path.is_file():
        return _result(
            valid=False,
            file_type=None,
            file_size_bytes=None,
            error=f"Path is not a regular file: {file_path}",
        )

    # Size (needed for empty check and success payload)
    try:
        file_size_bytes = path.stat().st_size
    except OSError as exc:
        return _result(
            valid=False,
            file_type=None,
            file_size_bytes=None,
            error=f"Unable to read file size: {exc}",
        )

    # 2. Not empty
    if file_size_bytes <= 0:
        return _result(
            valid=False,
            file_type=None,
            file_size_bytes=0,
            error="File is empty.",
        )

    # 3. Supported extension
    suffix = path.suffix.lower()
    file_type = SUPPORTED_EXTENSIONS.get(suffix)
    if file_type is None:
        allowed = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        return _result(
            valid=False,
            file_type=None,
            file_size_bytes=file_size_bytes,
            error=f"Unsupported file type '{suffix}'. Allowed: {allowed}",
        )

    # 4. Can be opened / read as the claimed type
    if file_type == "pdf":
        read_error = _can_read_pdf(path)
    else:
        read_error = _can_read_image(path, expected=file_type)

    if read_error is not None:
        return _result(
            valid=False,
            file_type=file_type,
            file_size_bytes=file_size_bytes,
            error=read_error,
        )

    return _result(
        valid=True,
        file_type=file_type,
        file_size_bytes=file_size_bytes,
        error=None,
    )
