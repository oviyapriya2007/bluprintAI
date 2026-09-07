"""Tests for bom_extract.py's pure row/column parsing logic.

These exercise _map_columns / _rows_to_bom_dicts / _split_row_into_cells /
_words_to_text_rows directly with hand-written fake table data -- no
pdfplumber, OpenCV, or Tesseract (and no real drawing) required.
"""

import unittest

from backend.bom_extract import (
    _DEFAULT_GAP_THRESHOLD_PX,
    _infer_gap_threshold,
    _map_columns,
    _rows_to_bom_dicts,
    _split_row_into_cells,
    _table_rows_to_bom_dicts,
    _words_to_text_rows,
)


class TestMapColumns(unittest.TestCase):
    def test_standard_header(self):
        mapping = _map_columns(["Item No", "Description", "Qty", "Material"])
        self.assertEqual(mapping, {"item_no": 0, "description": 1, "qty": 2, "material": 3})

    def test_abbreviated_header(self):
        mapping = _map_columns(["#", "Desc", "Q'ty", "Matl"])
        self.assertEqual(mapping, {"item_no": 0, "description": 1, "qty": 2, "material": 3})

    def test_reordered_header(self):
        mapping = _map_columns(["Material", "Item#", "Qty", "Description"])
        self.assertEqual(mapping, {"material": 0, "item_no": 1, "qty": 2, "description": 3})

    def test_no_recognizable_header_returns_none(self):
        self.assertIsNone(_map_columns(["Foo", "Bar", "Baz"]))

    def test_empty_header_returns_none(self):
        self.assertIsNone(_map_columns(["", None, ""]))


class TestRowsToBomDicts(unittest.TestCase):
    def test_basic_rows(self):
        mapping = {"item_no": 0, "description": 1, "qty": 2, "material": 3}
        rows = [
            ["1", "Hex Bolt M8", "4", "Steel"],
            ["2", "Washer", "8", "Nylon"],
        ]
        result = _rows_to_bom_dicts(rows, mapping)
        self.assertEqual(
            result,
            [
                {
                    "item_no": "1",
                    "description": "Hex Bolt M8",
                    "qty": 4,
                    "material": "Steel",
                    "part_number": None,
                },
                {
                    "item_no": "2",
                    "description": "Washer",
                    "qty": 8,
                    "material": "Nylon",
                    "part_number": None,
                },
            ],
        )

    def test_rows_without_a_parseable_item_no_are_skipped(self):
        mapping = {"item_no": 0, "description": 1, "qty": 2, "material": 3}
        rows = [["", "Note row", "", ""], ["3", "Nut", "2", "Steel"]]
        result = _rows_to_bom_dicts(rows, mapping)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["item_no"], "3")

    def test_blank_rows_are_skipped(self):
        mapping = {"item_no": 0, "description": 1, "qty": 2, "material": 3}
        rows = [["", "", "", ""], ["1", "Bolt", "1", "Steel"]]
        result = _rows_to_bom_dicts(rows, mapping)
        self.assertEqual(len(result), 1)

    def test_missing_optional_columns_are_none(self):
        mapping = {"item_no": 0}
        rows = [["1"]]
        result = _rows_to_bom_dicts(rows, mapping)
        self.assertEqual(
            result,
            [{"item_no": "1", "description": "", "qty": None, "material": None, "part_number": None}],
        )

    def test_item_no_extracts_digits_from_noisy_cell(self):
        mapping = {"item_no": 0, "description": 1, "qty": 2, "material": 3}
        rows = [["Item 07", "Bracket", "x2", "Al"]]
        result = _rows_to_bom_dicts(rows, mapping)
        self.assertEqual(result[0]["item_no"], "07")
        self.assertEqual(result[0]["qty"], 2)


