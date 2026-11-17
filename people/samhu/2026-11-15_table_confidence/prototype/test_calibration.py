import unittest
from copy import deepcopy
from calibration import fit_isotonic,predict,outer_predictions,choose_feature

class TestCalibration(unittest.TestCase):
 def test_monotone_and_ties(self):
  m=fit_isotonic([.1,.2,.2,.3],[1,0,1,1])
  p=[predict(m,x/100) for x in range(101)];self.assertEqual(p,sorted(p));self.assertTrue(all(0<=x<=1 for x in p))
 def rows(self):
  return [dict(table_id=f'{i}-{j}',issuer=str(i),fact_f1=(i+j)%3/2,native_numeric=(i+j+1)/10,native_all=(8-i-j)/10) for i in range(4) for j in range(2)]
 def test_heldout_labels_do_not_change_fit_or_selection(self):
  rows=self.rows();a=outer_predictions(rows,select=True)
  edited=deepcopy(rows)
  for r in edited:
   if r['issuer']=='0':r['fact_f1']=1-r['fact_f1']
  b=outer_predictions(edited,select=True)
  aa=[r for r in a if r['issuer']=='0'];bb=[r for r in b if r['issuer']=='0']
  self.assertEqual([(r['prediction'],r['selected_feature']) for r in aa],[(r['prediction'],r['selected_feature']) for r in bb])
  self.assertTrue(all('0' not in r['training_issuers'] for r in aa))
 def test_missing_heldout_secondary_confidence_falls_back(self):
  rows=self.rows()
  for r in rows:
   r['native_structure']=r['fact_f1']
   if r['issuer']=='0':r['native_structure']=None
  pred=outer_predictions(rows,select=True)
  self.assertTrue(all(r['prediction'] is not None for r in pred))
  for r in pred:
   if r['missing_selected_confidence']:
    self.assertEqual(r['prediction'],r['baseline']);self.assertTrue(r['review'])
 def test_no_numbers_output_is_not_dropped(self):
  rows=self.rows();rows[0]['native_numeric']=None;rows[0]['fact_f1']=0
  pred=outer_predictions(rows)
  self.assertEqual(len(pred),len(rows))
  first=next(r for r in pred if r['table_id']==rows[0]['table_id'])
  self.assertTrue(first['missing_selected_confidence']);self.assertTrue(first['review'])
  self.assertEqual(first['prediction'],first['baseline'])
 def test_missing_primary_can_use_complete_secondary(self):
  rows=self.rows();rows[0]['native_numeric']=None
  pred=outer_predictions(rows,select=True)
  self.assertEqual(len(pred),len(rows))
 def test_baseline_is_training_mean(self):
  rows=self.rows();pred=outer_predictions(rows)
  for r in pred:
   y=[x['fact_f1'] for x in rows if x['issuer']!=r['issuer']]
   self.assertAlmostEqual(r['baseline'],sum(y)/len(y))
if __name__=='__main__':unittest.main()
