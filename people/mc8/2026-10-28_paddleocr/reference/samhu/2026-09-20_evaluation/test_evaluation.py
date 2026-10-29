"""Synthetic unit fixtures test metric behavior; they are not benchmark labels."""
import json
import tempfile
import unittest
from pathlib import Path

from formats import canonical, fact_groups, numbers, plain_text, read_jsonl, write_jsonl
from score import prf, score_page, table_scores


def table(a='10', b='20'):
    return f'<table><tr><th>Year</th><th>2024</th><th>2025</th></tr><tr><td>Revenue</td><td>{a}</td><td>{b}</td></tr></table>'


class EvaluationTests(unittest.TestCase):
    def test_number_format_and_multiplicity(self):
        self.assertEqual(numbers('1,200 12.00 -2 (3) 4% −5'), ['1,200', '12.00', '-2', '(3)', '4%', '-5'])
        from formats import numeric_counts
        p, r, f = prf(numeric_counts('10 10 20'), numeric_counts('10 20'))
        self.assertEqual(p, 1)
        self.assertAlmostEqual(r, 2/3)
        self.assertLess(f, 1)
        self.assertNotEqual(numbers('1,200'), numbers('12.00'))
        self.assertNotEqual(numbers('(3)'), numbers('3'))
        self.assertEqual(numbers('收入2024年增长10%'), ['2024', '10%'])
        self.assertEqual(numbers('($3) (4)% -$5 $-6'), ['($3)', '(4)%', '-$5', '$-6'])
        self.assertNotEqual(numbers('($3)'), numbers('$3'))

    def test_identity(self):
        h = table()
        m, _, _ = score_page(dict(content=h, format='html', tables=[h]), h)
        for key in ('text_similarity', 'numeric_f1', 'table_structure', 'table_content', 'table_numeric_cell_f1'):
            self.assertEqual(m[key], 1, key)
        self.assertIsNone(m['critical_context_recall'])

    def test_swapped_columns(self):
        h, swapped = table(), table('20', '10')
        m, _, _ = score_page(dict(content=h, format='html', tables=[h]), swapped)
        self.assertEqual(m['numeric_f1'], 1)
        self.assertEqual(m['table_structure'], 1)
        self.assertLess(m['table_content'], 1)
        self.assertEqual(m['table_numeric_cell_f1'], .5)

    def test_missing_and_extra_table(self):
        h = table()
        m, _, _ = table_scores([h], '')
        self.assertEqual(m['table_structure'], 0)
        self.assertEqual(m['table_numeric_cell_f1'], 0)
        m, _, _ = table_scores([h], h+h)
        self.assertEqual(m['table_structure'], .5)
        self.assertLess(m['table_numeric_cell_f1'], 1)

    def test_malformed_and_spans(self):
        h = table()
        m, _, flags = table_scores([h], h.replace('</table>', ''))
        self.assertIn('malformed_or_nested_table', flags)
        self.assertEqual(m['table_structure'], 0)
        merged = h.replace('<th>Year</th>', '<th rowspan="2">Year</th>')
        m, _, _ = table_scores([h], merged)
        self.assertLess(m['table_structure'], 1)
        bad = h.replace('<th>Year</th>', '<th colspan="-1">Year</th>')
        m, _, flags = table_scores([h], bad)
        self.assertEqual(m['table_content'], 0)

    def test_pipe_adapter(self):
        source = '# Results\n\n| Metric | 2025 |\n| --- | --- |\n| Revenue | 20 |\n'
        converted = canonical(source, 'markdown')
        self.assertIn('<table>', converted)
        self.assertTrue(converted.startswith('# Results'))
        self.assertNotIn('| ---', converted)
        self.assertEqual(plain_text(source), plain_text(converted))

    def test_fin_context(self):
        gold = '<p>Revenue <temporal>2024</temporal>: <number>10</number></p><p>Revenue <temporal>2025</temporal>: <number>20</number></p>'
        groups = fact_groups(gold)
        ref = dict(content=gold, format='html', fact_groups=groups, tables=None)
        m, _, _ = score_page(ref, gold)
        self.assertEqual(m['critical_context_recall'], 1)
        swapped = gold.replace('>10<', '>TEMP<').replace('>20<', '>10<').replace('>TEMP<', '>20<')
        m, _, _ = score_page(ref, swapped)
        self.assertEqual(m['critical_span_recall'], 1)
        self.assertEqual(m['critical_context_recall'], 0)
        self.assertIsNone(m['table_structure'])
        changed = gold.replace('>10<', '>10.0<')
        m, _, _ = score_page(ref, changed)
        self.assertLess(m['critical_span_recall'], 1)
        self.assertLess(m['critical_context_recall'], 1)

    def test_duplicate_ids_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'a.jsonl'
            write_jsonl(p, [{'id': 'a'}, {'id': 'a'}])
            with self.assertRaises(ValueError):
                read_jsonl(p)

    def test_failed_predictions_count(self):
        from score import evaluate
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            write_jsonl(d/'in.jsonl', [dict(id='a', dataset='test', source_id='a')])
            write_jsonl(d/'ref.jsonl', [dict(id='a', content=table(), format='html', tables=[table()])])
            write_jsonl(d/'pred.jsonl', [])
            result = evaluate(d/'in.jsonl', d/'ref.jsonl', d/'pred.jsonl')
            self.assertEqual(result['summary']['test']['pages'], 1)
            self.assertEqual(result['summary']['test']['successful'], 0)
            self.assertEqual(result['summary']['test']['metrics']['numeric_f1']['mean'], 0)
            write_jsonl(d/'pred.jsonl', [dict(id='extra', status='failed')])
            with self.assertRaises(ValueError):
                evaluate(d/'in.jsonl', d/'ref.jsonl', d/'pred.jsonl')


if __name__ == '__main__':
    unittest.main()
