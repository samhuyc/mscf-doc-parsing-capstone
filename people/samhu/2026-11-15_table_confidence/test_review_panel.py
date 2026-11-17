import json
from pathlib import Path
import tempfile
import unittest
from review_panel import CHECKS, ReviewStore, parse_grids


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'review.json'
        self.table = dict(table_id='test', image_sha256='image', source_sha256='pdf',
                          draft_sha256='draft', grids=[dict(name='Table 1', cells=[['Metric', '2025', '2024'], ['Revenue', '100', '90']])])
        self.store = ReviewStore(self.path, [self.table], 'refs')

    def tearDown(self):
        self.tmp.cleanup()

    def payload(self):
        value = self.store.default('test')
        value.update(action='approve', reviewer='Test reviewer', checks={k: True for k in CHECKS})
        return value

    def test_merged_headers_preserve_context(self):
        grids = parse_grids('<table><tr><th rowspan="2">Metric</th><th colspan="2">2025</th></tr><tr><th>Actual</th><th>Forecast</th></tr><tr><td>Revenue</td><td>1<br>2</td><td>3</td></tr></table>')
        self.assertEqual(grids[0]['cells'], [['Metric', '2025', '2025'], ['Metric', 'Actual', 'Forecast'], ['Revenue', '1\n2', '3']])

    def test_multiple_tables_are_preserved(self):
        self.assertEqual(len(parse_grids('<table><tr><td>A</td></tr></table><table><tr><td>B</td></tr></table>')), 2)

    def test_no_implicit_approval(self):
        p = self.payload(); p['action'] = 'save'
        result = self.store.save(p)
        self.assertFalse(result['human_verified'])
        self.assertFalse(any(result['checks'].values()))

    def test_requires_all_checks_and_identity(self):
        for key in CHECKS:
            p = self.payload(); p['checks'][key] = False
            with self.assertRaises(ValueError): self.store.save(p)
        p = self.payload(); p['reviewer'] = ''
        with self.assertRaises(ValueError): self.store.save(p)

    def test_approval_persists_with_source_and_history(self):
        result = self.store.save(self.payload())
        loaded = ReviewStore(self.path, [self.table], 'refs')
        self.assertTrue(loaded.records['test']['human_verified'])
        self.assertEqual(loaded.records['test']['grids'], self.table['grids'])
        self.assertEqual(result['source_sha256'], 'pdf')
        self.assertEqual(len(list((self.path.parent / 'history').glob('*.json'))), 1)

    def test_swapping_values_revokes_approval(self):
        p = self.store.save(self.payload())
        p['action'] = 'save'
        p['grids'][0]['cells'][1] = ['Revenue', '90', '100']
        result = self.store.save(p)
        self.assertFalse(result['human_verified'])
        self.assertEqual(result['status'], 'draft')
        self.assertNotEqual(result['grids'], self.table['grids'])

    def test_changing_row_labels_revokes_approval(self):
        p = self.store.save(self.payload()); p['action'] = 'save'
        p['grids'][0]['cells'][1][0] = 'Profit'
        self.assertFalse(self.store.save(p)['human_verified'])

    def test_stale_tab_cannot_overwrite(self):
        self.store.save(self.payload())
        with self.assertRaises(RuntimeError): self.store.save(self.payload())

    def test_flag_requires_note_and_excludes_table(self):
        p = self.payload(); p['action'] = 'flag'
        with self.assertRaises(ValueError): self.store.save(p)
        p['notes'] = 'Shared headers cut off'
        result = self.store.save(p)
        self.assertFalse(result['human_verified'])
        self.assertEqual(result['status'], 'needs_attention')

    def test_changed_source_cannot_reuse_review(self):
        self.store.save(self.payload())
        changed = dict(self.table, image_sha256='different')
        with self.assertRaises(ValueError): ReviewStore(self.path, [changed], 'refs')
        with self.assertRaises(ValueError): ReviewStore(self.path, [self.table], 'newrefs')

    def test_nonrectangular_and_empty_grid_rejected(self):
        p = self.payload(); p['grids'][0]['cells'][1].pop()
        with self.assertRaises(ValueError): self.store.save(p)
        p = self.payload(); p['grids'] = [dict(name='Empty', cells=[['']])]
        with self.assertRaises(ValueError): self.store.save(p)

    def test_assistant_draft_does_not_claim_human_review(self):
        self.table['assistant_review'] = dict(grids=[dict(name='Corrected', cells=[['2025', '2024'], ['100', '90']])], context='Checked source', requires_recrop=False)
        value = self.store.default('test')
        self.assertEqual(value['grids'][0]['name'], 'Corrected')
        self.assertFalse(value['human_verified'])
        self.assertFalse(self.path.exists())

    def test_incomplete_crop_cannot_be_approved(self):
        self.table['assistant_review'] = dict(requires_recrop=True)
        with self.assertRaisesRegex(ValueError, 'recrop'):
            self.store.save(self.payload())

    def test_human_approval_preserved_but_recheck_excluded(self):
        approved = self.store.save(self.payload())
        self.table['assistant_review'] = dict(material_correction=True, based_on_human_revision=approved['revision'])
        snapshot = self.store.snapshot()
        self.assertTrue(snapshot['reviews']['test']['human_verified'])
        self.assertEqual(snapshot['evaluation_status']['test'], 'needs_recheck')
        self.assertEqual(snapshot['evaluation_eligible_ids'], [])
        p = dict(approved, action='approve')
        self.store.save(p)
        self.assertEqual(self.store.snapshot()['evaluation_eligible_ids'], ['test'])

    def test_source_data_never_mutated(self):
        p = self.payload(); p['grids'][0]['cells'][1][1] = '42'
        self.store.save(p)
        self.assertEqual(self.table['grids'][0]['cells'][1][1], '100')


if __name__ == '__main__':
    unittest.main()
