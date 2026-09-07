"""
Configuration for the BlueprintAI hybrid detection pipeline (backend/).

Centralizes every tunable so no other module in this package reads
os.environ directly. Values are read lazily via get_settings() so tests
can monkeypatch environment variables cleanly (same pattern already used
by vision_extractor/config.py).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# python-dotenv's bare load_dotenv() does not reliably resolve to
# backend/.env: its default search walks *upward* from a caller-file guess
# that dotenv derives from stack-frame/`__main__` inspection, not from this
# module's own location -- it can land on the repo root (or nowhere) instead
# of backend/, silently leaving ANTHROPIC_API_KEY unset. Same issue, same
# fix already applied in vision_extractor/config.py: resolve backend/.env
# explicitly by this file's own path first.
try:
    from dotenv import load_dotenv

    _ENV_PATH = Path(__file__).resolve().parent / ".env"
    if _ENV_PATH.is_file():
        load_dotenv(_ENV_PATH)
    else:
        load_dotenv()  # last-resort default search
except ImportError:  # python-dotenv is optional; env vars still work without it
    pass


def _str_to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PipelineSettings:
    # "hybrid" (new deterministic + narrow-classify pipeline) or "legacy"
    # (original whole-page vision-only pipeline via vision-extractor).
    pipeline_mode: str

    # classify.py — the only stage that calls an LLM.
    anthropic_api_key: str | None
    claude_model: str
    classify_max_workers: int
    classify_timeout_seconds: float
    use_mock_classify: bool

    # callout_detect.py — OpenCV candidate filtering.
    callout_min_radius_px: int
    callout_max_radius_px: int
    callout_min_circularity: float

    @classmethod
    def load(cls) -> "PipelineSettings":
        mode = os.getenv("PIPELINE_MODE", "hybrid").strip().lower()
        if mode not in {"hybrid", "legacy"}:
            mode = "hybrid"

        api_key = os.getenv("ANTHROPIC_API_KEY") or None
        model = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
        max_workers = _safe_int(os.getenv("CLASSIFY_MAX_WORKERS"), default=8)
        timeout = _safe_float(os.getenv("CLASSIFY_TIMEOUT_SECONDS"), default=30.0)

        use_mock_raw = os.getenv("USE_MOCK_CLASSIFY", "")
        # No API key => force mock mode, same fallback philosophy as
        # vision_extractor.config.Settings (USE_MOCK), so the pipeline
        # always runs out of the box for teammates without a key.
        use_mock = _str_to_bool(use_mock_raw) if use_mock_raw else not bool(api_key)

        min_radius = _safe_int(os.getenv("CALLOUT_MIN_RADIUS_PX"), default=10)
        max_radius = _safe_int(os.getenv("CALLOUT_MAX_RADIUS_PX"), default=80)
        min_circularity = _safe_float(os.getenv("CALLOUT_MIN_CIRCULARITY"), default=0.6)

        return cls(
            pipeline_mode=mode,
            anthropic_api_key=api_key,
            claude_model=model,
            classify_max_workers=max_workers,
            classify_timeout_seconds=timeout,
            use_mock_classify=use_mock,
            callout_min_radius_px=min_radius,
            callout_max_radius_px=max_radius,
            callout_min_circularity=min_circularity,
        )


def _safe_int(value: str | None, *, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _safe_float(value: str | None, *, default: float) -> float:
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def get_settings() -> PipelineSettings:
    """Return a freshly loaded PipelineSettings instance (env may change
    between calls/tests)."""
    return PipelineSettings.load()
