import unittest
from standard_metric import content_score
class TestStandard(unittest.TestCase):
 def test_identity(self):
  g=[dict(cells=[['','2025','2024'],['Sales','100','200']])]
  self.assertAlmostEqual(content_score(g,g)['f1'],1)
 def test_swapped_values_lose_credit(self):
  a=[dict(cells=[['','2025','2024'],['Sales','100','200']])]
  b=[dict(cells=[['','2025','2024'],['Sales','200','100']])]
  self.assertLess(content_score(a,b)['f1'],1)
 def test_missing_table_zero(self):
  self.assertEqual(content_score([dict(cells=[['Sales','100']])],[])['f1'],0)
if __name__=='__main__':unittest.main()
