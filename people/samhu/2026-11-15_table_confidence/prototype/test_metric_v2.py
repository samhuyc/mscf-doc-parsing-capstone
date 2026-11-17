import unittest
from table_structure_v2 import facts,fact_score

class TestMetricV2(unittest.TestCase):
 def fs(self,rows):return facts(dict(cells=rows))['facts']
 def test_year_currency_scale_is_not_a_financial_value(self):
  combined=[['','Note','2024 £ m','2023 £ m'],['Revenue','5','305.0','358.2']]
  split=[['','Note','2024 £','2023 £'],['','','m','m'],combined[-1]]
  self.assertEqual(len(self.fs(combined)),2)
  self.assertEqual(fact_score(self.fs(combined),self.fs(split))['f1'],1)
 def test_unaudited_header_row_is_not_data(self):
  a=[['€ million','Full Year','Full Year'],['(unaudited)','2025','2024'],['Operating profit','9037','8829']]
  b=[['€ million (unaudited)','Full Year','Full Year'],['','2025','2024(a)'],a[-1]]
  self.assertEqual(len(self.fs(a)),2)
  self.assertEqual(fact_score(self.fs(a),self.fs(b))['f1'],1)
 def test_rowspanned_unit_caption_is_header(self):
  a=[['€ million','Full Year','Full Year'],['(unaudited)','2025','2024'],['Profit','100','200']]
  b=[['€ million(unaudited)','Full Year','Full Year'],['€ million(unaudited)','2025','2024(a)'],a[-1]]
  self.assertEqual(fact_score(self.fs(a),self.fs(b))['f1'],1)
 def test_explicit_latex_letter_footnotes_are_metadata(self):
  from table_structure_v2 import label
  self.assertEqual(label(r'2024\(^{(a)}\)'),label('2024(a)'))
  self.assertNotEqual(label('20241'),label('2024'))
 def test_swapped_values_remain_wrong_after_header_fix(self):
  a=[['','2024 £ m','2023 £ m'],['Revenue','305','358']]
  b=[a[0],['Revenue','358','305']]
  self.assertEqual(fact_score(self.fs(a),self.fs(b))['f1'],0)
 def test_real_period_error_remains_wrong(self):
  a=[['','52 weeks ended 1 February 2025 £ m'],['Revenue','894.6']]
  b=[['','53 weeks ended 1 February 2025 £ m'],a[-1]]
  self.assertEqual(fact_score(self.fs(a),self.fs(b))['f1'],0)
 def test_year_shaped_amount_stays_data(self):
  a=[['','2024 £ m','2023 £ m'],['Revenue','2013','2014']]
  self.assertEqual(len(self.fs(a)),2)

if __name__=='__main__':unittest.main()
