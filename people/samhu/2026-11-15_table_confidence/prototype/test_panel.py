import unittest
from unittest.mock import patch
from pathlib import Path
import panel

class TestPanel(unittest.TestCase):
 def test_unknown_record_cannot_select_arbitrary_path(self):
  with patch.object(panel,'optional',return_value=[dict(cohort='benchmark',engine='glm',table_id='known',image_path='/tmp/image')]):
   self.assertIsNone(panel.detail(dict(cohort=['benchmark'],engine=['glm'],table_id=['../../secret'])))
 def test_detail_requires_matching_engine_and_cohort(self):
  row=dict(cohort='benchmark',engine='glm',table_id='x')
  with patch.object(panel,'optional',return_value=[row]):
   self.assertEqual(panel.detail({k:[v] for k,v in row.items()}),row)
   self.assertIsNone(panel.detail(dict(cohort=['fresh_public'],engine=['glm'],table_id=['x'])))
if __name__=='__main__':unittest.main()
