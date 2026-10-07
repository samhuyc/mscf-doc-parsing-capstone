import unittest

from helpers import make_document
from adapters import validate_evidence
from rule_extractor import extract
from schema import validate_fields


def fields(*texts):
    doc = make_document(texts)
    result = extract(doc)[0]
    assert not validate_fields(result)
    assert not validate_evidence(doc, result)['errors']
    return result


class RuleTests(unittest.TestCase):
    def test_current_period_vs_comparative_table(self):
        result = fields('# H1 2023\n<table><tr><th>H1 2022</th><th>H1 2023</th></tr></table>',
                        'For the half-year ended 30 June 2023', 'For the half-year ended 30 June 2022')
        self.assertEqual(result['reporting_period']['value']['year'], 2023)
        self.assertEqual(result['reporting_period_end']['value'], '2023-06-30')

    def test_future_forecast_not_largest_year(self):
        result = fields('# H1 2023\n<table><tr><td>H1 2099 forecast</td></tr></table>')
        self.assertEqual(result['reporting_period']['value']['year'], 2023)

    def test_conflicting_headings(self):
        self.assertEqual(fields('# H1 2023\n# H1 2022')['reporting_period']['status'], 'ambiguous')

    def test_ambiguous_numeric_date(self):
        self.assertEqual(fields('Report and financial statements for the year ended 03/04/2022')['reporting_period_end']['status'], 'ambiguous')

    def test_invalid_calendar_date(self):
        self.assertIsNone(fields('Report and financial statements for the year ended 31 February 2022')['reporting_period_end']['value'])

    def test_companies_house_stamp(self):
        result = fields('Results Press Release\n16/06/2023 COMPANIES HOUSE')
        self.assertIsNone(result['document_date']['value'])

    def test_as_of_and_approval_dates(self):
        for prefix in ('As of', 'As at', 'Approved', 'Signed', 'Copyright'):
            with self.subTest(prefix=prefix):
                self.assertIsNone(fields(f'Results Presentation\n{prefix} 20 July 2022')['document_date']['value'])

    def test_no_inferred_quarter_end(self):
        result = fields('Q2 2023 Earnings Presentation')
        self.assertEqual(result['reporting_period']['value']['number'], 2)
        self.assertIsNone(result['reporting_period_end']['value'])

    def test_generic_issuer_and_competing_entities(self):
        self.assertEqual(fields('# Example Limited')['issuer']['value'], 'Example Limited')
        self.assertEqual(fields('# Example Limited\n# Another plc')['issuer']['status'], 'ambiguous')
        self.assertEqual(fields('Brand without legal suffix')['issuer']['status'], 'not_found')

    def test_excluded_candidates_preserved(self):
        _, audit = extract(make_document(['Results Press Release\n16/06/2023 COMPANIES HOUSE']))
        self.assertTrue(any(c['disposition'] == 'excluded' for c in audit['candidates']['document_date']))
