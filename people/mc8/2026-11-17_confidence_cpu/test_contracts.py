"""Small synthetic checks. No models, dataset inference or fitting."""
import copy
import unittest
from common import sam_paths
from worker import decoded_record


class Contracts(unittest.TestCase):
    def test_utf8_fragments_share_character_evidence(self):
        r=decoded_record(dict(backend='llama.cpp-cpu',confidence_units=[
            dict(token_id=1,piece_hex='c2',score=.8),
            dict(token_id=2,piece_hex='a331',score=.9)]))
        self.assertEqual(r['text'],'£1')
        self.assertEqual(r['confidence_units'][0]['decoded_span'],[0,1])
        self.assertEqual(r['confidence_units'][1]['decoded_span'],[0,2])

    def test_incomplete_unicode_is_flagged(self):
        r=decoded_record(dict(backend='llama.cpp-cpu',confidence_units=[dict(token_id=1,piece_hex='c2',score=.8)]))
        self.assertIn('alignment_error',r)

    def test_reference_never_selects_native_tokens(self):
        from sam_bridge import evidence
        text='<table><tr><td>Revenue</td><td>123</td></tr></table>'
        r=dict(backend='llama.cpp-cpu',text=text,confidence_units=[dict(token_id=0,score=.7,decoded_span=[0,len(text)])])
        a,_=evidence(r,'glm')
        r['reference']='wrong label 999'
        b,_=evidence(r,'glm')
        self.assertEqual(a,b)
        self.assertEqual(a['numeric_tokens']['n'],1)

    def test_swapped_years_lose_association_credit(self):
        from sam_bridge import parse_output,flatten_facts,fact_score
        a='<table><tr><td></td><td>2025</td><td>2024</td></tr><tr><td>Revenue</td><td>123</td><td>98</td></tr></table>'
        b=a.replace('<td>123</td><td>98</td>','<td>98</td><td>123</td>')
        ref=flatten_facts(parse_output(a,'glm')['grids'])
        pred=flatten_facts(parse_output(b,'glm')['grids'])
        self.assertTrue(ref)
        self.assertLess(fact_score(ref,pred)['f1'],1)

    def test_missing_confidence_uses_explicit_baseline(self):
        sam_paths()
        from calibrate import forecast
        f=dict(selected_feature='native_numeric',isotonic=[],baseline=.6,review_cutoff=None)
        result=forecast(f,dict(native_numeric=None))
        self.assertEqual(result['expected_f1'],.6)
        self.assertTrue(result['review'])
        self.assertTrue(result['missing_selected_confidence'])


if __name__=='__main__':unittest.main()
