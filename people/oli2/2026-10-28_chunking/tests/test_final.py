"""Final token budgets, retrieval handoff and regressions from the boundary audit."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmark import supports
from chunker import validate_chunks
from retrieval import Retriever, build_context, load_chunks
from run import DEFAULT_DOCS, METADATA, SOURCES, load_document, portable_hash, write_json, write_jsonl
from structure import chunk_document, count_tokens
from test_chunking import document


class FinalBoundaryTests(unittest.TestCase):
    def chunks(self, doc, budget=512):
        pages, sections, decisions = chunk_document(doc, budget)
        validate_chunks(doc, pages)
        validate_chunks(doc, sections)
        return pages, sections, decisions

    def test_parent_heading_and_balance_sheet_date_stay_with_body(self):
        doc = document('# Financial statements\n\n## Balance sheet\n\nAt 31 December 2025\n\n'
                       '<table><tr><td>Net assets</td><td>123</td></tr></table>\n')
        _, chunks, _ = self.chunks(doc)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0]['section_path'], ['Financial statements', 'Balance sheet'])
        self.assertNotIn('scaffolding_only', chunks[0]['flags'])

    def test_continued_page_heading_is_kept_with_its_own_body(self):
        doc = document('## 1. Accounting policies\n\nFirst policy and explanation.\n',
                       '### Accounting policies (continued)\n\nSecond policy and explanation.\n')
        _, chunks, _ = self.chunks(doc)
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(c['section_path'] == ['1. Accounting policies'] for c in chunks))
        self.assertTrue(chunks[1]['content'].startswith('### Accounting policies (continued)'))
        self.assertEqual({s['page'] for s in chunks[0]['source_spans']}, {1})

    def test_company_and_period_normalization_preserves_original(self):
        pages = [f'### EXAMPLE LIMITED\n\n## Topic {i}\n\nPolicy and explanation.\n' for i in range(3)]
        pages.append('### EXAMPLE LIMITED BALANCE SHEET AS AT 31 DECEMBER 2025\n\nNet assets GBP 123.\n')
        doc = document(*pages)
        _, chunks, decisions = self.chunks(doc)
        self.assertEqual(chunks[-1]['section_path'], ['BALANCE SHEET'])
        self.assertIn('EXAMPLE LIMITED BALANCE SHEET AS AT', chunks[-1]['content'])
        self.assertEqual(sum(d['decision'] == 'repeated_entity_heading' for d in decisions), 3)

    def test_balance_sheet_analysis_remains_a_subsection(self):
        doc = document('# Financial statements\n\n## Balance sheet\n\nNet assets GBP 123.\n\n'
                       '### Balance sheet analysis\n\nWorking capital explanation.\n')
        _, chunks, _ = self.chunks(doc)
        self.assertEqual(chunks[-1]['section_path'], ['Financial statements', 'Balance sheet', 'Balance sheet analysis'])

    def test_long_unicode_prose_is_lossless_and_token_bounded(self):
        text = '# Results\n\n' + 'Revenue £12, café sales 🙂 increased in 2025. ' * 300 + '\n'
        doc = document(text)
        _, chunks, _ = self.chunks(doc)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(c['context_tokens'] <= 512 for c in chunks))
        self.assertEqual(''.join(c['content'] for c in chunks), text)
        self.assertTrue(all(c['context_tokens'] == count_tokens(c['context_text']) for c in chunks))

    def test_plain_notes_title_and_numbered_siblings_recover_hierarchy(self):
        doc = document('# Financial statements\n\n## Balance sheet\n\nNet assets GBP 123.\n',
                       'NOTES TO THE FINANCIAL STATEMENTS FOR THE YEAR ENDED 31 MARCH 2025\n\n'
                       '2. Accounting policies\n\n### 2.1 Revenue\n\nRevenue policy explanation.\n\n'
                       '## Rendering of services\n\nService revenue explanation.\n\n'
                       '#### 2.2 Debtors\n\nDebtor accounting explanation.\n',
                       '## Notes to the financial statements\n\n## 2. Accounting policies (continued)\n\n'
                       '### 2.2 Debtors (continued)\n\nFurther debtor explanation.\n')
        _, chunks, decisions = self.chunks(doc)
        notes = [c for c in chunks if any(s['page'] == 2 for s in c['source_spans'])]
        self.assertTrue(all('Balance sheet' not in c['section_path'] for c in notes))
        revenue = next(c for c in notes if 'Revenue policy' in c['content'])
        debtors = next(c for c in notes if 'Debtor accounting' in c['content'])
        self.assertEqual(revenue['section_path'][-2:], ['2. Accounting policies', '2.1 Revenue'])
        self.assertEqual(debtors['section_path'][-2:], ['2. Accounting policies', '2.2 Debtors'])
        self.assertEqual(sum(d['recovered_from_plain_text'] for d in decisions), 2)

    def test_long_list_splits_without_losing_items(self):
        text = '# Policies\n\n' + ''.join(f'- Policy {i}: retain the original wording and values.\n' for i in range(200))
        _, chunks, _ = self.chunks(document(text))
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(c['context_tokens'] <= 512 for c in chunks))
        self.assertEqual(''.join(c['content'] for c in chunks), text)

    def test_oversized_table_remains_whole_and_flagged(self):
        table = '<table><tr><th>Year</th><th>GBP million</th></tr>' + '<tr><td>2025</td><td>(123)</td></tr>' * 100 + '</table>\n'
        _, chunks, _ = self.chunks(document('# Results\n\n' + table))
        found = [c for c in chunks if table in c['content']]
        self.assertEqual(len(found), 1)
        self.assertIn('atomic_table_exception', found[0]['flags'])
        self.assertIn('over_token_budget', found[0]['flags'])
        self.assertGreater(found[0]['context_tokens'], 512)

    def test_table_notes_are_separate_traceable_context(self):
        doc = document('# Results\n\n<table><tr><td>Profit</td><td>12</td></tr></table>\n\n'
                       '## Notes on reconciling items\n\nOnly licensed activities are included.\n')
        _, chunks, _ = self.chunks(doc)
        self.assertIn('Only licensed activities', chunks[0]['context_text'])
        self.assertNotIn('Only licensed activities', chunks[0]['content'])
        self.assertTrue(chunks[0]['context_spans'])
        self.assertLessEqual(chunks[0]['context_tokens'], 512)

    def test_empty_and_low_information_pages_remain_auditable(self):
        doc = document('', 'jrua\n\n', '# Policy\n\nThe accounting policy uses historical cost.\n')
        pages, chunks, _ = self.chunks(doc)
        self.assertEqual(len(pages), 3)
        self.assertFalse(pages[0]['indexable'])
        cover = next(c for c in chunks if 'jrua' in c['content'])
        self.assertFalse(cover['indexable'])
        self.assertIn('low_information_preserved', cover['flags'])

    def test_ids_reproduce_and_configuration_changes_them(self):
        doc = document('# Results\n\nA stable statement about financial performance.\n')
        first = self.chunks(doc)[1]
        self.assertEqual(first, self.chunks(doc)[1])
        self.assertNotEqual(first[0]['chunk_id'], self.chunks(doc, 1024)[1][0]['chunk_id'])

    def test_all_six_sources_are_lossless_with_explicit_token_exceptions(self):
        for name in DEFAULT_DOCS:
            with self.subTest(name=name):
                doc = load_document(SOURCES / name / 'pymupdf4llm', METADATA)
                pages, chunks, _ = self.chunks(doc, 1024)
                self.assertTrue(validate_chunks(doc, chunks)['exact_character_coverage'])
                self.assertTrue(all(c['context_tokens'] <= 1024 or 'atomic_table_exception' in c['flags'] for c in chunks))
                self.assertTrue(all(c['context_tokens'] == count_tokens(c['context_text']) for c in chunks))


class FinalRetrievalTests(unittest.TestCase):
    def setUp(self):
        doc = document('# Accounting policies\n\nHistorical cost is the basis of preparation.\n\n'
                       '# Performance\n\nSales increased during the reporting period.\n')
        self.chunks = chunk_document(doc, 512)[1]

    def test_known_evidence_is_retrieved_and_cited_within_total_budget(self):
        ranked = Retriever(self.chunks).search('What is the accounting basis?', 'synthetic', 3)
        result = build_context('What is the accounting basis?', ranked, 512)
        self.assertEqual(result['status'], 'evidence_found')
        self.assertEqual(result['prompt_tokens'], count_tokens(result['prompt']))
        self.assertLessEqual(result['prompt_tokens'], 512)
        self.assertIn('[S1]', result['prompt'])
        self.assertIn('Historical cost', result['selected'][0]['chunk']['content'])

    def test_budget_never_truncates_a_table(self):
        table = '<table>' + '<tr><td>Revenue</td><td>12</td></tr>' * 100 + '</table>'
        chunk = chunk_document(document('# Revenue\n\n' + table), 512)[1][0]
        result = build_context('What is revenue?', [(10.0, chunk)], 256)
        self.assertEqual(result['selected'], [])
        self.assertEqual(result['status'], 'no_evidence_within_budget')
        self.assertEqual(len(result['skipped']), 1)
        self.assertNotIn('<table>', result['prompt'])

    def test_no_match_unknown_document_and_invalid_request(self):
        retriever = Retriever(self.chunks)
        self.assertEqual(retriever.search('unmatchedzz vocabularyzz'), [])
        with self.assertRaisesRegex(ValueError, 'Unknown document'):
            retriever.search('accounting', 'other')
        with self.assertRaises(ValueError):
            build_context('question', [], 1)
        with self.assertRaises(ValueError):
            build_context('', [], 512)
        with self.assertRaises(ValueError):
            build_context('question', [], 512, 0)

    def test_duplicate_ids_and_low_information_are_not_silent(self):
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            Retriever(self.chunks + self.chunks)
        excluded = copy.deepcopy(self.chunks)
        for c in excluded:
            c['indexable'] = False
        self.assertEqual(Retriever(excluded).search('accounting'), [])

    def test_index_hash_rejects_changed_content(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            path = folder / 'section_chunks.jsonl'
            write_jsonl(path, self.chunks)
            write_json(folder / 'index.json', dict(tokenizer='cl100k_base', chunk_files=dict(
                section=dict(path=path.name, sha256_utf8_lf=portable_hash(path)))))
            self.assertEqual(load_chunks(folder), self.chunks)
            path.write_text(path.read_text(encoding='utf8').replace('Historical cost', 'Invented basis'), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'hash'):
                load_chunks(folder)

    def test_evidence_requires_document_page_and_unbroken_span_coverage(self):
        evidence = [dict(document_id='right', page=1, start=0, end=20)]
        spans = [dict(page=1, start=0, end=10), dict(page=1, start=10, end=20)]
        chunk = dict(document_id='wrong', source_spans=spans, context_spans=[])
        self.assertFalse(supports([chunk], evidence))
        chunk['document_id'] = 'right'
        self.assertTrue(supports([chunk], evidence))
        chunk['source_spans'][1]['start'] = 11
        self.assertFalse(supports([chunk], evidence))


if __name__ == '__main__':
    unittest.main()
