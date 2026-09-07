"""Smoke tests for reconcile.py -- pure Python, no LLM/CV/OCR involved.

Feeds hand-written fake BOM rows and balloon-classification results
directly, exactly as the module's own docstring promises is possible.
"""

import unittest

from backend.reconcile import normalize_item_number, reconcile


class TestNormalizeItemNumber(unittest.TestCase):
    def test_int(self):
        self.assertEqual(normalize_item_number(3), "3")

    def test_string_digit(self):
        self.assertEqual(normalize_item_number("3"), "3")

    def test_leading_zeros_stripped(self):
        self.assertEqual(normalize_item_number("03"), "3")

    def test_string_with_surrounding_text(self):
        self.assertEqual(normalize_item_number("Item 12"), "12")

    def test_float_whole_number(self):
        self.assertEqual(normalize_item_number(4.0), "4")

    def test_float_fractional_is_ambiguous(self):
        self.assertIsNone(normalize_item_number(3.5))

    def test_multiple_digit_runs_is_ambiguous(self):
        self.assertIsNone(normalize_item_number("3-4"))

    def test_none_is_ambiguous(self):
        self.assertIsNone(normalize_item_number(None))

    def test_empty_string_is_ambiguous(self):
        self.assertIsNone(normalize_item_number(""))

    def test_bool_is_ambiguous(self):
        self.assertIsNone(normalize_item_number(True))

    def test_no_digits_is_ambiguous(self):
        self.assertIsNone(normalize_item_number("abc"))


class TestReconcile(unittest.TestCase):
    def test_matched(self):
        bom_items = [{"item_no": "1", "description": "Bolt", "qty": 4, "material": "Steel"}]
        balloons = [{"crop_id": "c1", "is_balloon": True, "number": 1, "confidence": 0.9}]
        result = reconcile(bom_items, balloons)
        self.assertEqual(len(result["matched"]), 1)
        self.assertEqual(result["matched"][0]["item_no"], "1")
        self.assertEqual(result["matched"][0]["crop_ids"], ["c1"])
        self.assertEqual(result["missing"], [])
        self.assertEqual(result["extra"], [])
        self.assertEqual(result["duplicates"], [])

    def test_missing_bom_item_with_no_balloon(self):
        bom_items = [{"item_no": "1"}, {"item_no": "2"}]
        balloons = [{"crop_id": "c1", "is_balloon": True, "number": 1, "confidence": 0.9}]
        result = reconcile(bom_items, balloons)
        self.assertEqual([m["item_no"] for m in result["missing"]], ["2"])

    def test_extra_balloon_with_no_bom_row(self):
        bom_items = [{"item_no": "1"}]
        balloons = [
            {"crop_id": "c1", "is_balloon": True, "number": 1, "confidence": 0.9},
            {"crop_id": "c2", "is_balloon": True, "number": 99, "confidence": 0.9},
        ]
        result = reconcile(bom_items, balloons)
        self.assertEqual([e["number"] for e in result["extra"]], ["99"])

    def test_duplicate_balloon_number(self):
        bom_items = [{"item_no": "1"}]
        balloons = [
            {"crop_id": "c1", "is_balloon": True, "number": 1, "confidence": 0.9},
            {"crop_id": "c2", "is_balloon": True, "number": 1, "confidence": 0.8},
        ]
        result = reconcile(bom_items, balloons)
        self.assertEqual(len(result["duplicates"]), 1)
        self.assertEqual(result["duplicates"][0]["number"], "1")
        self.assertEqual(result["duplicates"][0]["count"], 2)
        # A duplicated-but-matched number still shows up as matched too.
        self.assertEqual(len(result["matched"]), 1)
        self.assertEqual(result["matched"][0]["balloon_count"], 2)

    def test_non_balloon_results_are_ignored(self):
        bom_items = [{"item_no": "1"}]
        balloons = [
            {"crop_id": "c1", "is_balloon": False, "number": None, "confidence": 0.0},
        ]
        result = reconcile(bom_items, balloons)
        self.assertEqual(result["matched"], [])
        self.assertEqual([m["item_no"] for m in result["missing"]], ["1"])
        self.assertEqual(result["extra"], [])

    def test_unnormalizable_numbers_are_dropped_not_crashed_on(self):
        bom_items = [{"item_no": "3-4"}, {"item_no": None}, {"item_no": "5"}]
        balloons = [{"crop_id": "c1", "is_balloon": True, "number": 5, "confidence": 0.9}]
        result = reconcile(bom_items, balloons)
        self.assertEqual([m["item_no"] for m in result["matched"]], ["5"])

    def test_empty_inputs(self):
        result = reconcile([], [])
        self.assertEqual(result, {"matched": [], "missing": [], "extra": [], "duplicates": []})

    def test_accepts_dataclass_like_objects_not_just_dicts(self):
        class FakeResult:
            def __init__(self, crop_id, is_balloon, number):
                self.crop_id = crop_id
                self.is_balloon = is_balloon
                self.number = number

        bom_items = [{"item_no": "7"}]
        balloons = [FakeResult("c1", True, 7)]
        result = reconcile(bom_items, balloons)
        self.assertEqual([m["item_no"] for m in result["matched"]], ["7"])


if __name__ == "__main__":
    unittest.main()
