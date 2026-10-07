from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from excel_parser import extract_workbook
from scripts.evaluate import level_one, level_two


class ExcelExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate_fixtures.py")],
            check=True,
            cwd=ROOT,
        )
        cls.fixture = ROOT / "fixtures" / "edge_cases.xlsx"
        cls.payload = extract_workbook(cls.fixture)
        cls.sheet = cls.payload["workbook"]["sheets"][0]
        cls.cells = {cell["coordinate"]: cell for cell in cls.sheet["cells"]}

    def test_canonical_envelope(self) -> None:
        self.assertEqual(self.payload["schema_version"], "1.0.0")
        self.assertEqual(self.payload["parser"]["library"], "openpyxl")
        self.assertEqual(self.payload["workbook"]["sheet_count"], 2)
        self.assertEqual(len(self.payload["source"]["sha256"]), 64)

    def test_formula_and_cache_policy(self) -> None:
        self.assertEqual(self.cells["B6"]["formula"], "=B4-B5")
        self.assertEqual(self.cells["B6"]["cached_value"], 450)
        self.assertEqual(self.cells["B6"]["cached_value_status"], "present")
        self.assertEqual(self.cells["C6"]["formula"], "=C4-C5")
        self.assertIsNone(self.cells["C6"]["cached_value"])
        self.assertEqual(self.cells["C6"]["cached_value_status"], "missing")

    def test_merged_and_hidden_metadata(self) -> None:
        self.assertEqual(self.cells["A1"]["merged"]["role"], "anchor")
        self.assertEqual(self.cells["B1"]["merged"]["role"], "child")
        self.assertEqual(self.cells["B1"]["merged"]["anchor"], "A1")
        self.assertTrue(self.cells["A5"]["row_hidden"])
        self.assertTrue(self.cells["D4"]["column_hidden"])

    def test_error_cell_and_number_format(self) -> None:
        self.assertEqual(self.cells["D6"]["value_type"], "error")
        self.assertEqual(self.cells["D6"]["value"], "#DIV/0!")
        self.assertEqual(self.cells["B4"]["number_format"], "$#,##0")

    def test_boolean_date_and_hidden_sheet(self) -> None:
        hidden = self.payload["workbook"]["sheets"][1]
        hidden_cells = {cell["coordinate"]: cell for cell in hidden["cells"]}
        self.assertEqual(hidden["state"], "hidden")
        self.assertEqual(hidden_cells["B2"]["value_type"], "boolean")
        self.assertIs(hidden_cells["B2"]["value"], True)
        self.assertEqual(hidden_cells["B3"]["value_type"], "datetime")
        self.assertEqual(hidden_cells["B3"]["value"], "2026-10-06T00:00:00")

    def test_multiple_tables_and_row_roles(self) -> None:
        self.assertEqual(len(self.sheet["tables"]), 2)
        first, second = self.sheet["tables"]
        self.assertEqual(first["title"], "Illustrative Income Statement")
        self.assertEqual(first["row_roles"]["header"], [3])
        self.assertEqual(first["row_roles"]["footnote"], [8])
        self.assertEqual(second["title"], "Key Ratios")
        self.assertEqual(second["row_roles"]["header"], [12])
        self.assertEqual(second["row_roles"]["footnote"], [16])

    def test_level_one_reconstruction(self) -> None:
        result = level_one(self.fixture)
        self.assertGreater(result["checks"], 0)
        self.assertEqual(result["accuracy"], 1.0)
        self.assertEqual(result["mismatches"], [])

    def test_level_two_gold_records(self) -> None:
        result = level_two(ROOT / "fixtures" / "gold_annotations.json")
        self.assertEqual(result["line_item_survival"], 1.0)
        self.assertEqual(result["coordinate_accuracy"], 1.0)
        self.assertEqual(result["value_accuracy"], 1.0)
        self.assertEqual(result["complete_record_accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
