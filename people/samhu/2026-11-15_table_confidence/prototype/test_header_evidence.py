import unittest
from header_evidence import header_features
class TestHeaderEvidence(unittest.TestCase):
 def test_low_header_probability_is_separated_from_numeric_cells(self):
  text='<table><tr><td></td><td>2025</td></tr><tr><td>Sales</td><td>100</td></tr></table>'
  a=dict(units=[dict(start=i,end=i+1,score=.2 if text.index('2025')<=i<text.index('2025')+4 else .99) for i in range(len(text))])
  f=header_features(text,'glm',a)
  self.assertAlmostEqual(f['native_header'],.2);self.assertAlmostEqual(f['native_label'],.99)
 def test_no_header_never_invents_a_probability(self):
  f=header_features('Sales 100','glm',dict(units=[]));self.assertIsNone(f['native_header'])
 def test_otsl_spanning_headers_retain_native_units_once(self):
  text='<ecel><fcel>2025<lcel><nl><fcel>Sales<fcel>100<fcel>200<nl>'
  a=dict(units=[dict(start=i,end=i+1,score=.8) for i in range(len(text))])
  f=header_features(text,'paddle_vl',a);self.assertEqual(f['header_units'],4);self.assertAlmostEqual(f['native_header'],.8)
if __name__=='__main__':unittest.main()
