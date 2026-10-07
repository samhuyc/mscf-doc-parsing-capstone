from copy import deepcopy
import json
import unittest

from helpers import make_document, resolved, wire
from hybrid import resolve
from llm_extractor import validate_response
from rule_extractor import extract


class HybridTests(unittest.TestCase):
    def setUp(self):
        self.doc = make_document(['# Example Limited\nQ2 2023\nBrand Alternative'])
        self.rule = extract(self.doc)[0]

    def llm(self, value, quote):
        response = wire()
        response['issuer'] = resolved(value, quote)
        return validate_response(json.dumps(response), self.doc)[0]

    def test_disagreement_retains_rule(self):
        fields, audit = resolve(self.doc, self.rule, self.llm('Brand Alternative', 'Brand Alternative'))
        self.assertEqual(fields['issuer']['value'], 'Example Limited')
        self.assertTrue(audit['issuer']['disagreement'])

    def test_fallback_on_rule_abstention(self):
        self.rule['issuer'].update(value=None, status='not_found', evidence=[])
        fields, audit = resolve(self.doc, self.rule, self.llm('Brand Alternative', 'Brand Alternative'))
        self.assertEqual(fields['issuer']['value'], 'Brand Alternative')
        self.assertEqual(audit['issuer']['reason'], 'validated_llm_fallback')

    def test_invalid_evidence_never_fills_gap(self):
        self.rule['issuer'].update(value=None, status='not_found', evidence=[])
        fields, audit = resolve(self.doc, self.rule, self.llm('FakeBank', 'No such text'))
        self.assertIsNone(fields['issuer']['value'])
        self.assertTrue(audit['issuer']['llm_evidence_rejected'])

    def test_hybrid_revalidates_supplied_evidence(self):
        llm = self.llm('Brand Alternative', 'Brand Alternative')
        llm['issuer']['evidence'][0]['page'] = 99
        _, audit = resolve(self.doc, self.rule, llm)
        self.assertTrue(audit['issuer']['llm_evidence_rejected'])
