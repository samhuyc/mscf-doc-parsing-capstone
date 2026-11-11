import unittest

from benchmark_pilot import Snapshot, extract_fields, query_from_label


class PilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.adapter = Snapshot("0baababc2652757982ae5898500a1c72409c4848").adapter()

    def test_reference_values_cannot_affect_features(self):
        label = {"rows": [{"label": "Revenue", "values": ["999"]}],
                 "columns": [{"header_path": ["2025"]}]}
        text = "| Item | 2025 |\n|---|---|\n|Revenue|12|\n"
        query = query_from_label(label)
        self.assertNotIn("values", query["rows"][0])
        before = extract_fields(self.adapter, text, query)
        label["rows"][0]["values"] = ["12"]
        self.assertEqual(before, extract_fields(self.adapter, text, query_from_label(label)))
        self.assertEqual(before[0]["text"], "12")

    def test_duplicate_tables_abstain(self):
        label = {"rows": [{"label": "Revenue", "values": ["12"]}],
                 "columns": [{"header_path": ["2025"]}]}
        table = "<table><tr><th>Item</th><th>2025</th></tr><tr><td>Revenue</td><td>12</td></tr></table>"
        field = extract_fields(self.adapter, table + table, query_from_label(label))[0]
        self.assertIsNone(field["value_key"])
        self.assertEqual(field["reason"], "ambiguous_table_match")

    def test_missing_table_kept_as_missing(self):
        label = {"rows": [{"label": "Revenue", "values": ["12"]}],
                 "columns": [{"header_path": ["2025"]}]}
        self.assertIsNone(extract_fields(self.adapter, "Revenue was 12", query_from_label(label))[0]["text"])


if __name__ == "__main__":
    unittest.main()
