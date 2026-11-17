import unittest
from evaluate import flatten_facts
from table_structure import fact_score

class TestEvaluation(unittest.TestCase):
 def test_repeated_subtables_cannot_swap_values(self):
  a=[dict(cells=[['','2025'],['Profit','100']]),dict(cells=[['','2025'],['Profit','200']])]
  b=[dict(cells=[['','2025'],['Profit','200']]),dict(cells=[['','2025'],['Profit','100']])]
  self.assertEqual(fact_score(flatten_facts(a),flatten_facts(b))['f1'],0)
 def test_source_coordinates_survive_empty_margin(self):
  fs=flatten_facts([dict(cells=[['','','2025'],['','Sales','100']])])
  self.assertEqual((fs[0]['row'],fs[0]['column'],fs[0]['grid_index']),(1,2,0))
if __name__=='__main__':unittest.main()
