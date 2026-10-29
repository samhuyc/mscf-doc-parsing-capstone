"""Adversarial checks for scorer behavior, independent of sponsor predictions."""
import copy
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import benchmark

from benchmark import (amount_key, extract_tables, number_key, score_label, soup_for,
                       summarize, table_html, validate)


def gold():
    return dict(id='fixture',kind='table',review_status='draft',importance='critical',
                coverage='complete_data_matrix',columns=[dict(header_path=['2025']),dict(header_path=['2024'])],
                rows=[dict(label='Profit',values=['(84.6)','12.0'])],unit_evidence=[])


def evaluate(markdown, label=None):
    soup = soup_for(markdown)
    tables, _ = extract_tables(soup)
    return summarize(score_label(label or gold(), soup, tables))


class ScoringTests(unittest.TestCase):
    def test_gold_passes(self):
        self.assertEqual(evaluate(table_html(gold()))['associated_value_accuracy']['value'],1)

    def test_spacer_column_does_not_break_header_association(self):
        source = '<table><tr><th>Metric</th><th>2025</th><th></th><th>2024</th></tr><tr><td>Profit</td><td>(84.6)</td><td></td><td>12.0</td></tr></table>'
        self.assertEqual(evaluate(source)['associated_value_accuracy']['value'],1)

    def test_swapped_headers_fail_but_values_remain(self):
        source = table_html(gold()).replace('2025','TEMP').replace('2024','2025').replace('TEMP','2024')
        result = evaluate(source)
        self.assertEqual(result['selected_value_presence']['value'],1)
        self.assertEqual(result['associated_value_accuracy']['value'],0)

    def test_lost_negative_sign_fails(self):
        result = evaluate(table_html(gold()).replace('(84.6)','84.6'))
        self.assertEqual(result['negative_value_accuracy']['value'],0)
        self.assertEqual(result['associated_value_accuracy']['value'],0.5)

    def test_deleted_row_kept_in_denominator(self):
        result = evaluate('')
        self.assertEqual(result['associated_value_accuracy']['total'],2)
        self.assertEqual(result['associated_value_accuracy']['value'],0)

    def test_flattened_numbers_do_not_get_table_credit(self):
        result = evaluate('Profit 2025 (84.6) 2024 12.0')
        self.assertEqual(result['selected_value_presence']['value'],1)
        self.assertEqual(result['associated_value_accuracy']['value'],0)

    def test_duplicate_row_is_ambiguous(self):
        source = table_html(gold()).replace('</table>','<tr><td>Profit</td><td>99</td><td>88</td></tr></table>')
        self.assertEqual(evaluate(source)['associated_value_accuracy']['value'],0)

    def test_extra_row_lowers_complete_numeric_precision(self):
        source = table_html(gold()).replace('</table>','<tr><td>Invented</td><td>99</td><td>88</td></tr></table>')
        self.assertEqual(evaluate(source)['complete_matrix_numeric_precision']['value'],0.5)

    def test_amount_normalization_is_conservative(self):
        self.assertEqual(amount_key('(1,200.00)'),amount_key('-1200'))
        self.assertNotEqual(amount_key('12%'),amount_key('12'))
        self.assertNotEqual(amount_key('12bn'),amount_key('12'))
        self.assertNotEqual(number_key(''),number_key('-'))
        self.assertNotEqual(number_key('-'),number_key('0'))

    def test_currency_removed_has_separate_failure(self):
        label = gold();label['rows'][0]['values'][0]='$84.6'
        result = evaluate(table_html(label).replace('$84.6','84.6'),label)
        self.assertEqual(result['associated_value_accuracy']['value'],1)
        self.assertEqual(result['inline_currency_unit_accuracy']['value'],0)

    def test_no_numeric_substring_matches(self):
        label = gold();label['rows'][0]['values']=['98.9','12.0']
        self.assertEqual(evaluate('198.9 112.0',label)['selected_value_presence']['value'],0)

    def test_hierarchical_headers_and_repeated_domestic(self):
        label = gold();label['columns']=[dict(header_path=['Electricity','Domestic']),dict(header_path=['Gas','Domestic'])]
        self.assertEqual(evaluate(table_html(label),label)['associated_value_accuracy']['value'],1)

    def test_domestic_cannot_match_non_domestic(self):
        label=gold();label['columns']=[dict(header_path=['Gas','Domestic']),dict(header_path=['Gas','Non Domestic'])]
        self.assertEqual(evaluate(table_html(label),label)['associated_value_accuracy']['value'],1)

    def test_same_cell_basis_and_period(self):
        label = gold();label['columns']=[dict(header_path=['Underlying','2025']),dict(header_path=['Statutory','2025'])]
        source = '<table><tr><td></td><td>Underlying 2025</td><td>Statutory 2025</td></tr><tr><td>Profit</td><td>(84.6)</td><td>12.0</td></tr></table>'
        self.assertEqual(evaluate(source,label)['associated_value_accuracy']['value'],1)

    def test_absolute_and_percent_change_are_different_columns(self):
        label=gold();label['columns']=[dict(header_path=['Change']),dict(header_path=['Change %'])]
        self.assertEqual(evaluate(table_html(label),label)['associated_value_accuracy']['value'],1)

    def test_malformed_span_is_rejected(self):
        soup=soup_for('<table><tr><td rowspan="-1">Bad</td></tr></table>')
        tables, errors=extract_tables(soup)
        self.assertFalse(tables);self.assertTrue(errors)

    def test_reading_order_requires_unique_present_anchors(self):
        label=dict(id='order',kind='reading_order',review_status='draft',importance='supporting',before='First',after='Last')
        self.assertEqual(evaluate('First then Last',label)['reading_order_accuracy']['value'],1)
        self.assertEqual(evaluate('Last then First',label)['reading_order_accuracy']['value'],0)
        self.assertEqual(evaluate('First First Last',label)['reading_order_accuracy']['value'],0)

    def test_metadata_does_not_get_scored_from_source_manifest(self):
        label=dict(id='meta',kind='metadata',review_status='draft',importance='supporting',field='issuer',value='Acme',evidence_text='Acme')
        result=evaluate('Acme',label)
        self.assertIsNone(result['metadata_field_accuracy']['value'])
        self.assertEqual(result['metadata_evidence_retention']['value'],1)

    def test_images_are_not_text_evidence(self):
        self.assertEqual(evaluate('![Profit (84.6) 12.0](image.png)')['selected_value_presence']['value'],0)

    def test_visual_sequence_is_not_claimed_as_semantic(self):
        label=dict(id='visual',kind='visual_fact',review_status='draft',importance='critical',label='Profit',value='£2.5bn',next_label='Margin')
        result=evaluate('Profit £2.5bn Margin 22%',label)
        self.assertEqual(result['visual_label_value_sequence']['value'],1)
        self.assertIsNone(result['visual_semantic_association']['value'])
        self.assertEqual(evaluate('Profit £9bn Margin £2.5bn',label)['visual_label_value_sequence']['value'],0)

    def test_all_source_reference_cells_round_trip(self):
        for label in benchmark.read_jsonl(benchmark.ROOT/'labels.jsonl'):
            if label['kind'] == 'table':
                with self.subTest(label=label['id']):
                    self.assertEqual(evaluate(table_html(label),label)['associated_value_accuracy']['value'],1)

    def test_review_gate_missing_predictions_and_source_mismatch(self):
        label=gold()
        label.update(document='fixture_doc',page=1,source_sha256='abc',evidence={'region':'top'})
        with TemporaryDirectory() as folder, patch.object(benchmark,'ROOT',Path(folder)):
            root=Path(folder)
            benchmark.write_json(root/'documents.json',[dict(id='fixture_doc',pages=1,sha256='abc')])
            benchmark.write_jsonl(root/'labels.jsonl',[label])
            cached=root/'cached'
            result=benchmark.score(output_root=cached)
            self.assertEqual(result['selected_labels'],0)
            self.assertTrue(all(not metrics for metrics in result['aggregate'].values()))
            result=benchmark.score(include_drafts=True,output_root=cached)
            for parser in benchmark.PARSERS:
                self.assertEqual(result['aggregate'][parser]['associated_value_accuracy']['total'],2)
                self.assertEqual(result['aggregate'][parser]['associated_value_accuracy']['value'],0)
            label['review_status']='human_verified'
            benchmark.write_jsonl(root/'labels.jsonl',[label])
            with self.assertRaises(AssertionError):
                benchmark.score(output_root=cached)
            label.update(reviewer='test reviewer',reviewed_at='2026-10-05')
            benchmark.write_jsonl(root/'labels.jsonl',[label])
            self.assertEqual(benchmark.score(output_root=cached)['selected_labels'],1)
            benchmark.write_json(cached/'fixture_doc'/benchmark.PARSERS[0]/'pages.json',
                                 dict(source_sha256='wrong',parser=benchmark.PARSERS[0],pages=[]))
            with self.assertRaisesRegex(AssertionError,'source hash mismatch'):
                benchmark.score(output_root=cached)


if __name__=='__main__':
    unittest.main()
