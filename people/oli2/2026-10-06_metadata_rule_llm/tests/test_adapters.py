from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from helpers import fixture
from adapters import load_export, load_inputs, make_document, locate_evidence
from config import PARSERS
from llm_extractor import messages
from rule_extractor import extract


class AdapterTests(unittest.TestCase):
    def test_all_18_real_contracts(self):
        loaded = load_inputs()
        self.assertEqual(len(loaded), 18)
        for parser in PARSERS:
            self.assertEqual(sum(len(d.pages) for d, _ in loaded if d.parser == parser), 140)

    def test_three_native_formats_same_semantics(self):
        with tempfile.TemporaryDirectory() as t:
            docs = [load_export(fixture(Path(t) / p, parser=p))[0] for p in PARSERS]
            self.assertTrue(all(d.semantic_payload() == docs[0].semantic_payload() for d in docs))
            self.assertTrue(all(extract(d) == extract(docs[0]) for d in docs))
            self.assertTrue(all(messages(d) == messages(docs[0]) for d in docs))

    def test_filename_id_and_manifest_poisoning(self):
        with tempfile.TemporaryDirectory() as t:
            first = load_export(fixture(Path(t) / 'ordinary'))[0]
            poisoned = load_export(fixture(Path(t) / 'FakeBank-2099-Q4-release.pdf',
                                          identity='FakeBank-Q4-2099', title='FakeBank Results Press Release Q4 2099'))[0]
            self.assertEqual(extract(first), extract(poisoned))
            self.assertEqual(messages(first), messages(poisoned))
            payload = json.dumps(poisoned.semantic_payload())
            self.assertNotIn('FakeBank', payload)
            self.assertNotIn('2099', payload)

    def test_image_link_and_attribute_paths_are_not_semantics(self):
        text = '![](Q4-2099-results-press-release.png)\n[click](Q4-2099.pdf)\n<img src="Q4-2099.pdf">'
        doc = make_document([text])
        self.assertNotIn('2099', json.dumps(doc.semantic_payload()))
        self.assertTrue(all(d['value'] is None for d in extract(doc)[0].values()))
        self.assertEqual(len(doc.pages[0].markdown), len(text))

    def test_missing_page_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            folder = fixture(Path(t), texts=['one', 'two'])
            path = folder / 'pages.json'
            data = json.loads(path.read_text())
            data['pages'].pop()
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'Page count'):
                load_export(folder)

    def test_invalid_page_sequence_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            folder = fixture(Path(t))
            path = folder / 'pages.json'
            data = json.loads(path.read_text())
            data['pages'][0]['page'] = 2
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'physical page'):
                load_export(folder)

    def test_source_hash_and_document_tampering(self):
        with tempfile.TemporaryDirectory() as t:
            folder = fixture(Path(t))
            (folder / 'document.md').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'mismatch'):
                load_export(folder)

    def test_crlf_equivalent(self):
        with tempfile.TemporaryDirectory() as t:
            folder = fixture(Path(t))
            before = load_export(folder)[0]
            for file in folder.iterdir():
                file.write_bytes(file.read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n'))
            self.assertEqual(before, load_export(folder)[0])

    def test_original_evidence_and_pointer_verified(self):
        doc = make_document(['# Entity Limited'])
        item = locate_evidence(doc, dict(source='page', page=1, quote='Entity Limited'))
        self.assertEqual(item['start'], 2)
        self.assertEqual(item['original_quote'], 'Entity Limited')
        item['original_quote'] = 'tampered'
        with self.assertRaises(ValueError):
            locate_evidence(doc, item)

    def test_embedded_title_allowed_separately(self):
        doc = make_document(['blank'], title='Example Results Presentation')
        d = extract(doc)[0]['document_type']
        self.assertEqual(d['value'], 'results_presentation')
        self.assertIsNone(d['evidence'][0]['page'])