class TestTableRowsToBomDicts(unittest.TestCase):
    def test_full_pdfplumber_style_table(self):
        table = [
            ["ITEM NO.", "DESCRIPTION", "QTY", "MATERIAL"],
            ["1", "Base Plate", "1", "Aluminum 6061"],
            ["2", "Hex Bolt M8x20", "4", "Steel"],
        ]
        result = _table_rows_to_bom_dicts(table)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["item_no"], "1")
        self.assertEqual(result[1]["qty"], 4)

    def test_part_number_column_is_extracted_when_present(self):
        # Real parts-list tables commonly have a PART NUMBER column
        # between ITEM and DESCRIPTION -- procurement pricing is keyed by
        # part number, so this needs to come through, not be dropped.
        table = [
            ["ITEM", "PART NUMBER", "DESCRIPTION", "MATERIAL", "QTY"],
            ["1", "HB-M8-001", "Hexagon Head Bolt M8 x 25", "Carbon Steel", "4"],
        ]
        result = _table_rows_to_bom_dicts(table)
        self.assertEqual(result[0]["part_number"], "HB-M8-001")
        self.assertEqual(result[0]["item_no"], "1")

    def test_part_number_defaults_to_none_when_no_such_column(self):
        table = [
            ["ITEM NO.", "DESCRIPTION", "QTY", "MATERIAL"],
            ["1", "Base Plate", "1", "Aluminum 6061"],
        ]
        result = _table_rows_to_bom_dicts(table)
        self.assertIsNone(result[0]["part_number"])

    def test_single_row_table_is_skipped(self):
        self.assertEqual(_table_rows_to_bom_dicts([["ITEM", "DESC", "QTY", "MATERIAL"]]), [])

    def test_empty_table(self):
        self.assertEqual(_table_rows_to_bom_dicts([]), [])

    def test_unrecognized_table_is_skipped(self):
        table = [["Revision History"], ["Rev A - initial release"]]
        self.assertEqual(_table_rows_to_bom_dicts(table), [])


def _word(text, left, top, width=20, height=15):
    return {"text": text, "left": left, "top": top, "width": width, "height": height}


class TestWordsToTextRows(unittest.TestCase):
    def test_clusters_by_row_and_orders_by_column(self):
        words = [
            _word("1", left=100, top=10),
            _word("Bracket", left=10, top=12),
            _word("Bolt", left=10, top=52),
            _word("2", left=100, top=50),
        ]
        rows = _words_to_text_rows(words)
        self.assertEqual(len(rows), 2)
        self.assertEqual([w["text"] for w in rows[0]], ["Bracket", "1"])
        self.assertEqual([w["text"] for w in rows[1]], ["Bolt", "2"])

    def test_empty_input(self):
        self.assertEqual(_words_to_text_rows([]), [])


class TestInferGapThreshold(unittest.TestCase):
    def test_falls_back_to_default_with_too_few_gaps(self):
        rows = [[_word("A", left=0, top=0), _word("B", left=100, top=0)]]
        self.assertEqual(_infer_gap_threshold(rows), float(_DEFAULT_GAP_THRESHOLD_PX))

    def test_calibrates_a_low_threshold_from_a_tight_small_font_table(self):
        # Reproduces the real failure this fix addresses: at small
        # font/low resolution, real column gaps (7-23px) are far smaller
        # than the old fixed 25px default, but still clearly separated
        # from genuine intra-cell word gaps (~4px).
        header = [_word("ITEMNO.", 21, 0, width=40), _word("DESCRIPTION", 70, 0, width=63)]
        row1 = [
            _word("1", 21, 40, width=3),
            _word("Base", 47, 40, width=19),
            _word("Plate", 70, 40, width=21),  # 4px gap from "Base" -- intra-cell
            _word("1", 111, 40, width=3),  # 20px gap from "Plate" -- column boundary
        ]
        threshold = _infer_gap_threshold([header, row1])
        self.assertGreater(threshold, 4)
        self.assertLess(threshold, 20)

    def test_uniform_gaps_fall_back_to_default(self):
        # No genuine cluster break (every gap is ~the same size) -- should
        # not invent a boundary that isn't there.
        row = [_word(str(i), left=i * 50, top=0, width=10) for i in range(5)]
        threshold = _infer_gap_threshold([row])
        self.assertEqual(threshold, float(_DEFAULT_GAP_THRESHOLD_PX))


class TestSplitRowIntoCells(unittest.TestCase):
    def test_wide_gaps_become_columns(self):
        row = [
            _word("1", left=0, top=0, width=15),
            _word("Bolt", left=100, top=0, width=40),
            _word("M8", left=145, top=0, width=25),  # small gap -> same cell as "Bolt"
            _word("4", left=250, top=0, width=15),
        ]
        cells = _split_row_into_cells(row, gap_threshold_px=25)
        self.assertEqual(cells, ["1", "Bolt M8", "4"])

    def test_empty_row(self):
        self.assertEqual(_split_row_into_cells([]), [])


if __name__ == "__main__":
    unittest.main()
