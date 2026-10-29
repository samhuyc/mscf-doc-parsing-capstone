"""Adversarial checks for wrong signs, ambiguous headers, missing and duplicate rows."""
import unittest

from extract_rules import MISSING, convert, extract
from evaluate import official_extractbench
from longextract_bench.grading import grade


SCHEMA = {'type': 'object', 'properties': {'rows': {'type': 'array', 'items': {
    'type': 'object', 'properties': {'name': {'type': 'string'}, 'amount': {'type': 'number'}}}}}}


class PilotTests(unittest.TestCase):
    def test_sign_and_blank(self):
        self.assertEqual(convert('($1,234.50)', {'type': 'number'}), -1234.5)
        self.assertIs(convert('—', {'type': 'number'}), MISSING)
        self.assertIs(convert('3.5', {'type': 'integer'}), MISSING)

    def test_missing_and_duplicate_rows_not_repaired(self):
        markdown = '<table><tr><th>Name</th><th>Amount</th></tr><tr><td>A</td><td>(4)</td></tr><tr><td>A</td><td>(4)</td></tr></table>'
        prediction, _ = extract(markdown, SCHEMA)
        self.assertEqual(prediction['rows'], [{'name': 'A', 'amount': -4.0}] * 2)
        truth = {'rows': [{'name': 'A', 'amount': -4}, {'name': 'B', 'amount': 8}]}
        scored = grade(prediction, truth, SCHEMA)
        self.assertLess(scored['precision'], 1)
        self.assertLess(scored['recall'], 1)

    def test_ambiguous_columns_abstain(self):
        prediction, _ = extract('<table><tr><th>Name</th><th>Amount</th><th>Amount</th></tr><tr><td>A</td><td>1</td><td>2</td></tr></table>', SCHEMA)
        self.assertEqual(prediction, {})

    def test_no_unsupported_fields_or_defaults(self):
        schema = {'type': 'object', 'properties': {'paid': {'type': 'boolean', 'default': False}}}
        prediction, _ = extract('Nothing relevant here.', schema)
        self.assertEqual(prediction, {})

    def test_conflicting_scalar_abstains(self):
        schema = {'type': 'object', 'properties': {'invoice_number': {'type': 'string'}}}
        prediction, _ = extract('Invoice Number: A\nInvoice Number: B', schema)
        self.assertEqual(prediction, {})

    def test_official_extractbench_positive_and_negative_controls(self):
        schema = {'type': 'object', 'properties': {'amount': {'type': 'number'}}}
        reference = {'expected_output': {'amount': -5}, 'field_rules': {}}
        correct = official_extractbench(reference, {'amount': -5}, schema)
        wrong = official_extractbench(reference, {'amount': 5}, schema)
        empty = official_extractbench(reference, {}, schema)
        self.assertGreater(correct['extract_unified_value_f1'], wrong['extract_unified_value_f1'])
        self.assertEqual(empty['extract_unified_value_f1'], 0)


if __name__ == '__main__':
    unittest.main()
