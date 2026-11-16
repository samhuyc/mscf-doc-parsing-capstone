import unittest
from types import SimpleNamespace as NS
from extra_scores import collect, classify_content

class TestEvidence(unittest.TestCase):
    def event(self, token, text='', finish=None, ids=None):
        return NS(token=token, text=text, finish_reason=finish, token_ids=ids,
                  prompt_tokens=10, peak_memory=2)

    def test_eos_not_scored(self):
        observer = NS(records=[dict(token_id=7), dict(token_id=9), dict(token_id=10)])
        result = collect(iter([self.event(7,'x'), self.event(9,finish='stop',ids=[7,9])]),observer)
        self.assertEqual(result['token_ids'],[7])
        self.assertEqual(len(result['confidence_units']),1)
        self.assertFalse(result['truncated'])

    def test_length_final_does_not_duplicate_token(self):
        result = collect(iter([self.event(7,'x'),self.event(7,'!',finish='length',ids=[7])]))
        self.assertEqual(result['token_ids'],[7])
        self.assertEqual(result['text'],'x!')
        self.assertTrue(result['truncated'])

    def test_alignment_mismatch_fails(self):
        with self.assertRaises(ValueError):
            collect(iter([self.event(7,'x'),self.event(9,finish='stop',ids=[7,9])]),
                    NS(records=[dict(token_id=8)]))

    def test_mixed_markup_token_excluded(self):
        pieces=['<td>', '123', '</td><td>4', '5', '</td>']
        tokenizer=NS(decode=lambda ids,**kw: ''.join(pieces[i] for i in ids))
        units=[dict(token_id=i,text=p,score=.8,unit_kind='subword_token') for i,p in enumerate(pieces)]
        result=classify_content(units,tokenizer)
        self.assertEqual(result['token_counts'],dict(formatting=2,content=2,mixed=1))
        self.assertEqual(result['confidence']['scored_units'],2)

if __name__ == '__main__':
    unittest.main()
