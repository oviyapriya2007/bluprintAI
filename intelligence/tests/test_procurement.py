import unittest

from intelligence.procurement import calculate_procurement
from intelligence.reconciliation import reconcile_bom_and_callouts


class TestProcurement(unittest.TestCase):
    def test_procurement_calculation(self):
        bom = [
            {
                "item_number": "1",
                "part_number": "FB-M8-001",
                "quantity": 6,
            }
        ]
        result = reconcile_bom_and_callouts(bom, [{"bubble_number": "1"}])
        summary = calculate_procurement(result.components)
        procurement = result.components[0].procurement_data
        self.assertEqual(procurement["estimated_unit_cost_usd"], 35.00)
        self.assertEqual(procurement["estimated_total_cost_usd"], 210.00)
        self.assertTrue(procurement["estimated"])
        self.assertEqual(summary["items_with_price"], 1)
        self.assertEqual(summary["items_without_price"], 0)
        self.assertAlmostEqual(summary["estimated_total_cost_usd"], 210.00)

    def test_missing_procurement_data_does_not_crash(self):
        bom = [{"item_number": "1", "part_number": "UNKNOWN-PART", "quantity": 2}]
        result = reconcile_bom_and_callouts(bom, [{"bubble_number": "1"}])
        summary = calculate_procurement(result.components)
        procurement = result.components[0].procurement_data
        self.assertIsNone(procurement["estimated_unit_cost_usd"])
        self.assertIsNone(procurement["estimated_total_cost_usd"])
        self.assertIsNotNone(procurement["note"])
        self.assertEqual(summary["items_without_price"], 1)

    def test_missing_part_number_does_not_crash(self):
        bom = [{"item_number": "1", "quantity": 2}]
        result = reconcile_bom_and_callouts(bom, [{"bubble_number": "1"}])
        calculate_procurement(result.components)
        procurement = result.components[0].procurement_data
        self.assertIsNone(procurement["estimated_unit_cost_usd"])

    def test_invalid_quantity_omits_total_but_keeps_unit_cost(self):
        bom = [
            {"item_number": "1", "part_number": "FB-M8-001", "quantity": -3},
        ]
        result = reconcile_bom_and_callouts(bom, [{"bubble_number": "1"}])
        calculate_procurement(result.components)
        procurement = result.components[0].procurement_data
        self.assertEqual(procurement["estimated_unit_cost_usd"], 35.00)
        self.assertIsNone(procurement["estimated_total_cost_usd"])

    def test_zero_quantity_omits_total(self):
        bom = [{"item_number": "1", "part_number": "FB-M8-001", "quantity": 0}]
        result = reconcile_bom_and_callouts(bom, [{"bubble_number": "1"}])
        calculate_procurement(result.components)
        procurement = result.components[0].procurement_data
        self.assertIsNone(procurement["estimated_total_cost_usd"])

    def test_catalog_override_extends_default(self):
        bom = [{"item_number": "1", "part_number": "CUSTOM-1", "quantity": 2}]
        result = reconcile_bom_and_callouts(bom, [{"bubble_number": "1"}])
        calculate_procurement(
            result.components,
            catalog={"CUSTOM-1": {"estimated_unit_cost_usd": 10.0, "supplier_source": "X"}},
        )
        procurement = result.components[0].procurement_data
        self.assertEqual(procurement["estimated_unit_cost_usd"], 10.0)
        self.assertEqual(procurement["estimated_total_cost_usd"], 20.0)


if __name__ == "__main__":
    unittest.main()
