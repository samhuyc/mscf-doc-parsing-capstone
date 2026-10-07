"""Read-only integration checks against the saved experiment, with network denied."""
import json
import unittest
from unittest.mock import patch

from helpers import make_document
from adapters import load_inputs
from config import ROOT
from hybrid import resolve
from llm_extractor import extract as llm_extract
from providers import OpenAIProvider
from rule_extractor import extract as rule_extract
from run import read_records, run
from schema import CANONICAL_SCHEMA, LLM_SCHEMA


class ReplayTests(unittest.TestCase):
    def test_schema_files_match_runtime_contract(self):
        for name, expected in [('metadata.schema.json', CANONICAL_SCHEMA), ('llm.schema.json', LLM_SCHEMA)]:
            self.assertEqual(json.loads((ROOT / name).read_text(encoding='utf8')), expected)

    def test_runner_preserves_existing_outputs_and_old_experiment(self):
        with self.assertRaises(ValueError):
            run(output=ROOT.parent / '2026-09-29_metadata_extraction/results')
        if (ROOT / 'results/predictions/pymupdf4llm/rule.jsonl').exists():
            with self.assertRaises(FileExistsError):
                run(parsers=['pymupdf4llm'])

    def test_all_54_predictions_replay_without_model_calls(self):
        if not (ROOT / 'results/predictions/mineru_vlm/hybrid.jsonl').exists():
            self.skipTest('Saved full experiment not present')
        indexed = {}
        for path in (ROOT / 'results/predictions').glob('*/*.jsonl'):
            for row in read_records(path):
                indexed[(row['parser'], row['source_sha256'], row['method'])] = row
        compared = 0
        with patch.object(OpenAIProvider, 'generate', side_effect=AssertionError('Network forbidden')):
            for doc, _ in load_inputs():
                r, _ = rule_extract(doc)
                l, _, resources = llm_extract(doc, OpenAIProvider(), ROOT / 'results/cache', offline=True)
                h, _ = resolve(doc, r, l)
                self.assertEqual(resources['model_calls_this_run'], 0)
                for method, actual in [('rule', r), ('llm', l), ('hybrid', h)]:
                    self.assertEqual(actual, indexed[(doc.parser, doc.source_sha256, method)]['fields'])
                    compared += 1
        self.assertEqual(compared, 54)
