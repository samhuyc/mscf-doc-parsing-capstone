"""Review decisions cannot silently approve stale or corrected references."""
import copy
import unittest

from import_reviews import apply_decisions


class ReviewImportTests(unittest.TestCase):
    def setUp(self):
        self.labels=[dict(id='one',source_sha256='pdf',review_status='draft',rows=[{'values':['12']}])]
        self.decision=dict(id='one',source_sha256='pdf',status='approved',reviewer='Human reviewer',
                           reviewed_at='2026-10-05T12:00:00Z',notes='')
        self.bundle=dict(schema_version=1,label_sha256='version',decisions=[self.decision])

    def test_approval_preserves_reference_and_input(self):
        original=copy.deepcopy(self.labels)
        labels,count=apply_decisions(self.labels,self.bundle,'version')
        self.assertEqual(count,1)
        self.assertEqual(labels[0]['review_status'],'human_verified')
        self.assertEqual(labels[0]['rows'],original[0]['rows'])
        self.assertEqual(self.labels,original)

    def test_correction_does_not_become_ground_truth(self):
        self.decision.update(status='needs_correction',notes='Value should be 13')
        labels,_=apply_decisions(self.labels,self.bundle,'version')
        self.assertEqual(labels[0]['review_status'],'draft')
        self.assertEqual(labels[0]['rows'][0]['values'],['12'])

    def test_stale_missing_identity_duplicate_and_missing_reason_rejected(self):
        for change in ['version','identity','duplicate','source','note']:
            bundle=copy.deepcopy(self.bundle)
            if change=='version':bundle['label_sha256']='stale'
            if change=='identity':bundle['decisions'][0]['reviewer']=''
            if change=='duplicate':bundle['decisions']*=2
            if change=='source':bundle['decisions'][0]['source_sha256']='wrong'
            if change=='note':bundle['decisions'][0]['status']='excluded'
            with self.subTest(change=change),self.assertRaises(ValueError):
                apply_decisions(self.labels,bundle,'version')

    def test_pending_revokes_approval(self):
        self.labels[0]['review_status']='human_verified'
        self.decision.update(status='pending',reviewed_at=None)
        labels,_=apply_decisions(self.labels,self.bundle,'version')
        self.assertEqual(labels[0]['review_status'],'draft')
        self.assertIsNone(labels[0]['reviewed_at'])


if __name__=='__main__':
    unittest.main()
