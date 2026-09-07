"""Realistic end-to-end scenario for the intelligence layer.

Exercises build_workspace() directly with a hand-built, realistic 5-BOM /
5-callout dataset covering every case called out in the integration spec:
linked components, a low-confidence component, a BOM item with no callout,
and a drawing callout with no BOM item -- with realistic bounding boxes.

This targets the intelligence (reconciliation/validation) layer specifically,
which is where this logic actually lives and where it's testable
deterministically -- vision-extractor's own extraction accuracy is a
separate concern already covered by its own test suite and by the live
Gemini test in vision-extractor/tests/test_integration.py.
"""

import json
import unittest

from intelligence import build_workspace

# 5 BOM items: items 1-4 have a matching callout, item 5 does not
# (-> missing_callout). Item 4 is deliberately low confidence.
BOM_DATA = [
    {
        "item_number": "1",
        "part_number": "FB-M8-001",
        "part_name": "Hexagonal Flange Bolt M8",
        "quantity": 6,
        "material_specification": "Grade 8.8 Carbon Steel",
        "confidence_score": 0.97,
    },
    {
        "item_number": "2",
        "part_number": "WSH-M8-002",
        "part_name": "Flat Washer M8",
        "quantity": 12,
        "material_specification": "Zinc-Plated Steel",
        "confidence_score": 0.94,
    },
    {
        "item_number": "3",
        "part_number": "BRK-STD-100",
        "part_name": "Standard Mounting Bracket",
        "quantity": 2,
        "material_specification": "6061 Aluminum",
        "confidence_score": 0.96,
    },
    {
        "item_number": "4",
        "part_number": "BRG-6202-Z",
        "part_name": "Ball Bearing 6202-Z",
        "quantity": 4,
        "material_specification": "Chrome Steel",
        "confidence_score": 0.55,  # deliberately low confidence
    },
    {
        "item_number": "5",
        "part_number": "GSK-RUB-045",
        "part_name": "Rubber Gasket",
        "quantity": 8,
        "material_specification": "Nitrile Rubber",
        "confidence_score": 0.92,
        # no matching callout below -> missing_callout
    },
]

# 5 callouts: bubbles 1-4 match BOM items 1-4, bubble 6 has no BOM item
# (-> missing_bom_item / "unmatched callout").
CALLOUT_DATA = [
    {
        "bubble_number": "1",
        "location_description": "Upper-left mounting bracket",
        "bounding_box": {"xmin": 185, "ymin": 412, "xmax": 230, "ymax": 458},
        "confidence_score": 0.95,
    },
    {
        "bubble_number": "2",
        "location_description": "Adjacent to bolt callout 1",
        "bounding_box": {"xmin": 240, "ymin": 412, "xmax": 285, "ymax": 458},
        "confidence_score": 0.93,
    },
    {
        "bubble_number": "3",
        "location_description": "Center bracket mount",
        "bounding_box": {"xmin": 300, "ymin": 400, "xmax": 350, "ymax": 445},
        "confidence_score": 0.96,
    },
    {
        "bubble_number": "4",
        "location_description": "Lower shaft assembly, bearing seat",
        "bounding_box": {"xmin": 150, "ymin": 520, "xmax": 200, "ymax": 565},
        "confidence_score": 0.90,
    },
    {
        "bubble_number": "6",  # no BOM item 6 -> unmatched callout
        "location_description": "Unidentified fastener, bottom edge",
        "bounding_box": {"xmin": 610, "ymin": 600, "xmax": 650, "ymax": 640},
        "confidence_score": 0.88,
    },
]


class TestRealisticScenario(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = build_workspace(bom_data=BOM_DATA, callout_data=CALLOUT_DATA)
        cls.components_by_item = {
            c["item_number"]: c for c in cls.workspace["components"] if c["item_number"]
        }
        cls.components_by_bubble = {
            c["bubble_number"]: c for c in cls.workspace["components"] if c["bubble_number"]
        }
        cls.validation_by_id = {
            v["component_id"]: v for v in cls.workspace["validation"]["issues"]
        }

    def test_input_shape_matches_spec(self):
        self.assertEqual(len(BOM_DATA), 5)
        self.assertEqual(len(CALLOUT_DATA), 5)

    def test_four_linked_components(self):
        summary = self.workspace["validation"]["summary"]
        self.assertEqual(summary["linked_items"], 4)  # items 1,2,3,4

    def test_bubble_to_item_to_component_relationship(self):
        # Bubble 3 -> BOM item 3 -> cmp with part number/name/qty/bbox/confidence.
        component = self.components_by_bubble["3"]
        self.assertEqual(component["item_number"], "3")
        self.assertEqual(component["part_number"], "BRK-STD-100")
        self.assertEqual(component["part_name"], "Standard Mounting Bracket")
        self.assertEqual(component["quantity"], 2)
        self.assertEqual(
            component["bounding_box"],
            {"xmin": 300.0, "ymin": 400.0, "xmax": 350.0, "ymax": 445.0},
        )
        validation = self.validation_by_id[component["id"]]
        self.assertEqual(validation["status"], "linked")

    def test_low_confidence_component_flagged_for_review(self):
        component = self.components_by_item["4"]
        validation = self.validation_by_id[component["id"]]
        self.assertEqual(validation["status"], "review_required")
        self.assertTrue(any(i["type"] == "low_confidence" for i in validation["issues"]))
        # combined confidence = min(bom=0.55, callout=0.90) = 0.55
        self.assertAlmostEqual(component["confidence_score"], 0.55)

    def test_missing_callout_for_bom_item_5(self):
        component = self.components_by_item["5"]
        self.assertIsNone(component["bubble_number"])
        self.assertIsNone(component["bounding_box"])
        validation = self.validation_by_id[component["id"]]
        self.assertEqual(validation["status"], "missing_callout")

    def test_unmatched_callout_bubble_6(self):
        component = self.components_by_bubble["6"]
        self.assertIsNone(component["item_number"])
        self.assertIsNone(component["part_number"])
        validation = self.validation_by_id[component["id"]]
        self.assertEqual(validation["status"], "missing_bom_item")

    def test_workspace_summary_counts(self):
        summary = self.workspace["validation"]["summary"]
        self.assertEqual(summary["total_bom_items"], 5)
        self.assertEqual(summary["total_callouts"], 5)
        self.assertEqual(summary["linked_items"], 4)
        self.assertEqual(summary["missing_callouts"], 1)
        self.assertEqual(summary["missing_bom_items"], 1)
        self.assertEqual(summary["low_confidence_items"], 1)

    def test_procurement_calculated_for_known_parts(self):
        component = self.components_by_item["1"]  # FB-M8-001 is in the mock catalog
        procurement = component["procurement_data"]
        self.assertEqual(procurement["estimated_unit_cost_usd"], 35.00)
        self.assertEqual(procurement["estimated_total_cost_usd"], 210.00)  # 6 * 35.00
        self.assertTrue(procurement["estimated"])

    def test_procurement_summary_is_present(self):
        summary = self.workspace["procurement_summary"]
        self.assertIn("estimated_total_cost_usd", summary)
        self.assertGreater(summary["items_with_price"], 0)

    def test_workspace_is_json_serializable(self):
        json.dumps(self.workspace)


if __name__ == "__main__":
    unittest.main()
