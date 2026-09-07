import json
import unittest

from intelligence import build_workspace
from intelligence.sample_data import SAMPLE_BOM, SAMPLE_CALLOUTS


class TestPipeline(unittest.TestCase):
    def test_end_to_end_workspace_generation(self):
        workspace = build_workspace(bom_data=SAMPLE_BOM, callout_data=SAMPLE_CALLOUTS)

        self.assertIn("components", workspace)
        self.assertIn("validation", workspace)
        self.assertIn("procurement_summary", workspace)
        self.assertIn("metadata", workspace)

        self.assertEqual(
            len(workspace["components"]), len(workspace["validation"]["issues"])
        )

        # Every component the sample data implies must be present.
        item_numbers = {c["item_number"] for c in workspace["components"]}
        self.assertIn("9", item_numbers)  # missing_callout case
        bubble_numbers = {c["bubble_number"] for c in workspace["components"]}
        self.assertIn("14", bubble_numbers)  # missing_bom_item case

        summary = workspace["validation"]["summary"]
        self.assertGreater(summary["missing_callouts"], 0)
        self.assertGreater(summary["missing_bom_items"], 0)
        self.assertGreater(summary["low_confidence_items"], 0)
        self.assertGreater(summary["duplicate_bom_items"], 0)
        self.assertGreater(summary["duplicate_callouts"], 0)

        procurement_summary = workspace["procurement_summary"]
        self.assertGreater(procurement_summary["items_without_price"], 0)
        self.assertGreater(procurement_summary["items_with_price"], 0)

    def test_workspace_is_json_serializable(self):
        workspace = build_workspace(bom_data=SAMPLE_BOM, callout_data=SAMPLE_CALLOUTS)
        # Must not raise -- this is the contract the UI layer depends on.
        serialized = json.dumps(workspace)
        self.assertIsInstance(serialized, str)

    def test_empty_input_produces_empty_but_valid_workspace(self):
        workspace = build_workspace(bom_data=[], callout_data=[])
        self.assertEqual(workspace["components"], [])
        self.assertEqual(workspace["validation"]["summary"]["total_bom_items"], 0)
        self.assertEqual(workspace["procurement_summary"]["items_with_price"], 0)

    def test_custom_confidence_threshold_flows_through(self):
        bom = [
            {
                "item_number": "1",
                "part_name": "Bolt",
                "quantity": 1,
                "material_specification": "Steel",
                "confidence_score": 0.80,
            }
        ]
        callouts = [{"bubble_number": "1", "confidence_score": 0.80}]
        strict_workspace = build_workspace(
            bom_data=bom, callout_data=callouts, confidence_threshold=0.95
        )
        self.assertEqual(strict_workspace["validation"]["issues"][0]["status"], "review_required")

        lenient_workspace = build_workspace(
            bom_data=bom, callout_data=callouts, confidence_threshold=0.50
        )
        self.assertEqual(lenient_workspace["validation"]["issues"][0]["status"], "linked")


if __name__ == "__main__":
    unittest.main()
