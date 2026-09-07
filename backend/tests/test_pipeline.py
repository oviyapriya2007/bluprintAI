"""Tests for pipeline.py's pure adapter/conversion functions -- the glue
between backend/'s stage outputs and intelligence.build_workspace's
contract (contracts/README.md). No ingest/OpenCV/OCR/Claude calls; the
callout_detect.CalloutCandidate and classify.ClassificationResult objects
used below are hand-constructed fakes.
"""

import unittest

from backend.callout_detect import CalloutCandidate
from backend.classify import ClassificationResult
from backend.ingest import IngestedPage
from backend.pipeline import (
    _bbox_px_to_full_page_norm,
    _bom_row_to_bom_data,
    _classification_to_callout_data,
    _crop_origin_px,
    _empty_workspace,
)


class TestBomRowToBomData(unittest.TestCase):
    def test_maps_fields(self):
        row = {"item_no": "3", "description": "Hex Bolt", "qty": 6, "material": "Steel"}
        data = _bom_row_to_bom_data(row)
        self.assertEqual(data["item_number"], "3")
        self.assertEqual(data["description"], "Hex Bolt")
        self.assertEqual(data["quantity"], 6)
        self.assertEqual(data["material_specification"], "Steel")

    def test_missing_optional_fields(self):
        data = _bom_row_to_bom_data({"item_no": "1"})
        self.assertEqual(data["item_number"], "1")
        self.assertEqual(data["description"], "")
        self.assertIsNone(data["quantity"])
        self.assertIsNone(data["material_specification"])


class TestBboxPxToFullPageNorm(unittest.TestCase):
    def test_full_page_no_crop_offset(self):
        bbox = {"xmin": 100, "ymin": 100, "xmax": 200, "ymax": 200}
        norm = _bbox_px_to_full_page_norm(
            bbox, crop_origin_x_px=0, crop_origin_y_px=0, full_page_width_px=1000, full_page_height_px=1000
        )
        self.assertEqual(norm, {"xmin": 100.0, "ymin": 100.0, "xmax": 200.0, "ymax": 200.0})

    def test_crop_offset_is_applied(self):
        bbox = {"xmin": 0, "ymin": 0, "xmax": 50, "ymax": 50}
        norm = _bbox_px_to_full_page_norm(
            bbox,
            crop_origin_x_px=500,
            crop_origin_y_px=500,
            full_page_width_px=1000,
            full_page_height_px=1000,
        )
        self.assertEqual(norm, {"xmin": 500.0, "ymin": 500.0, "xmax": 550.0, "ymax": 550.0})

    def test_clamped_to_0_1000(self):
        bbox = {"xmin": -10, "ymin": 0, "xmax": 2000, "ymax": 50}
        norm = _bbox_px_to_full_page_norm(
            bbox, crop_origin_x_px=0, crop_origin_y_px=0, full_page_width_px=1000, full_page_height_px=1000
        )
        self.assertEqual(norm["xmin"], 0.0)
        self.assertEqual(norm["xmax"], 1000.0)


def _candidate(bbox=None) -> CalloutCandidate:
    return CalloutCandidate(
        crop_id="page_c0001",
        x=15,
        y=15,
        radius=5.0,
        bbox=bbox or {"xmin": 10, "ymin": 10, "xmax": 20, "ymax": 20},
        circularity=0.9,
        crop_bytes=b"fake",
    )


class TestClassificationToCalloutData(unittest.TestCase):
    def test_balloon_produces_callout_row(self):
        result = ClassificationResult(crop_id="page_c0001", is_balloon=True, number=7, confidence=0.85)
        row = _classification_to_callout_data(
            result,
            _candidate(),
            region_origin_px=(0.0, 0.0),
            full_page_size_px=(100.0, 100.0),
        )
        self.assertIsNotNone(row)
        self.assertEqual(row["bubble_number"], "7")
        self.assertEqual(row["confidence_score"], 0.85)
        self.assertEqual(row["bounding_box"], {"xmin": 100.0, "ymin": 100.0, "xmax": 200.0, "ymax": 200.0})

    def test_non_balloon_returns_none(self):
        result = ClassificationResult(crop_id="page_c0001", is_balloon=False, number=None, confidence=0.1)
        row = _classification_to_callout_data(
            result, _candidate(), region_origin_px=(0.0, 0.0), full_page_size_px=(100.0, 100.0)
        )
        self.assertIsNone(row)

    def test_balloon_with_no_number_returns_none(self):
        result = ClassificationResult(crop_id="page_c0001", is_balloon=True, number=None, confidence=0.5)
        row = _classification_to_callout_data(
            result, _candidate(), region_origin_px=(0.0, 0.0), full_page_size_px=(100.0, 100.0)
        )
        self.assertIsNone(row)


class TestCropOriginPx(unittest.TestCase):
    def test_full_page_used_returns_zero_origin(self):
        page = IngestedPage(page_id="p1", page_number=1, image_path="x", width=1000, height=1000)
        self.assertEqual(_crop_origin_px(page, used_drawing_region=False), (0.0, 0.0))

    def test_drawing_region_offsets_origin(self):
        page = IngestedPage(
            page_id="p1",
            page_number=1,
            image_path="x",
            width=1000,
            height=2000,
            drawing_region_path="crop.png",
            drawing_region={"xmin": 100, "ymin": 200, "xmax": 900, "ymax": 1800},
        )
        origin = _crop_origin_px(page, used_drawing_region=True)
        self.assertEqual(origin, (100.0, 400.0))


class TestEmptyWorkspace(unittest.TestCase):
    def test_shape_matches_build_workspace_contract(self):
        workspace = _empty_workspace("failed", "document_processing", "boom")
        self.assertEqual(workspace["components"], [])
        self.assertIn("summary", workspace["validation"])
        self.assertIn("issues", workspace["validation"])
        self.assertEqual(workspace["metadata"]["pipeline_status"], "failed")
        self.assertEqual(workspace["metadata"]["pipeline_errors"][0]["stage"], "document_processing")
        self.assertEqual(workspace["metadata"]["pipeline_mode"], "hybrid")

    def test_json_serializable(self):
        import json

        json.dumps(_empty_workspace("failed", "input", "bad input"))


if __name__ == "__main__":
    unittest.main()
