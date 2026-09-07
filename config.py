"""
Processing settings for BlueprintAI document preprocessing.

Adjust DPI, resolution limits, Poppler path, and output paths here.
No AI, network, or storage backends are configured in this module.
"""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


def _default_poppler_path() -> Optional[str]:
    """
    Optional Poppler bin directory for pdf2image (important on Windows).

    Set env var POPPLER_PATH to the folder that contains pdftoppm.exe, e.g.:
      set POPPLER_PATH=C:\\poppler\\Library\\bin
    """
    value = os.environ.get("POPPLER_PATH", "").strip()
    return value or None


@dataclass
class ProcessingConfig:
    """Settings used during document validation and image preprocessing."""

    # Rasterization density when converting PDF pages to images
    dpi: int = 300

    # normalize_resolution bounds (longest side)
    max_dimension: int = 7000
    min_dimension: int = 2000

    # Legacy alias used by older helpers (longest-side cap for in-memory resize)
    max_resolution: int = 4096

    # Directory for intermediate / final processed images
    output_dir: Path = field(default_factory=lambda: Path(__file__).parent / "processed")

    # Poppler binaries directory for pdf2image (None = rely on PATH)
    poppler_path: Optional[str] = field(default_factory=_default_poppler_path)

    # Allowed input extensions (lowercase, with leading dot)
    allowed_extensions: tuple[str, ...] = (".pdf", ".png", ".jpg", ".jpeg")

    # Soft upper bound for input file size (bytes); 50 MB default
    max_file_size_bytes: int = 50 * 1024 * 1024

    # JPEG / PNG save quality hints (used by image_utils when persisting)
    jpeg_quality: int = 95
    png_compress_level: int = 6

    def ensure_output_dir(self) -> Path:
        """Create the output directory if it does not exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        return self.output_dir


# Module-level default instance (callers may construct their own)
DEFAULT_CONFIG = ProcessingConfig()
