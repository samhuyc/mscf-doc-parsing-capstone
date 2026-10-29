"""Adversarial source-integrity and boundary checks; not semantic benchmark labels."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from chunker import blocks_for_page, chunk_document, digest, safe_render, validate_chunks
from run import load_document, METADATA, SOURCES
from review import build_review
from evaluate import rank, supports


def document(*texts):
    return dict(document_id='synthetic', parser='pymupdf4llm', source_sha256='a' * 64,
                pages_sha256=digest(texts), pages=[dict(page=i + 1, markdown=s) for i, s in enumerate(texts)])


class ChunkingTests(unittest.TestCase):
    def chunks(self, doc, budget=4000):
        page, section, decisions = chunk_document(doc, budget)
        validate_chunks(doc, page)
        validate_chunks(doc, section)
        return page, section, decisions

    def test_unicode_blank_lines_and_cross_page_offsets_are_lossless(self):
        doc = document('\n# Financial performance\n\nProfit £1,000; café revenue 🙂\n\n', 'Continued discussion.\n\n## Risks\n\nForeign exchange risk.\n')
        _, chunks, _ = self.chunks(doc)
        self.assertEqual(len(chunks), 3)  # leading whitespace, first section, second section
        self.assertEqual({s['page'] for s in chunks[1]['source_spans']}, {1, 2})

    def test_table_with_blank_lines_and_nested_table_is_atomic(self):
        table = '<table>\n<tr><th>2025</th><th>£m</th></tr>\n\n<tr><td><table><tr><td>-12</td></tr></table></td></tr>\n</table>\n'
        doc = document('# Financials\n\n' + table + '\nNotes apply.\n')
        _, chunks, _ = self.chunks(doc, 100)
        self.assertEqual(sum(table in c['content'] for c in chunks), 1)
        self.assertTrue(any('oversized_atomic_block' in c['flags'] for c in chunks))

    def test_fenced_table_and_heading_are_code(self):
        doc = document('# Real\n\n```html\n<table>\n# Fake\n```\n\nBody\n')
        _, _, decisions = self.chunks(doc)
        self.assertEqual([d['title'] for d in decisions], ['Real'])

    def test_setext_and_multiple_sections_on_same_page(self):
        doc = document('Title\n=====\n\nBody\n\n## Next\n\nMore\n')
        _, chunks, _ = self.chunks(doc)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(chunks[1]['section_path'], ['Title', 'Next'])

    def test_continued_title_is_same_section(self):
        doc = document('## Strategic report\n\nFirst\n', '### Strategic report (continued)\n\nSecond\n')
        _, chunks, _ = self.chunks(doc)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]['section_path'], ['Strategic report'])

    def test_repeated_entity_period_and_numeric_display_do_not_cut(self):
        doc = document(*[f'### EXAMPLE LIMITED\n\n## Topic {i}\n\n### FOR THE YEAR ENDED 31 DECEMBER 2025\n\n### $6.5B\n\nText\n' for i in range(3)])
        _, chunks, decisions = self.chunks(doc)
        self.assertEqual(len(chunks), 3)
        self.assertTrue(all(c['section_path'] == [f'Topic {i}'] for i, c in enumerate(chunks)))
        self.assertEqual(sum(d['decision'] == 'repeated_entity_heading' for d in decisions), 3)
        self.assertTrue(chunks[1]['content'].startswith('### EXAMPLE LIMITED'))

    def test_table_neighbors_are_explicit_context(self):
        table = '<table><tr><th>Year</th><th>GBP million</th></tr>' + '<tr><td>2025</td><td>12</td></tr>' * 5 + '</table>\n'
        doc = document('# Results\n\nAll amounts in GBP million.\n\n' + table + '\nNote: exceptional items excluded.\n')
        _, chunks, _ = self.chunks(doc, 100)
        chunk = next(c for c in chunks if '<table>' in c['content'])
        self.assertTrue(chunk['context_spans'])
        self.assertIn('exceptional items excluded', chunk['retrieval_text'])

    def test_unclosed_tables_fail_visibly(self):
        with self.assertRaisesRegex(ValueError, 'Unclosed'):
            self.chunks(document('# Results\n\n<table><tr><td>123</td></tr>'))

    def test_table_links_to_separate_notes_section(self):
        doc = document('# Results\n\n<table><tr><td>12</td></tr></table>\n\n## Notes on reconciling items\n\nOnly licensed activities are included.\n')
        _, chunks, _ = self.chunks(doc)
        self.assertEqual(len(chunks), 2)
        self.assertIn('Only licensed activities', chunks[0]['retrieval_text'])
        self.assertNotIn('Only licensed activities', chunks[0]['content'])
        self.assertEqual(len(chunks[0]['context_spans']), 2)

    def test_blank_page_kept_in_page_baseline(self):
        page, _, _ = self.chunks(document('', '# Body\n\ntext\n'))
        self.assertEqual(len(page), 2)
        self.assertEqual(page[0]['source_spans'][0]['page'], 1)

    def test_validator_rejects_lost_duplicate_or_changed_content(self):
        doc = document('# First\n\nText\n\n# Second\n\nMore\n')
        _, chunks, _ = self.chunks(doc)
        for bad in [chunks[1:], chunks + chunks[:1]]:
            with self.assertRaises(ValueError):
                validate_chunks(doc, bad)
        bad = copy.deepcopy(chunks)
        bad[0]['content'] += 'Invented number: 100'
        with self.assertRaisesRegex(ValueError, 'differs'):
            validate_chunks(doc, bad)

    def test_ids_reproducible_and_change_with_settings_or_source(self):
        doc = document('# Results\n\n' + 'text ' * 50)
        first = self.chunks(doc)[1]
        self.assertEqual(first, self.chunks(doc)[1])
        self.assertNotEqual(first[0]['chunk_id'], self.chunks(doc, 200)[1][0]['chunk_id'])
        changed = copy.deepcopy(doc)
        changed['pages_sha256'] = 'b' * 64
        self.assertNotEqual(first[0]['chunk_id'], self.chunks(changed)[1][0]['chunk_id'])

    def test_preview_strips_scripts_urls_and_event_handlers(self):
        value = safe_render('<script>alert(1)</script>\n\n<img src="https://x" onerror="alert(2)"><table onclick="x"><tr><td rowspan="2">123</td></tr></table>')
        self.assertNotIn('alert', value)
        self.assertNotIn('https:', value)
        self.assertNotIn('onclick', value)
        self.assertIn('rowspan="2"', value)

    def test_preview_json_cannot_close_script_element(self):
        doc = document('Text </script><script>alert(3)</script>\n')
        doc['document_metadata'] = {}
        page, chunks, _ = self.chunks(doc)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'preview.html'
            build_review(output, [doc], page, chunks, {}, {})
            html = output.read_text(encoding='utf8')
            self.assertEqual(html.count('</script>'), 2)
            self.assertNotIn('</script><script>alert(3)', html)


class InputContractTests(unittest.TestCase):
    def test_actual_six_export_integrity(self):
        from run import DEFAULT_DOCS
        for name in DEFAULT_DOCS:
            with self.subTest(name=name):
                doc = load_document(SOURCES / name / 'pymupdf4llm', METADATA)
                page, section, _ = chunk_document(doc)
                self.assertTrue(validate_chunks(doc, page)['exact_character_coverage'])
                self.assertTrue(validate_chunks(doc, section)['exact_character_coverage'])

    def test_missing_page_and_stale_metadata_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            for name in ('pages.json', 'metadata.json', 'run.json'):
                shutil.copyfile(SOURCES / 'edf_2024/pymupdf4llm' / name, folder / name)
            p = folder / 'pages.json'
            value = json.loads(p.read_text(encoding='utf8'))
            value['pages'][0]['markdown'] += '\nChanged content\n'
            p.write_text(json.dumps(value), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'different source pages'):
                load_document(folder, METADATA)
            value['pages'].pop(0)
            p.write_text(json.dumps(value), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'Missing'):
                load_document(folder)


class RetrievalTests(unittest.TestCase):
    def test_identical_words_on_wrong_page_do_not_pass_evidence(self):
        doc = document('Revenue 12\n', 'Revenue 12\n')
        chunks = chunk_document(doc)[0]
        self.assertFalse(supports(chunks[:1], [dict(page=2, start=0, end=10)]))
        self.assertTrue(supports(chunks[1:], [dict(page=2, start=0, end=10)]))

    def test_bm25_retrieves_relevant_text_without_labels(self):
        chunks = [dict(chunk_id='a', retrieval_text='Hedging policy energy risk'),
                  dict(chunk_id='b', retrieval_text='Total revenue increased')]
        self.assertEqual(rank(chunks, 'What is the hedging policy?')[0][1]['chunk_id'], 'a')
        self.assertEqual(rank(chunks, 'unmatched vocabulary'), [])


if __name__ == '__main__':
    unittest.main()
