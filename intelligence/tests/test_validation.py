import unittest

from intelligence.reconciliation import reconcile_bom_and_callouts
from intelligence.validation import DEFAULT_CONFIDENCE_THRESHOLD, validate_workspace


class TestValidation(unittest.TestCase):
    def test_low_confidence_flagged(self):
        bom = [{"item_number": "1", "part_name": "A", "quantity": 1, "confidence_score": 0.5}]
        callouts = [{"bubble_number": "1", "confidence_score": 0.9}]
        result = reconcile_bom_and_callouts(bom, callouts)
        validation = validate_workspace(result.components)
        record = validation["issues"][0]
        self.assertEqual(record["status"], "review_required")
        types = {i["type"] for i in record["issues"]}
        self.assertIn("low_confidence", types)

    def test_missing_confidence_flagged(self):
        bom = [{"item_number": "1", "part_name": "A", "quantity": 1}]
        callouts = [{"bubble_number": "1"}]
        result = reconcile_bom_and_callouts(bom, callouts)
        validation = validate_workspace(result.components)
        record = validation["issues"][0]
        types = {i["type"] for i in record["issues"]}
        self.assertIn("confidence_unavailable", types)
        self.assertEqual(record["status"], "review_required")

    def test_combined_confidence_uses_minimum(self):
        bom = [{"item_number": "1", "confidence_score": 0.97}]
        callouts = [{"bubble_number": "1", "confidence_score": 0.60}]
        result = reconcile_bom_and_callouts(bom, callouts)
        self.assertAlmostEqual(result.components[0].confidence_score, 0.60)

    def test_combined_confidence_single_source(self):
        bom = [{"item_number": "1", "confidence_score": 0.80}]
        callouts = [{"bubble_number": "1"}]
        result = reconcile_bom_and_callouts(bom, callouts)
        self.assertAlmostEqual(result.components[0].confidence_score, 0.80)

    def test_clean_component_is_linked(self):
        bom = [
            {
                "item_number": "1",
                "part_name": "Bolt",
                "quantity": 6,
                "material_specification": "Steel",
                "confidence_score": 0.97,
            }
        ]
        callouts = [{"bubble_number": "1", "confidence_score": 0.95}]
        result = reconcile_bom_and_callouts(bom, callouts)
        validation = validate_workspace(result.components)
        record = validation["issues"][0]
        self.assertEqual(record["status"], "linked")
        self.assertEqual(record["issues"], [])

    def test_missing_callout_status(self):
        bom = [{"item_number": "9", "part_name": "Screw", "quantity": 1}]
        result = reconcile_bom_and_callouts(bom, [])
        validation = validate_workspace(result.components)
        self.assertEqual(validation["issues"][0]["status"], "missing_callout")
        self.assertEqual(validation["summary"]["missing_callouts"], 1)

    def test_missing_bom_item_status(self):
        result = reconcile_bom_and_callouts([], [{"bubble_number": "14"}])
        validation = validate_workspace(result.components)
        self.assertEqual(validation["issues"][0]["status"], "missing_bom_item")
        self.assertEqual(validation["summary"]["missing_bom_items"], 1)

    def test_ambiguous_identifier_status_is_invalid(self):
        result = reconcile_bom_and_callouts(
            [{"item_number": "Item 3-4"}], []
        )
        validation = validate_workspace(result.components)
        self.assertEqual(validation["issues"][0]["status"], "invalid")

    def test_missing_required_field_flagged(self):
        bom = [{"item_number": "1"}]  # no part_name, no quantity, no material
        callouts = [{"bubble_number": "1", "confidence_score": 0.95}]
        result = reconcile_bom_and_callouts(bom, callouts)
        result.components[0].bom_confidence = 0.95  # keep confidence high for this test
        result.components[0].confidence_score = 0.95
        validation = validate_workspace(result.components)
        types = [i["type"] for i in validation["issues"][0]["issues"]]
        self.assertIn("missing_field", types)

    def test_custom_threshold_is_respected(self):
        bom = [{"item_number": "1", "confidence_score": 0.80}]
        callouts = [{"bubble_number": "1", "confidence_score": 0.80}]
        result = reconcile_bom_and_callouts(bom, callouts)
        validation = validate_workspace(result.components, confidence_threshold=0.90)
        types = {i["type"] for i in validation["issues"][0]["issues"]}
        self.assertIn("low_confidence", types)
        # And the default threshold used elsewhere is unaffected.
        self.assertEqual(DEFAULT_CONFIDENCE_THRESHOLD, 0.75)


if __name__ == "__main__":
    unittest.main()
