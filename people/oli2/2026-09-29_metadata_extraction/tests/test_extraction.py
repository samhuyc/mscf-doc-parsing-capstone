"""Synthetic adversarial cases plus read-only checks of the fixed input contract."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from inputs import ROOT, load_document, read_json, sha256, text_view
from rules import FIELDS, extract_fields, parse_date
from evaluate import evaluate, validate_evidence
from extract import run_experiment


def extract(texts, title=''):
    pages = [text_view(t, 'fixture/pages.json', f'/pages/{i}/markdown', i + 1) for i, t in enumerate(texts)]
    return extract_fields(pages, text_view(title, 'fixture/metadata.json', '/source/metadata/title', None))


def fixture(repo, doc_id='opaque-id', manifest_title='Untrusted supplied title', creation='D:20391201000000'):
    folder = repo / 'fixture'
    folder.mkdir(exist_ok=True)
    markdown = '# Example Limited\nUNAUDITED FINANCIAL STATEMENTS\nFOR THE YEAR ENDED 31 MARCH 2023\n'
    doc = '<!-- source page 1 -->\n\n' + markdown
    source = dict(id=doc_id, title=manifest_title, sha256='a'*64, pages=1,
                  metadata=dict(title='', creationDate=creation, modDate=creation), native_text_chars=[0])
    pages = dict(schema_version=1, source_sha256=source['sha256'], parser='pymupdf4llm',
                 page_numbering='1-based physical PDF pages',
                 pages=[dict(page=1, markdown=markdown, native={}, text_chars=90, confidence=None)])
    metadata = dict(source=source, parser='pymupdf4llm')
    run = dict(parser='pymupdf4llm', document=doc_id, input_sha256=source['sha256'], expected_pages=1,
               parsed_pages=1, nonempty_pages=1, status='success', versions={'fixture':'1'},
               document_sha256=sha256(doc.encode()))
    content = {'pages.json': json.dumps(pages), 'metadata.json': json.dumps(metadata),
               'run.json':json.dumps(run), 'document.md':doc}
    for name, value in content.items():
        (folder / name).write_bytes(value.encode())
    return dict(document_id=doc_id, parser='pymupdf4llm', path='fixture', source_sha256=source['sha256'],
                sha256_utf8_lf={name:sha256(value.encode()) for name,value in content.items()})


class SemanticRulesTests(unittest.TestCase):
    def test_pdf_creation_date_is_not_reporting_date(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            entry = fixture(repo, creation='D:20391201000000')
            pages, title, _ = load_document(entry, repo)
            result = extract_fields(pages, title)
            self.assertEqual(result['reference_date']['value'], '2023-03-31')
            self.assertIsNone(result['document_date']['value'])
            self.assertNotIn('2039', json.dumps(result))

    def test_companies_house_stamp_is_not_reporting_or_document_date(self):
        result = extract(['REPORT AND FINANCIAL STATEMENTS FOR THE YEAR ENDED 30 SEPTEMBER 2022\n16/06/2023 COMPANIES HOUSE'])
        self.assertEqual(result['reference_date']['value'], '2022-09-30')
        self.assertIsNone(result['document_date']['value'])
        stamps = [c for c in result['reference_date']['candidates'] if c['role'] == 'filing_stamp']
        self.assertEqual(stamps[0]['value'], '2023-06-16')
        self.assertEqual(stamps[0]['disposition'], 'excluded')

    def test_quarter_without_exact_end(self):
        result = extract(['Third Quarter 2022 | October 25, 2022\nEarnings Conference Call', 'This presentation includes forecasts.'])
        self.assertEqual(result['document_type']['value'], 'earnings_presentation')
        self.assertEqual(result['reference_period']['value'], dict(year=2022, kind='quarter', number=3))
        self.assertIsNone(result['reference_date']['value'])
        self.assertEqual(result['reference_date']['status'], 'not_found')
        self.assertEqual(result['document_date']['value'], '2022-10-25')

    def test_half_year_without_exact_end_or_fiscal_half(self):
        result = extract(['Half Year Results 2023'], 'Example Half Year Results Presentation')
        self.assertEqual(result['reference_period']['value'], dict(year=2023, kind='half', number=None))
        self.assertIsNone(result['reference_date']['value'])

    def test_explicit_half_label_supports_number(self):
        result = extract(['Half Year Results 2023', 'Underlying results H2 2023 and H2 2022'])
        self.assertEqual(result['reference_period']['value']['number'], 2)
        self.assertIsNone(result['reference_date']['value'])

    def test_two_competing_reporting_dates_abstain(self):
        result = extract(['Report and financial statements\nFor the year ended 30 April 2022\nFor the year ended 31 May 2022'])
        self.assertEqual(result['reference_date']['status'], 'ambiguous')
        self.assertIsNone(result['reference_date']['value'])
        self.assertEqual(len([c for c in result['reference_date']['candidates'] if c['disposition']=='competing']), 2)

    def test_competing_event_dates_abstain(self):
        result = extract(['Results Press Release\n15 August 2021\n16 August 2021'])
        self.assertEqual(result['document_date']['status'], 'ambiguous')

    def test_current_period_excludes_comparative_year(self):
        result = extract(['Results Press Release\nH1 2022\n20 July 2022',
                          'For the half-year ended 30 June 2022',
                          'For the half-year ended 30 June 2021'])
        self.assertEqual(result['reference_date']['value'], '2022-06-30')
        prior = [c for c in result['reference_date']['candidates'] if c['value']=='2021-06-30'][0]
        self.assertEqual(prior['exclusion_reason'], 'different_reporting_period')

    def test_body_forecast_does_not_replace_cover_period(self):
        result = extract(['Q2 2022 Earnings Presentation', 'Q4 2023 guidance and H1 2024 targets'])
        self.assertEqual(result['reference_period']['value'], dict(year=2022, kind='quarter', number=2))

    def test_as_of_date_not_presentation_event(self):
        result = extract(['Results Presentation\nH1 2022\nAs of 20 July 2022'])
        self.assertIsNone(result['document_date']['value'])

    def test_ambiguous_numeric_date(self):
        result = extract(['Report and financial statements for the year ended 03/04/2022'])
        self.assertEqual(result['reference_date']['status'], 'ambiguous')
        self.assertIsNone(result['reference_date']['value'])

    def test_invalid_date_is_not_repaired(self):
        result = extract(['Report and financial statements for the year ended 31 February 2022'])
        self.assertIsNone(result['reference_date']['value'])
        self.assertIn('invalid_date', result['warnings'])

    def test_calendar_validation_and_iso_dates(self):
        self.assertEqual(parse_date('29 February 2024'), ('2024-02-29', None))
        self.assertEqual(parse_date('2023-02-29'), (None, 'invalid_date'))
        self.assertEqual(parse_date('2023-03-31'), ('2023-03-31', None))

    def test_scanned_input_and_blank_embedded_metadata(self):
        with tempfile.TemporaryDirectory() as temp:
            entry = fixture(Path(temp))
            pages, title, provenance = load_document(entry, Path(temp))
            result = extract_fields(pages, title)
            self.assertEqual(provenance['source_kind'], 'scanned')
            self.assertEqual(title.raw, '')
            self.assertEqual(result['document_type']['value'], 'unaudited_financial_statements')

    def test_split_heading_and_exact_evidence(self):
        raw = '# REPORT AND FINANCIAL STATEMENTS\n\n# FOR THE YEAR ENDED\n\n# 31 DECEMBER 2021'
        result = extract([raw])
        self.assertEqual(result['reference_date']['value'], '2021-12-31')
        ids = result['reference_date']['evidence_ids']
        evidence = next(e for e in result['evidence'] if e['id'] in ids)
        self.assertEqual(evidence['quote'], raw[evidence['start']:evidence['end']])
        self.assertEqual(evidence['page'], 1)
        self.assertIn('\n\n#', evidence['quote'])

    def test_image_filename_does_not_supply_predictions(self):
        result = extract(['![](images/Q2-2022-results-press-release-2022-06-30.png)'])
        for key in FIELDS:
            self.assertIsNone(result[key]['value'])

    def test_manifest_title_and_id_cannot_supply_predictions(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            first = fixture(repo)
            p, t, _ = load_document(first, repo)
            before = extract_fields(p,t)
            poisoned = fixture(repo, doc_id='q4-2099-press-release', manifest_title='Results Press Release Q4 2099')
            p, t, _ = load_document(poisoned, repo)
            after = extract_fields(p,t)
            self.assertEqual(before, after)

    def test_unknown_document_abstains(self):
        result = extract(['A lunch menu with no financial metadata'])
        self.assertTrue(all(result[k]['status']=='not_found' for k in FIELDS))

    def test_deterministic_rules(self):
        texts = ['Consolidated Segmental Statement for the year ended 31 December 2021']
        self.assertEqual(extract(texts), extract(texts))


class PeriodAuthorityTests(unittest.TestCase):
    """Added before the 1.1.0 change; no issuer-specific fixtures."""

    @staticmethod
    def comparison(current=2026, prior=2025):
        return (f'<table><tr><th>Measure</th><th><b>H1 {current}</b></th>'
                f'<th><b>H1 {prior}</b></th></tr>'
                '<tr><td>Revenue</td><td>100</td><td>90</td></tr></table>')

    def test_title_outranks_comparative_headers_on_same_page(self):
        for title in ('# 2026 Half Year', '**2026 Half Year**', '<h1>2026 Half Year</h1>'):
            with self.subTest(title=title):
                result = extract([title + '\n\n' + self.comparison()])
                period = result['reference_period']
                self.assertEqual(period['status'], 'resolved')
                self.assertEqual(period['value'], dict(year=2026, kind='half', number=1))
                prior = [c for c in period['candidates'] if c['value']['year'] == 2025]
                self.assertTrue(prior)
                self.assertTrue(all(c['disposition'] == 'lower_priority' for c in prior))

    def test_older_title_wins_even_with_future_year_in_table(self):
        table = self.comparison(2025, 2024).replace('</table>',
            '<tr><td>H1 2029 forecast</td><td>500</td><td>400</td></tr></table>')
        result = extract(['# 2025 Half Year\n\n' + table])
        self.assertEqual(result['reference_period']['value'], dict(year=2025, kind='half', number=1))
        self.assertTrue(any(c['value']['year'] == 2029 for c in result['reference_period']['candidates']))

    def test_comparative_table_without_title_remains_ambiguous(self):
        result = extract([self.comparison()])
        self.assertIsNone(result['reference_period']['value'])
        self.assertEqual(result['reference_period']['status'], 'ambiguous')
        years = {c['value']['year'] for c in result['reference_period']['candidates'] if c['disposition'] == 'competing'}
        self.assertEqual(years, {2025, 2026})

    def test_resolved_title_scope_excludes_prior_reporting_dates(self):
        result = extract(['# 2026 Half Year\n\n' + self.comparison(),
                          'For the half-year ended 30 June 2026',
                          'For the half-year ended 30 June 2025'])
        self.assertEqual(result['reference_date']['status'], 'resolved')
        self.assertEqual(result['reference_date']['value'], '2026-06-30')
        prior = [c for c in result['reference_date']['candidates'] if c['value'] == '2025-06-30']
        self.assertTrue(prior)
        self.assertTrue(all(c['exclusion_reason'] == 'different_reporting_period' for c in prior))

    def test_heading_outranks_narrative_which_outranks_table(self):
        narrative = 'Earlier performance in H1 2024 is discussed below.'
        result = extract(['# 2026 Half Year\n\n' + narrative + '\n\n' + self.comparison()])
        period = result['reference_period']
        self.assertEqual(period['value'], dict(year=2026, kind='half', number=1))
        ranked = {c['rule_id']: c['priority'] for c in period['candidates']}
        self.assertGreater(ranked['cover_heading_period'], ranked['cover_narrative_period'])
        self.assertGreater(ranked['cover_narrative_period'], ranked['cover_table_header_period'])

    def test_conflicting_authoritative_headings_remain_ambiguous(self):
        result = extract(['# 2026 Half Year\n\n# 2025 Half Year\n\n' + self.comparison()])
        self.assertIsNone(result['reference_period']['value'])
        self.assertEqual(result['reference_period']['status'], 'ambiguous')


class ContractTests(unittest.TestCase):
    def test_baseline_archive_and_original_results_unchanged(self):
        archive = ROOT / 'baseline' / '1.0.0'
        integrity = read_json(archive / 'integrity.json')
        for name, digest in integrity['sha256'].items():
            self.assertEqual(sha256((archive / name).read_bytes()), digest, name)
            if name.startswith('results/'):
                self.assertEqual(sha256((ROOT / name).read_bytes()), digest, name)

    def test_extraction_refuses_baseline_overwrite(self):
        with self.assertRaises(FileExistsError):
            run_experiment(output=ROOT / 'results')
        with self.assertRaisesRegex(ValueError, 'read-only'):
            run_experiment(output=ROOT / 'baseline' / '1.0.0' / 'results')

    def test_existing_six_input_contracts(self):
        manifest = read_json(ROOT / 'input_manifest.json')
        self.assertEqual(len(manifest['documents']), 6)
        for entry in manifest['documents']:
            with self.subTest(document=entry['document_id']):
                pages, _, provenance = load_document(entry)
                self.assertEqual(len(pages), provenance['page_count'])

    def test_lf_and_crlf_checkout_are_equivalent(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            entry = fixture(repo)
            pages, title, _ = load_document(entry, repo)
            before = extract_fields(pages,title)
            for path in (repo/'fixture').iterdir():
                path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
            pages, title, provenance = load_document(entry, repo)
            self.assertEqual(before, extract_fields(pages,title))
            self.assertIn('document.md', provenance['line_endings_normalized'])

    def test_tampered_input_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            entry = fixture(repo)
            path = repo/'fixture'/'pages.json'
            path.write_bytes(path.read_bytes().replace(b'2023', b'2024'))
            with self.assertRaisesRegex(ValueError, 'Pinned input hash mismatch'):
                load_document(entry, repo)

    def test_bad_page_sequence_rejected_even_if_manifest_hash_updated(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            entry = fixture(repo)
            path = repo/'fixture'/'pages.json'
            data = read_json(path)
            data['pages'][0]['page'] = 0
            raw = json.dumps(data).encode()
            path.write_bytes(raw)
            entry['sha256_utf8_lf']['pages.json'] = sha256(raw)
            with self.assertRaisesRegex(ValueError, 'physical page sequence'):
                load_document(entry, repo)

    def test_evidence_validator_rejects_wrong_page_and_quote(self):
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            entry = fixture(repo)
            p,t,provenance = load_document(entry,repo)
            row = dict(provenance=provenance, **extract_fields(p,t))
            self.assertEqual(validate_evidence(row, repo)['errors'], [])
            row['evidence'][0]['page'] = 2
            row['evidence'][1]['quote'] = 'invented text'
            self.assertEqual(len(validate_evidence(row, repo)['errors']), 2)

    def test_missing_predictions_stay_in_evaluation_denominator(self):
        labels = dict(annotation_origin='test', review_status='synthetic', documents=[
            dict(document_id='missing', expected={f:dict(value=None,status='not_found') for f in FIELDS})])
        result = evaluate([], labels)
        self.assertEqual(result['metrics']['reference_date']['exact_match']['rate'], 0)
        self.assertEqual(result['missing_documents'], ['missing'])

    def test_extraction_modules_do_not_read_labels_or_import_evaluator(self):
        for name in ('extract.py','inputs.py','rules.py'):
            text = (ROOT/name).read_text(encoding='utf-8')
            tree = ast.parse(text)
            imports = [n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
            self.assertNotIn('evaluate',imports)
            self.assertNotIn('reference_labels',text)


if __name__ == '__main__':
    unittest.main()
