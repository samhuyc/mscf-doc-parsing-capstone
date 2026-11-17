import unittest
from native_evidence import stable_spans,numeric_spans,features,summary,visible_spans

class TestNative(unittest.TestCase):
 def test_split_unicode_keeps_both_probabilities(self):
  pieces={0:'',1:'\ufffd',2:'£',3:'£2'}
  text,spans=stable_spans([1,2,3],lambda ids:pieces[len(ids)])
  self.assertEqual(text,'£2');self.assertEqual(spans,[(0,1),(0,1),(1,2)])
 def test_markup_digits_excluded(self):
  t='<td colspan="2">(1,234)</td><td>3.2%</td>'
  self.assertEqual([t[a:b].strip() for a,b in numeric_spans(t)],['(1,234)','3.2%'])
 def test_visible_content_excludes_markup_and_keeps_labels(self):
  t='<td colspan="2">Sales 120</td>'
  self.assertEqual([t[a:b] for a,b in visible_spans(t)],['Sales','120'])
 def test_zero_not_missing(self):
  self.assertEqual(summary([0,.9])['geometric_mean'],0)
  self.assertIsNone(summary([])['geometric_mean'])
 def test_tesseract_native_preserved(self):
  r=dict(text='Sales\n120',confidence_units=[dict(text='Sales',score=.95),dict(text='120',score=.3)])
  f,a=features(r,'tesseract');self.assertEqual(f['numeric_tokens']['mean'],.3)
  self.assertEqual(r['confidence_units'][1]['score'],.3)
 def test_paddle_duplicate_digits_aligned(self):
  r=dict(text='11\n2',units=[dict(text='11'),dict(text='2')],confidence_units=[dict(text='1',line_index=0,score=.8),dict(text='1',line_index=0,score=.6),dict(text='2',line_index=1,score=.9)])
  f,a=features(r,'paddle');self.assertEqual([u['start'] for u in a['units']],[0,1,3]);self.assertEqual(len(f['numbers']),2)
if __name__=='__main__':unittest.main()
