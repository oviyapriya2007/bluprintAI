"""Automated tests for the FastAPI backend (app.py)."""

import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import app
from tests.test_realistic_scenario import BOM_DATA, CALLOUT_DATA

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DRAWING = ROOT / "vision-extractor" / "examples" / "sample_input" / "sample_drawing.png"

client = TestClient(app)


class TestHealthEndpoint(unittest.TestCase):
    def test_health_ok(self):
        response = client.get("/health")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(
            set(body["stages"]), {"document_processor", "vision_extractor", "intelligence"}
        )
        for stage_result in body["stages"].values():
            self.assertEqual(stage_result, "ok")


class TestProcessEndpoint(unittest.TestCase):
    def test_process_valid_drawing_returns_workspace(self):
        # Whichever vision-extraction mode is configured in the environment
        # (mock or live) is exercised here -- live Gemini's exact output for
        # one sample image can vary between calls, so this only asserts the
        # response is well-formed and the pipeline reached a usable state,
        # not an exact extraction result.
        with open(SAMPLE_DRAWING, "rb") as fh:
            response = client.post(
                "/process", files={"file": ("sample_drawing.png", fh, "image/png")}
            )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        for key in ("components", "validation", "procurement_summary", "metadata"):
            self.assertIn(key, body)
        self.assertIn(body["metadata"]["pipeline_status"], ("ok", "partial"))

    def test_process_unsupported_file_type_returns_400(self):
        response = client.post(
            "/process", files={"file": ("notes.txt", b"hello", "text/plain")}
        )
        self.assertEqual(response.status_code, 400)

    def test_process_corrupt_image_returns_422_with_details(self):
        response = client.post(
            "/process", files={"file": ("corrupt.png", b"not a real png", "image/png")}
        )
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body["metadata"]["pipeline_status"], "failed")
        self.assertEqual(body["metadata"]["pipeline_errors"][0]["stage"], "document_processing")


class TestExportEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from intelligence import build_workspace

        cls.workspace = build_workspace(bom_data=BOM_DATA, callout_data=CALLOUT_DATA)

    def test_export_excel_returns_xlsx_file(self):
        response = client.post("/export/excel", json=self.workspace)
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response.headers["content-type"])
        self.assertIn("BlueprintAI_BOM.xlsx", response.headers["content-disposition"])
        self.assertGreater(len(response.content), 0)

    def test_export_csv_returns_csv_file(self):
        response = client.post("/export/csv", json=self.workspace)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers["content-type"])
        self.assertIn("BlueprintAI_BOM.csv", response.headers["content-disposition"])
        body = response.content.decode("utf-8")
        self.assertIn("Item Number", body)
        self.assertIn("FB-M8-001", body)

    def test_export_rejects_non_workspace_body(self):
        response = client.post("/export/excel", json={"not": "a workspace"})
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
