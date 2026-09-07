"""Integration tests for the top-level run_pipeline() entry point.

Exercises the real document-processor -> vision-extractor -> intelligence
chain. The deterministic tests below force vision-extractor's USE_MOCK=true
so pipeline *wiring* is verified quickly and reproducibly, independent of
network access, API quota, or how well Gemini happens to read one sample
image. The real live Gemini path is covered separately by
TestRunPipelineLiveGemini (skipped automatically without a configured key)
and by vision-extractor/tests/test_integration.py.
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

from run_pipeline import run_pipeline

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DRAWING = ROOT / "vision-extractor" / "examples" / "sample_input" / "sample_drawing.png"


def _force_mock_mode() -> dict[str, str | None]:
    """Set USE_MOCK=true for the duration of a test class; return the
    previous env values so they can be restored exactly."""
    previous = {"USE_MOCK": os.environ.get("USE_MOCK")}
    os.environ["USE_MOCK"] = "true"
    return previous


def _restore_env(previous: dict[str, str | None]) -> None:
    for key, value in previous.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


class TestRunPipelineHappyPath(unittest.TestCase):
    """Deterministic pipeline-wiring check using vision-extractor's mock data."""

    @classmethod
    def setUpClass(cls):
        cls._previous_env = _force_mock_mode()
        cls.workspace = run_pipeline(str(SAMPLE_DRAWING))

    @classmethod
    def tearDownClass(cls):
        _restore_env(cls._previous_env)

    def test_pipeline_status_ok(self):
        self.assertEqual(self.workspace["metadata"]["pipeline_status"], "ok")
        self.assertEqual(self.workspace["metadata"]["pipeline_errors"], [])

    def test_components_were_reconciled(self):
        components = self.workspace["components"]
        self.assertEqual(len(components), 5)  # vision-extractor mock data has 5 items
        for component in components:
            self.assertIsNotNone(component["item_number"])
            self.assertIsNotNone(component["bubble_number"])
            self.assertIsNotNone(component["bounding_box"])

    def test_low_confidence_item_flagged(self):
        summary = self.workspace["validation"]["summary"]
        self.assertGreaterEqual(summary["low_confidence_items"], 1)

    def test_procurement_attached(self):
        summary = self.workspace["procurement_summary"]
        self.assertGreater(summary["items_with_price"], 0)

    def test_metadata_traceability_fields(self):
        metadata = self.workspace["metadata"]
        self.assertTrue(metadata["document_id"].startswith("doc_"))
        self.assertEqual(metadata["drawing_number"], "ASM-001")
        self.assertTrue(metadata["using_mock_vision_extraction"])
        self.assertEqual(metadata["pages_processed"], 1)

    def test_workspace_is_json_serializable(self):
        json.dumps(self.workspace)  # must not raise

    def test_bom_item_to_bounding_box_relationship_preserved(self):
        # This is what the UI needs: BOM item # -> component -> bounding box.
        component = next(
            c for c in self.workspace["components"] if c["item_number"] == "3"
        )
        self.assertEqual(component["bubble_number"], "3")
        self.assertEqual(
            component["bounding_box"],
            {"xmin": 185.0, "ymin": 412.0, "xmax": 230.0, "ymax": 458.0},
        )


class TestRunPipelineErrorHandling(unittest.TestCase):
    def test_missing_file_does_not_raise(self):
        workspace = run_pipeline(str(ROOT / "does_not_exist.png"))
        self.assertEqual(workspace["metadata"]["pipeline_status"], "failed")
        self.assertEqual(
            workspace["metadata"]["pipeline_errors"][0]["stage"], "document_processing"
        )
        self.assertEqual(workspace["components"], [])

    def test_unsupported_file_type_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad_file = Path(tmp) / "not_a_drawing.txt"
            bad_file.write_text("hello")
            workspace = run_pipeline(str(bad_file))
        self.assertEqual(workspace["metadata"]["pipeline_status"], "failed")
        self.assertEqual(workspace["components"], [])

    def test_empty_file_path_does_not_raise(self):
        workspace = run_pipeline("")
        self.assertEqual(workspace["metadata"]["pipeline_status"], "failed")
        self.assertEqual(workspace["metadata"]["pipeline_errors"][0]["stage"], "input")

    def test_corrupt_image_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_png = Path(tmp) / "corrupt.png"
            fake_png.write_bytes(b"not a real png")
            workspace = run_pipeline(str(fake_png))
        self.assertEqual(workspace["metadata"]["pipeline_status"], "failed")

    def test_error_workspace_is_json_serializable(self):
        workspace = run_pipeline("")
        json.dumps(workspace)  # must not raise


class TestRunPipelineExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._previous_env = _force_mock_mode()

    @classmethod
    def tearDownClass(cls):
        _restore_env(cls._previous_env)

    def test_pipeline_output_exports_to_excel_and_csv(self):
        from intelligence import export_to_csv, export_to_excel

        workspace = run_pipeline(str(SAMPLE_DRAWING))
        with tempfile.TemporaryDirectory() as tmp:
            excel_path = export_to_excel(workspace, str(Path(tmp) / "out.xlsx"))
            csv_path = export_to_csv(workspace, str(Path(tmp) / "out.csv"))
            self.assertTrue(Path(excel_path).exists())
            self.assertTrue(Path(csv_path).exists())


class TestRunPipelineLiveGemini(unittest.TestCase):
    """Runs the pipeline against the real Gemini API, when a key is configured.

    Deliberately does not assert exact component counts or values -- real
    extraction quality/output depends on Gemini and the input image, which
    is vision-extractor's concern, not this pipeline's wiring. This only
    confirms the live path is actually reachable end-to-end (no exceptions,
    a well-formed result) when a real key is present.
    """

    @classmethod
    def setUpClass(cls):
        # Import after path bootstrap (run_pipeline already imported above)
        # so vision_extractor.config's .env loading has already happened.
        from vision_extractor.config import get_settings

        cls._has_key = bool(get_settings().gemini_api_key)

    def test_live_pipeline_run_does_not_crash(self):
        if not self._has_key:
            self.skipTest("No GEMINI_API_KEY configured; skipping live Gemini pipeline test")

        previous = {"USE_MOCK": os.environ.get("USE_MOCK")}
        os.environ["USE_MOCK"] = "false"
        try:
            # isolate_regions=False here: this test is a wiring smoke test
            # (does the live path complete without raising), not an
            # accuracy check -- region-isolation correctness is verified
            # separately. Skipping it keeps this test to 2 Gemini calls
            # instead of 4, so routine test runs don't take minutes.
            workspace = run_pipeline(str(SAMPLE_DRAWING), isolate_regions=False)
        finally:
            _restore_env(previous)

        self.assertIn(workspace["metadata"]["pipeline_status"], ("ok", "partial"))
        self.assertFalse(workspace["metadata"]["using_mock_vision_extraction"])
        json.dumps(workspace)  # must be JSON-serializable regardless of content


if __name__ == "__main__":
    unittest.main()
