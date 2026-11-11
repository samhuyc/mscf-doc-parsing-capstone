from contextlib import redirect_stdout
import io
import unittest
from unittest.mock import patch

import demo


class ToolCallingTests(unittest.TestCase):
    def test_calculate_subtracts_decimals(self):
        self.assertEqual(demo.calculate("98.9", "91.2", "subtract"), "7.7")
        self.assertEqual(demo.calculate("0.3", "0.2", "subtract"), "0.1")

    def test_invalid_tool_parameters(self):
        with self.assertRaises(ValueError):
            demo.search_report(" ")
        for a, b, operation in [
            ("98.9", "91.2", "multiply"),
            (98.9, "91.2", "subtract"),
            ("not a number", "91.2", "subtract"),
            ("NaN", "91.2", "subtract"),
        ]:
            with self.subTest(a=a, b=b, operation=operation), self.assertRaises(ValueError):
                demo.calculate(a, b, operation)

    def test_real_retrieval_and_cited_answer(self):
        trace = io.StringIO()
        with redirect_stdout(trace):
            self.assertEqual(demo.main(), 0)

        output = trace.getvalue()
        self.assertLess(output.index("Tool Call search_report"), output.index("Tool Call calculate"))
        self.assertIn(f'"question": "{demo.SEARCH_QUESTION}"', output)
        self.assertIn('"a": "98.9", "b": "91.2", "operation": "subtract"', output)
        self.assertIn('返回 "7.7"', output)
        self.assertIn("同比变动约 +7.7 十亿美元", output)
        self.assertIn("[S1] CVS Health 2025 Q2 Earnings Presentation，PDF 第 6 页", output)
        self.assertIn("2Q-2025-Earnings-Presentation.pdf#page=6", output)

    def test_no_retrieval_match(self):
        self.assertIsNone(demo.search_report("zzznomatch"))

    def test_ranked_chunk_without_both_periods_stops_before_calculation(self):
        chunks = demo.load_chunks(demo.INDEX_DIR)
        for chunk in chunks:
            # Keep retrieval_text intact so BM25 still finds the altered evidence.
            chunk["content"] = chunk["content"].replace("<th>2Q 2024</th>", "<th>2Q 2023</th>")

        trace = io.StringIO()
        with patch.object(demo, "load_chunks", return_value=chunks), redirect_stdout(trace):
            self.assertEqual(demo.main(), 1)

        output = trace.getvalue()
        self.assertIn("返回 null", output)
        self.assertIn("证据不足，无法回答", output)
        self.assertNotIn("Tool Call calculate", output)


if __name__ == "__main__":
    unittest.main()
