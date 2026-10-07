from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.evaluate_benchmark_cases import evaluate_all


class ConvertedBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        result = evaluate_all(ROOT / "benchmark_cases")
        cls.sponsor, cls.tatqa = result["results"]

    def test_sponsor_cells_coordinates_and_merges(self) -> None:
        totals = self.sponsor["totals"]
        self.assertEqual(totals["nonblank_values_correct"], 217)
        self.assertEqual(totals["nonblank_values"], 217)
        self.assertEqual(totals["coordinates_correct"], totals["cells"])
        self.assertEqual(totals["merged_cells_correct"], 14)
        self.assertEqual(totals["merged_cells"], 14)

    def test_sponsor_detection_baseline(self) -> None:
        totals = self.sponsor["totals"]
        self.assertEqual(totals["single_table_detected"], 11)
        self.assertEqual(totals["table_ranges_correct"], 11)
        self.assertEqual(totals["titles_correct"], 11)
        self.assertEqual(totals["header_classifications_correct"], 9)

    def test_tatqa_cells_and_coordinates(self) -> None:
        totals = self.tatqa["totals"]
        self.assertEqual(totals["nonblank_values_correct"], 8773)
        self.assertEqual(totals["nonblank_values"], 8773)
        self.assertEqual(totals["coordinates_correct"], 10411)
        self.assertEqual(totals["cells"], 10411)

    def test_tatqa_detection_baseline(self) -> None:
        totals = self.tatqa["totals"]
        self.assertEqual(totals["single_table_detected"], 254)
        self.assertEqual(totals["table_ranges_correct"], 120)
        self.assertEqual(totals["titles_correct"], 120)
        self.assertEqual(totals["header_classifications_correct"], 120)

    def test_empty_string_normalization_is_explicit(self) -> None:
        sponsor = self.sponsor["totals"]
        tatqa = self.tatqa["totals"]
        self.assertEqual(sponsor["explicit_blank_values"], 13)
        self.assertEqual(sponsor["explicit_blanks_normalized_to_null"], 13)
        self.assertEqual(tatqa["explicit_blank_values"], 1638)
        self.assertEqual(tatqa["explicit_blanks_normalized_to_null"], 1638)


if __name__ == "__main__":
    unittest.main()
