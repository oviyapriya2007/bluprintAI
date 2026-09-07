"""Tests for classify.py's response parsing -- no network calls.

_parse_classification is pure (text in, ClassificationResult out), so it
is exercised directly with hand-written Claude-response-shaped strings.
classify_candidates() is exercised only in mock mode (USE_MOCK_CLASSIFY),
which also makes no network calls.
"""

import unittest

from backend.callout_detect import CalloutCandidate
from backend.classify import _parse_classification, classify_candidates


def _candidate(crop_id: str = "page_c0001") -> CalloutCandidate:
    return CalloutCandidate(
        crop_id=crop_id,
        x=10,
        y=10,
        radius=5.0,
        bbox={"xmin": 0, "ymin": 0, "xmax": 20, "ymax": 20},
        circularity=0.9,
        crop_bytes=b"not-a-real-png",
    )


class TestParseClassification(unittest.TestCase):
    def test_valid_balloon_response(self):
        result = _parse_classification("c1", '{"is_balloon": true, "number": 7, "confidence": 0.92}')
        self.assertTrue(result.is_balloon)
        self.assertEqual(result.number, 7)
        self.assertAlmostEqual(result.confidence, 0.92)
        self.assertIsNone(result.error)

    def test_valid_non_balloon_response(self):
        result = _parse_classification(
            "c1", '{"is_balloon": false, "number": null, "confidence": 0.1}'
        )
        self.assertFalse(result.is_balloon)
        self.assertIsNone(result.number)

    def test_response_with_surrounding_prose(self):
        text = 'Sure, here is the answer:\n{"is_balloon": true, "number": 3, "confidence": 0.8}\nHope that helps!'
        result = _parse_classification("c1", text)
        self.assertTrue(result.is_balloon)
        self.assertEqual(result.number, 3)

    def test_balloon_true_but_no_number_is_downgraded(self):
        # A numberless "yes" must not silently match nothing in reconcile.py.
        result = _parse_classification("c1", '{"is_balloon": true, "number": null, "confidence": 0.5}')
        self.assertFalse(result.is_balloon)

    def test_confidence_is_clamped(self):
        result = _parse_classification("c1", '{"is_balloon": true, "number": 1, "confidence": 5.0}')
        self.assertEqual(result.confidence, 1.0)

    def test_unparseable_text(self):
        result = _parse_classification("c1", "I cannot help with that.")
        self.assertFalse(result.is_balloon)
        self.assertIsNone(result.number)
        self.assertEqual(result.confidence, 0.0)
        self.assertIsNotNone(result.error)

    def test_invalid_json(self):
        result = _parse_classification("c1", "{is_balloon: true, number: 3}")
        self.assertFalse(result.is_balloon)
        self.assertIsNotNone(result.error)

    def test_non_integer_number_string_is_coerced(self):
        result = _parse_classification("c1", '{"is_balloon": true, "number": "12", "confidence": 0.9}')
        self.assertEqual(result.number, 12)


class TestClassifyCandidatesMockMode(unittest.TestCase):
    def test_empty_input(self):
        self.assertEqual(classify_candidates([]), [])

    def test_mock_mode_returns_one_result_per_candidate(self):
        import os

        previous = os.environ.get("USE_MOCK_CLASSIFY")
        os.environ["USE_MOCK_CLASSIFY"] = "true"
        try:
            candidates = [_candidate("a"), _candidate("b")]
            results = classify_candidates(candidates)
        finally:
            if previous is None:
                os.environ.pop("USE_MOCK_CLASSIFY", None)
            else:
                os.environ["USE_MOCK_CLASSIFY"] = previous

        self.assertEqual(len(results), 2)
        self.assertEqual({r.crop_id for r in results}, {"a", "b"})
        self.assertTrue(all(r.is_balloon for r in results))


if __name__ == "__main__":
    unittest.main()
