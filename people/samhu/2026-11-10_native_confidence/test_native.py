import math
from types import SimpleNamespace
import unittest
import numpy as np
from core import document_result, summarize
from evaluate import association, ranks, score_span, word_reliability, reliability_summary, norm, best_edit_window
from run_tesseract import parse_tsv
from run_paddle import parse_result
from run_mineru import collect_stream, normalized_logprob


class NativeConfidenceTests(unittest.TestCase):
    def test_empty_is_unknown(self):
        self.assertIsNone(summarize([])['mean'])
        self.assertIsNone(summarize([{'text':'x','score':None}])['mean'])

    def test_summaries(self):
        got=summarize([{'text':'a','score':.5},{'text':'long','score':1.}])
        self.assertEqual(got['mean'],.75)
        self.assertEqual(got['character_weighted_mean'],.9)
        self.assertAlmostEqual(got['geometric_mean'],math.sqrt(.5))
        self.assertEqual(got['p10'],.5)
        self.assertIsNone(got['probability_document_correct'])

    def test_invalid_values_rejected(self):
        for value in (float('nan'),float('inf'),-.1,1.1,True):
            with self.assertRaises(ValueError):summarize([{'text':'a','score':value}])

    def test_zero_geomean(self):
        self.assertEqual(summarize([{'text':'a','score':0}])['geometric_mean'],0)

    def test_missing_page_not_perfect(self):
        got=document_result('d','test',[{'page':1,'status':'failed','units':[]}],2)
        self.assertEqual(got['page_coverage'],0)
        self.assertEqual(got['missing_or_failed_page_ids'],[1,2])
        self.assertIsNone(got['confidence']['mean'])

    def test_duplicate_pages_rejected(self):
        with self.assertRaises(ValueError):
            document_result('d','test',[{'page':1,'status':'success','units':[]}]*2,2)

    def test_empty_text_candidates_are_empty_pages(self):
        got=document_result('d','test',[{'page':1,'status':'success','units':[{'text':'','score':0}]}],1)
        self.assertEqual(got['empty_successful_pages'],1)
        self.assertIsNone(got['confidence']['mean'])

    def test_whitespace_token_is_included(self):
        self.assertEqual(summarize([{'text':' ','score':.7,'unit_kind':'subword_token'}])['mean'],.7)

    def test_separate_token_inventory(self):
        got=document_result('d','mineru',[{'page':1,'status':'success',
            'units':[{'text':'hello','score':None}],
            'confidence_units':[{'text':'hello','score':.8}], 'truncated':True}],1)
        self.assertEqual(got['confidence']['mean'],.8)
        self.assertEqual(got['truncated_pages'],[1])

    def test_tsv_pairs_and_sentinel(self):
        header='level\tconf\ttext\tleft\ttop\twidth\theight\tblock_num\tpar_num\tline_num\n'
        data=header+'5\t98\tHello\t1\t2\t3\t4\t1\t1\t1\n5\t-1\tx\t1\t2\t3\t4\t1\t1\t1\n'
        units=parse_tsv(data)
        self.assertEqual(len(units),1)
        self.assertEqual(units[0]['score'],.98)
        self.assertEqual(units[0]['text'],'Hello')
        self.assertEqual(units[0]['bbox'],[1,2,4,6])

    def test_plain_text_is_not_tsv(self):
        with self.assertRaises(ValueError):parse_tsv('Some OCR output\n')

    def test_paddle_pairs(self):
        units=parse_result({'rec_texts':['ab','cd'],'rec_scores':[.9,.2],'rec_polys':[[[0,0]],[[1,1]]]})
        self.assertEqual([(u['text'],u['score']) for u in units],[('ab',.9),('cd',.2)])
        with self.assertRaises(ValueError):parse_result({'rec_texts':['a'],'rec_scores':[],'rec_polys':[]})

    def test_ties_and_constant_rank(self):
        self.assertEqual(ranks([3,1,1]),[3,1.5,1.5])
        self.assertAlmostEqual(association([1,2,3],[3,2,1])['spearman'],-1)
        self.assertIsNone(association([1,2,3],[1,1,1])['spearman'])

    def test_matching_and_omission(self):
        units=[{'text':'prefix','score':.2},{'text':'hello','score':.8},{'text':'world','score':.9}]
        got=score_span('Hello world',units)
        self.assertEqual(got['exact'],1)
        self.assertEqual(got['matched_unit_indices'],[1,2])
        self.assertEqual(score_span('hello',[])['character_accuracy'],0)
        self.assertIsNone(score_span('hello',[])['matched_native_confidence']['mean'])

    def test_format_escapes_preserve_financial_symbols(self):
        self.assertEqual(norm(r'Returned \$866 million, up 5\%.'),'returned $866 million, up 5%.')
        self.assertNotEqual(norm('$866'),norm('866'))

    def test_edit_window_ignores_unrelated_neighbors(self):
        got=score_span('contract. Further',[{'text':'noise contract.Further end','score':None}])
        self.assertEqual(got['matched_output'],'contract.further')
        self.assertEqual(got['edit_errors'],1)

    def test_edit_window_matches_exhaustive_search(self):
        from itertools import product
        from rapidfuzz.distance import Levenshtein
        for chars in product('ab',repeat=4):
            prediction=''.join(chars)
            for target in ('a','aba','bbb','c'):
                start,end=best_edit_window(target,prediction)
                best=min(Levenshtein.distance(target,prediction[i:j]) for i in range(5) for j in range(i,5))
                self.assertEqual(Levenshtein.distance(target,prediction[start:end]),best)

    def test_mlx_final_duplicate_not_counted(self):
        tokenizer=SimpleNamespace(stopping_criteria=lambda t:t==2,decode=lambda ids:['A','B','EOS'][ids[0]])
        def item(text,token,step):
            return SimpleNamespace(text=text,token=token,generation_tokens=step,logprobs=np.log([.6,.3,.1]))
        text,tokens,stopped=collect_stream([item('A',0,1),item('B',1,2),item('!',1,2)],tokenizer)
        self.assertEqual(text,'AB!')
        self.assertEqual(len(tokens),2)
        self.assertFalse(stopped)
        self.assertAlmostEqual(tokens[1]['score'],.3)
        text,tokens,stopped=collect_stream([item('A',0,1),item('',2,2)],tokenizer)
        self.assertEqual(len(tokens),1)
        self.assertTrue(stopped)

    def test_reliability_counts_substitution_and_deletion(self):
        units=[{'text':'hello','score':.9,'unit_kind':'word'},
               {'text':'wurld','score':.8,'unit_kind':'word'}]
        got=word_reliability('hello world missing',units)
        self.assertEqual([w['correct'] for w in got['words']],[True,False])
        self.assertEqual(got['deleted_reference_words'],1)
        self.assertAlmostEqual(reliability_summary(got['words'])['brier'],.325)
        self.assertIsNone(word_reliability('hello',[{'text':'hello','score':.9,'unit_kind':'line'}]))

    def test_decoder_normalization_and_shift_invariance(self):
        raw=np.array([0.,-1.,-2.])
        probs=[math.exp(normalized_logprob(raw,i,np)[0]) for i in range(3)]
        self.assertAlmostEqual(sum(probs),1.,places=6)
        self.assertLess(probs[0],1.)
        self.assertAlmostEqual(normalized_logprob(raw,0,np)[0],
                               normalized_logprob(raw+10,0,np)[0],places=5)


if __name__=='__main__':unittest.main()
