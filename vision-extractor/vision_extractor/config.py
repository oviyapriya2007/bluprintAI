"""Configuration loaded from environment variables / .env file.

Centralizes every tunable so nothing else in the package reads os.environ
directly. Values are read lazily via Settings() so tests can monkeypatch
environment variables cleanly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _str_to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str
    use_mock: bool
    low_confidence_threshold: float
    normalized_coordinate_max: float = 1000.0

    @classmethod
    def load(cls) -> "Settings":
        api_key = os.getenv("GEMINI_API_KEY") or None
        model = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
        use_mock_raw = os.getenv("USE_MOCK", "")
        # No API key => force mock mode regardless of USE_MOCK, so the
        # module always works out of the box for teammates without a key.
        use_mock = _str_to_bool(use_mock_raw) if use_mock_raw else not bool(api_key)
        threshold_raw = os.getenv("LOW_CONFIDENCE_THRESHOLD", "0.70")
        try:
            threshold = float(threshold_raw)
        except ValueError:
            threshold = 0.70

        return cls(
            gemini_api_key=api_key,
            gemini_model=model,
            use_mock=use_mock,
            low_confidence_threshold=threshold,
        )


def get_settings() -> Settings:
    """Return a freshly loaded Settings instance (env may change between calls/tests)."""
    return Settings.load()
