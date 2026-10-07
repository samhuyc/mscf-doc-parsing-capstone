import ast
import builtins
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from helpers import make_document
from config import ROOT
from evaluate import index_records, pilot_reference, ratio, score_references
from rule_extractor import extract
from schema import equivalent


class EvaluationTests(unittest.TestCase):
    def test_taxonomy_normalization(self):
        self.assertTrue(equivalent('document_type', 'annual_accounts', 'annual_financial_statements'))
        self.assertTrue(equivalent('issuer', 'EXAMPLE LIMITED', 'Example Limited'))
        self.assertFalse(equivalent('issuer', 'Example', 'Example Holdings plc'))

    def test_date_label_maps_to_end_not_assumed_kind(self):
        label = dict(document='opaque', source_sha256='a' * 64, field='reporting_period',
                     value='2023-03-31', id='test', review_status='draft')
        self.assertEqual(pilot_reference(label)['field'], 'reporting_period_end')
        label['value'] = '2023-H1'
        self.assertEqual(pilot_reference(label)['value'], dict(year=2023, kind='half', number=1))

    def test_missing_null_prediction_not_correct(self):
        refs = [dict(document_id='missing', field='document_date', value=None, status='not_found', reference_id='x')]
        m = score_references({}, refs, 'pymupdf4llm', 'rule')['metrics']['document_date']
        self.assertEqual(m['exact_match']['rate'], 0)
        self.assertIsNone(m['supported_value_accuracy']['rate'])
        self.assertEqual(m['missing_or_failed_rate']['rate'], 1)

    def test_empty_reviewed_denominator_undefined(self):
        self.assertIsNone(ratio(0, 0)['rate'])
        self.assertIsNone(score_references({}, [], 'pymupdf4llm', 'rule')['metrics']['issuer']['exact_match']['rate'])

    def test_duplicate_predictions_rejected(self):
        row = dict(document_id='x', parser='pymupdf4llm', method='rule')
        with self.assertRaises(ValueError):
            index_records([row, row])

    def test_extraction_modules_have_no_evaluation_dependencies(self):
        for name in ('run.py', 'adapters.py', 'rule_extractor.py', 'llm_extractor.py', 'providers.py',
                     'hybrid.py', 'config.py', 'schema.py', 'baseline_bridge.py', 'evidence_policy.py'):
            source = (ROOT / name).read_text(encoding='utf8')
            imports = [n.module for n in ast.walk(ast.parse(source)) if isinstance(n, ast.ImportFrom)]
            self.assertNotIn('evaluate', imports)
            self.assertNotIn('labels.json', source)
            self.assertNotIn('pilot_reference', source)

    def test_extraction_works_with_all_label_access_denied(self):
        original = builtins.open
        def guarded(file, *args, **kwargs):
            if 'label' in str(file).lower() or 'evaluation' in str(file).lower():
                raise PermissionError('Labels unavailable')
            return original(file, *args, **kwargs)
        with patch('builtins.open', guarded), patch('pathlib.Path.open', side_effect=PermissionError('No file access')):
            fields, _ = extract(make_document(['Q2 2023 Earnings Presentation']))
        self.assertEqual(fields['reporting_period']['value']['year'], 2023)
