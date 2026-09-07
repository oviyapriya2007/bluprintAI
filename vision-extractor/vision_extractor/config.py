"""Configuration loaded from environment variables / .env file.

Centralizes every tunable so nothing else in the package reads os.environ
directly. Values are read lazily via Settings() so tests can monkeypatch
environment variables cleanly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .tiling import parse_grid_size

# python-dotenv's default load_dotenv() walks *upward* from the caller's
# working directory looking for a .env file -- it never looks inside
# subdirectories, and the search can miss entirely when this package is
# imported via a sys.path shim from a different project root (e.g.
# run_pipeline.py at the repo root). Resolve explicitly instead, checking
# both the documented location (vision-extractor/.env, per README.md) and
# this package's own directory, so loading is independent of cwd.
_MODULE_ROOT = Path(__file__).resolve().parent.parent  # vision-extractor/
_PACKAGE_DIR = Path(__file__).resolve().parent  # vision-extractor/vision_extractor/

for _env_path in (_MODULE_ROOT / ".env", _PACKAGE_DIR / ".env"):
    if _env_path.is_file():
        load_dotenv(_env_path)
        break
else:
    load_dotenv()  # last-resort default search (e.g. a .env elsewhere on the path)


def _str_to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # Active provider (see extractor.py, claude_client.py). Gemini fields are
    # kept (unused by extractor.py) rather than removed, so switching back
    # is a one-line change, not a config rebuild.
    anthropic_api_key: str | None
    anthropic_model: str
    gemini_api_key: str | None
    gemini_model: str
    use_mock: bool
    low_confidence_threshold: float
    # Optional tiled callout detection for large drawings (BOM is never tiled).
    callout_tiling_enabled: bool = False
    callout_tile_grid_rows: int = 2
    callout_tile_grid_cols: int = 2
    callout_tile_overlap: float = 0.12  # 12% of cell size (within 10–15%)
    callout_dedupe_iou: float = 0.5
    # Optional second-pass crop verification of each detected callout.
    callout_verification_enabled: bool = False
    normalized_coordinate_max: float = 1000.0

    @classmethod
    def load(cls) -> "Settings":
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") or None
        anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
        gemini_api_key = os.getenv("GEMINI_API_KEY") or None
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        use_mock_raw = os.getenv("USE_MOCK", "false")
        # Mock is explicit development/testing only. Never auto-enable from a
        # missing API key — live mode must fail loudly instead.
        use_mock = _str_to_bool(use_mock_raw)
        threshold_raw = os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.70")
        try:
            threshold = float(threshold_raw)
        except ValueError:
            threshold = 0.70

        tiling_enabled = _str_to_bool(os.getenv("CALLOUT_TILING_ENABLED", "false"))
        try:
            grid_rows, grid_cols = parse_grid_size(
                os.getenv("CALLOUT_TILE_GRID", "2x2"), default=(2, 2)
            )
        except ValueError:
            grid_rows, grid_cols = 2, 2

        overlap_raw = os.getenv("CALLOUT_TILE_OVERLAP", "0.12")
        try:
            overlap = float(overlap_raw)
        except ValueError:
            overlap = 0.12
        # Keep overlap in the intended 10–15% band unless explicitly set outside.
        if not 0.0 <= overlap < 1.0:
            overlap = 0.12

        iou_raw = os.getenv("CALLOUT_DEDUPE_IOU", "0.5")
        try:
            dedupe_iou = float(iou_raw)
        except ValueError:
            dedupe_iou = 0.5

        verification_enabled = _str_to_bool(
            os.getenv("CALLOUT_VERIFICATION_ENABLED", "false")
        )

        return cls(
            anthropic_api_key=anthropic_api_key,
            anthropic_model=anthropic_model,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            use_mock=use_mock,
            low_confidence_threshold=threshold,
            callout_tiling_enabled=tiling_enabled,
            callout_tile_grid_rows=grid_rows,
            callout_tile_grid_cols=grid_cols,
            callout_tile_overlap=overlap,
            callout_dedupe_iou=dedupe_iou,
            callout_verification_enabled=verification_enabled,
        )


def get_settings() -> Settings:
    """Return a freshly loaded Settings instance (env may change between calls/tests)."""
    return Settings.load()
