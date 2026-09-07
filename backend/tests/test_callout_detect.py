"""Tests for callout_detect.py.

_padded_bbox and _calibrate_radius_range are pure geometry/statistics
helpers, tested directly. detect_callouts() itself is exercised end-to-end
against a synthetic image (drawn circles on a blank page) rather than a
real engineering drawing, since none is available in this environment --
see the final summary for what still needs manual verification against a
real sample sheet.
"""

import unittest

import numpy as np

from backend.callout_detect import _calibrate_radius_range, _padded_bbox, detect_callouts
from backend.config import PipelineSettings


def _settings(**overrides) -> PipelineSettings:
    base = dict(
        pipeline_mode="hybrid",
        anthropic_api_key=None,
        claude_model="claude-haiku-4-5-20251001",
        classify_max_workers=4,
        classify_timeout_seconds=30.0,
        use_mock_classify=True,
        callout_min_radius_px=10,
        callout_max_radius_px=80,
        callout_min_circularity=0.6,
    )
    base.update(overrides)
    return PipelineSettings(**base)


class TestPaddedBbox(unittest.TestCase):
    def test_padding_applied(self):
        bbox = _padded_bbox(cx=50, cy=50, radius=10, width=200, height=200)
        self.assertEqual(bbox, {"xmin": 30, "ymin": 30, "xmax": 70, "ymax": 70})

    def test_clamped_to_image_bounds_near_edge(self):
        bbox = _padded_bbox(cx=5, cy=5, radius=10, width=200, height=200)
        self.assertEqual(bbox["xmin"], 0)
        self.assertEqual(bbox["ymin"], 0)

    def test_clamped_to_image_bounds_far_edge(self):
        bbox = _padded_bbox(cx=195, cy=195, radius=10, width=200, height=200)
        self.assertEqual(bbox["xmax"], 200)
        self.assertEqual(bbox["ymax"], 200)


class TestCalibrateRadiusRange(unittest.TestCase):
    def test_falls_back_to_config_default_with_few_candidates(self):
        loose = [(100.0, (0, 0), 12.0, 0.9)]
        low, high = _calibrate_radius_range(loose, _settings())
        self.assertEqual((low, high), (10.0, 80.0))

    def test_calibrates_from_distribution_with_enough_candidates(self):
        radii = [10.0, 11.0, 12.0, 12.0, 13.0, 14.0, 50.0]  # 50.0 is an outlier
        loose = [(0.0, (0, 0), r, 0.9) for r in radii]
        low, high = _calibrate_radius_range(loose, _settings())
        median = 12.0
        self.assertAlmostEqual(low, max(10.0, median * 0.4))
        self.assertLess(high, 80.0 * 3)  # outlier does not blow out the ceiling


class TestDetectCalloutsOnSyntheticImage(unittest.TestCase):
    def test_finds_filled_circles(self):
        import cv2

        image = np.full((400, 400, 3), 255, dtype=np.uint8)
        # Six filled circles of the same size -- enough for auto-calibration
        # (_MIN_CANDIDATES_FOR_CALIBRATION == 5) and clearly circular.
        centers = [(60, 60), (140, 60), (220, 60), (60, 140), (140, 140), (220, 140)]
        for cx, cy in centers:
            cv2.circle(image, (cx, cy), 15, (0, 0, 0), thickness=2)

        with _TempImage(image) as path:
            candidates = detect_callouts(path, page_id="test_page")

        self.assertGreaterEqual(len(candidates), len(centers) - 1)  # allow one miss
        for candidate in candidates:
            self.assertTrue(candidate.crop_id.startswith("test_page_c"))
            self.assertIsInstance(candidate.crop_bytes, bytes)
            self.assertGreater(len(candidate.crop_bytes), 0)

    def test_missing_image_raises_value_error(self):
        with self.assertRaises(ValueError):
            detect_callouts("this/path/does/not/exist.png")


class _TempImage:
    """Writes a numpy image to a temp PNG file for the duration of a with-block."""

    def __init__(self, image: np.ndarray):
        self._image = image
        self._path = None

    def __enter__(self) -> str:
        import tempfile

        import cv2

        fd, path = tempfile.mkstemp(suffix=".png")
        import os

        os.close(fd)
        cv2.imwrite(path, self._image)
        self._path = path
        return path

    def __exit__(self, exc_type, exc, tb):
        import os

        if self._path and os.path.exists(self._path):
            os.remove(self._path)


if __name__ == "__main__":
    unittest.main()
