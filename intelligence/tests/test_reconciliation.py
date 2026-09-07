import unittest

from intelligence.normalization import normalize_identifier
from intelligence.reconciliation import reconcile_bom_and_callouts


class TestNormalization(unittest.TestCase):
    def test_plain_int_and_str_agree(self):
        self.assertEqual(normalize_identifier(3), "3")
        self.assertEqual(normalize_identifier("3"), "3")

    def test_leading_zero(self):
        self.assertEqual(normalize_identifier("03"), "3")

    def test_text_prefixed_forms(self):
        self.assertEqual(normalize_identifier("Item 3"), "3")
        self.assertEqual(normalize_identifier("BUBBLE 3"), "3")
        self.assertEqual(normalize_identifier("Bubble-3"), "3")

    def test_ambiguous_multiple_digit_groups(self):
        self.assertIsNone(normalize_identifier("Item 3-4"))

    def test_ambiguous_no_digits(self):
        self.assertIsNone(normalize_identifier("N/A"))
        self.assertIsNone(normalize_identifier(""))
        self.assertIsNone(normalize_identifier(None))

    def test_non_integer_float_is_ambiguous(self):
        self.assertIsNone(normalize_identifier(3.5))


class TestReconciliation(unittest.TestCase):
    def test_exact_successful_match(self):
        bom = [{"item_number": "1", "part_number": "P1", "confidence_score": 0.9}]
        callouts = [{"bubble_number": "1", "confidence_score": 0.9}]
        result = reconcile_bom_and_callouts(bom, callouts)
        self.assertEqual(len(result.components), 1)
        component = result.components[0]
        self.assertEqual(component.link_status, "matched")
        self.assertEqual(component.item_number, "1")
        self.assertEqual(component.bubble_number, "1")
        self.assertEqual(component.id, "cmp_001")

    def test_normalized_identifier_match(self):
        bom = [{"item_number": "03", "part_number": "P1"}]
        callouts = [{"bubble_number": "Bubble-3"}]
        result = reconcile_bom_and_callouts(bom, callouts)
        self.assertEqual(len(result.components), 1)
        component = result.components[0]
        self.assertEqual(component.link_status, "matched")
        self.assertEqual(component.item_number, "3")
        self.assertEqual(component.bubble_number, "3")
        # Raw values must be preserved for traceability.
        self.assertEqual(component.raw_item_number, "03")
        self.assertEqual(component.raw_bubble_number, "Bubble-3")

    def test_unmatched_bom_item(self):
        bom = [{"item_number": "9", "part_number": "P9"}]
        callouts = []
        result = reconcile_bom_and_callouts(bom, callouts)
        self.assertEqual(len(result.components), 1)
        self.assertEqual(result.components[0].link_status, "bom_only")
        self.assertEqual(len(result.unmatched_bom_items), 1)

    def test_unmatched_callout(self):
        bom = []
        callouts = [{"bubble_number": "14"}]
        result = reconcile_bom_and_callouts(bom, callouts)
        self.assertEqual(len(result.components), 1)
        self.assertEqual(result.components[0].link_status, "callout_only")
        self.assertEqual(len(result.unmatched_callouts), 1)

    def test_duplicate_bom_item(self):
        bom = [
            {"item_number": "3", "part_number": "A"},
            {"item_number": "3", "part_number": "B"},
        ]
        callouts = [{"bubble_number": "3"}]
        result = reconcile_bom_and_callouts(bom, callouts)
        self.assertIn("3", result.duplicate_item_numbers)
        flagged = [c for c in result.components if c.duplicate_item_number]
        self.assertEqual(len(flagged), 2)
        # One of the duplicates still pairs with the single callout.
        statuses = sorted(c.link_status for c in result.components)
        self.assertEqual(statuses, ["bom_only", "matched"])

    def test_duplicate_callout(self):
        bom = [{"item_number": "7", "part_number": "A"}]
        callouts = [{"bubble_number": "7"}, {"bubble_number": "7"}]
        result = reconcile_bom_and_callouts(bom, callouts)
        self.assertIn("7", result.duplicate_bubble_numbers)
        flagged = [c for c in result.components if c.duplicate_bubble_number]
        self.assertEqual(len(flagged), 2)
        statuses = sorted(c.link_status for c in result.components)
        self.assertEqual(statuses, ["callout_only", "matched"])

    def test_ambiguous_identifier_is_not_matched(self):
        bom = [{"item_number": "Item 3-4", "part_number": "AMB"}]
        callouts = [{"bubble_number": "3"}]
        result = reconcile_bom_and_callouts(bom, callouts)
        ambiguous = [c for c in result.components if c.ambiguous_item_number]
        self.assertEqual(len(ambiguous), 1)
        self.assertEqual(ambiguous[0].link_status, "ambiguous")
        # The unrelated bubble "3" is correctly left unmatched, not
        # fuzzily paired with the ambiguous item.
        callout_only = [c for c in result.components if c.link_status == "callout_only"]
        self.assertEqual(len(callout_only), 1)

    def test_stable_ids_are_deterministic_across_runs(self):
        bom = [{"item_number": "2"}, {"item_number": "1"}]
        callouts = [{"bubble_number": "1"}, {"bubble_number": "2"}]
        result_a = reconcile_bom_and_callouts(bom, callouts)
        result_b = reconcile_bom_and_callouts(bom, callouts)
        ids_a = [(c.id, c.item_number) for c in result_a.components]
        ids_b = [(c.id, c.item_number) for c in result_b.components]
        self.assertEqual(ids_a, ids_b)


if __name__ == "__main__":
    unittest.main()
