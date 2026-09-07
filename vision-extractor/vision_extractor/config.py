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
    normalized_coordinate_max: float = 1000.0

    @classmethod
    def load(cls) -> "Settings":
        anthropic_api_key = os.getenv("ANTHROPIC_API_KEY") or None
        anthropic_model = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5")
        gemini_api_key = os.getenv("GEMINI_API_KEY") or None
        gemini_model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        use_mock_raw = os.getenv("USE_MOCK", "")
        # No API key => force mock mode regardless of USE_MOCK, so the
        # module always works out of the box for teammates without a key.
        # Keyed on the *active* provider's key (Claude), not Gemini's.
        use_mock = (
            _str_to_bool(use_mock_raw) if use_mock_raw else not bool(anthropic_api_key)
        )
        threshold_raw = os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.70")
        try:
            threshold = float(threshold_raw)
        except ValueError:
            threshold = 0.70

        return cls(
            anthropic_api_key=anthropic_api_key,
            anthropic_model=anthropic_model,
            gemini_api_key=gemini_api_key,
            gemini_model=gemini_model,
            use_mock=use_mock,
            low_confidence_threshold=threshold,
        )


def get_settings() -> Settings:
    """Return a freshly loaded Settings instance (env may change between calls/tests)."""
    return Settings.load()
