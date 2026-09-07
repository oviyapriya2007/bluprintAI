"""Tests for config.py's env-var parsing."""

import os
import unittest

from backend.config import get_settings


class TestPipelineSettings(unittest.TestCase):
    def setUp(self):
        self._saved = {
            k: os.environ.get(k)
            for k in (
                "PIPELINE_MODE",
                "ANTHROPIC_API_KEY",
                "USE_MOCK_CLASSIFY",
                "CALLOUT_MIN_RADIUS_PX",
                "CALLOUT_MAX_RADIUS_PX",
                "CALLOUT_MIN_CIRCULARITY",
            )
        }

    def tearDown(self):
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_defaults_to_hybrid_mode(self):
        os.environ.pop("PIPELINE_MODE", None)
        self.assertEqual(get_settings().pipeline_mode, "hybrid")

    def test_invalid_mode_falls_back_to_hybrid(self):
        os.environ["PIPELINE_MODE"] = "bogus"
        self.assertEqual(get_settings().pipeline_mode, "hybrid")

    def test_legacy_mode_is_respected(self):
        os.environ["PIPELINE_MODE"] = "legacy"
        self.assertEqual(get_settings().pipeline_mode, "legacy")

    def test_no_api_key_forces_mock_classify(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("USE_MOCK_CLASSIFY", None)
        self.assertTrue(get_settings().use_mock_classify)

    def test_api_key_present_disables_mock_by_default(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-fake-test-key"
        os.environ.pop("USE_MOCK_CLASSIFY", None)
        try:
            self.assertFalse(get_settings().use_mock_classify)
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_explicit_use_mock_classify_overrides_api_key(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-fake-test-key"
        os.environ["USE_MOCK_CLASSIFY"] = "true"
        try:
            self.assertTrue(get_settings().use_mock_classify)
        finally:
            os.environ.pop("ANTHROPIC_API_KEY", None)

    def test_radius_config_defaults(self):
        os.environ.pop("CALLOUT_MIN_RADIUS_PX", None)
        os.environ.pop("CALLOUT_MAX_RADIUS_PX", None)
        settings = get_settings()
        self.assertEqual(settings.callout_min_radius_px, 10)
        self.assertEqual(settings.callout_max_radius_px, 80)


if __name__ == "__main__":
    unittest.main()
