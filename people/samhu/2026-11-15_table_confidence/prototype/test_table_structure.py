import unittest
from table_structure import parse_html,parse_otsl,facts,fact_score,ordered_grid_score,value

class TestStructure(unittest.TestCase):
 def grid(self,rows):return dict(cells=rows)
 def score(self,a,b):return fact_score(facts(self.grid(a))['facts'],facts(self.grid(b))['facts'])
 def test_swapped_year_values_are_wrong(self):
  a=[['','2025','2024'],['Sales','100','200']];b=[a[0],['Sales','200','100']]
  self.assertEqual(self.score(a,b)['f1'],0)
 def test_mismatched_row_values_are_wrong(self):
  a=[['','2025'],['Sales','100'],['Costs','200']];b=[a[0],['Sales','200'],['Costs','100']]
  self.assertEqual(self.score(a,b)['f1'],0)
 def test_grouped_headers_preserved(self):
  g=parse_html('<table><tr><th></th><th colspan="2">Underlying</th><th>Statutory</th></tr><tr><td></td><td>2025</td><td>2024</td><td>2025</td></tr><tr><td>Sales</td><td>1</td><td>2</td><td>3</td></tr></table>')[0]
  fs=facts(g)['facts'];self.assertEqual(fs[0]['column_header'],['underlying','2025']);self.assertEqual(fs[2]['column_header'],['statutory','2025'])
 def test_otsl_spanning_headers(self):
  g=parse_otsl('<ecel><fcel>2025<lcel><nl><fcel>Sales<fcel>1<fcel>2<nl>')[0]
  self.assertEqual(g['cells'][0],['','2025','2025'])
 def test_split_header_lines_are_equivalent(self):
  a=[['','2025 £','2024 £'],['Sales','100','200']]
  b=[['','2025','2024'],['','£','£'],['Sales','100','200']]
  self.assertEqual(self.score(a,b)['f1'],1)
 def test_year_with_count_unit_is_header(self):
  a=[['','2025 Number','2024 Number'],['Staff','100','200']]
  b=[['','2025Number','2024Number'],['Staff','100','200']]
  self.assertEqual(len(facts(self.grid(a))['facts']),2);self.assertEqual(self.score(a,b)['f1'],1)
 def test_currency_whitespace_is_not_structure_error(self):
  a=[['','Civil Aerospace £m'],['Sales','100']];b=[['','Civil Aerospace£m'],['Sales','100']]
  self.assertEqual(self.score(a,b)['f1'],1)
 def test_guidance_qualifier_is_meaningful(self):
  a=[['','2025'],['Revenue','At least $391.5']];b=[a[0],['Revenue','$391.5']]
  self.assertEqual(self.score(a,b)['f1'],0)
 def test_repeated_row_labels_do_not_allow_swaps(self):
  a=[['','2025'],['Profit','4.5'],['Profit','4.7']];b=[a[0],['Profit','4.7'],['Profit','4.5']]
  self.assertEqual(self.score(a,b)['f1'],0)
 def test_negative_basis_points(self):
  self.assertEqual(value('(20)bps'),value('-20 bps'))
 def test_math_delimiters_are_not_currency_duplicates(self):
  self.assertEqual(value('$36.3$'),value('$36.3'))
 def test_explicit_footnotes_are_formatting(self):
  from table_structure import label
  for x in ['Revenue[1,2]',r'Revenue\(^{{1, 2}}\)',r'Revenue$^{1}$','Revenue¹','Revenue(a)']:
   self.assertEqual(label(x),'revenue')
  self.assertNotEqual(label('20251'),label('2025'))
 def test_empty_margin_column_is_formatting(self):
  a=[['Sales','100'],['Costs','200']];b=[['']+r for r in a]
  self.assertEqual(self.score(a,b)['f1'],1)
 def test_global_caption_not_a_column_header(self):
  a=[['','2025','2024'],['In millions','',''],['Sales','100','200']]
  b=[a[0],['In millions']*3,a[2]]
  self.assertEqual(self.score(a,b)['f1'],1)
 def test_literal_newline_in_header(self):
  a=[['','2025 £','2024 £'],['Sales','100','200']]
  b=[['',r'2025\n£',r'2024\n£'],a[1]]
  self.assertEqual(self.score(a,b)['f1'],1)
 def test_repeated_headers_reset_associations(self):
  a=[['','2025','2024'],['Sales','100','200'],['','2023','2022'],['Costs','300','400']]
  fs=facts(self.grid(a))['facts'];self.assertEqual(fs[-1]['column_header'],['2022'])
  b=[r[:] for r in a];b[-1]=['Costs','400','300']
  self.assertEqual(self.score(a,b)['f1'],.5)
 def test_grouped_header_swap_stays_wrong(self):
  a=[['','Underlying','Statutory'],['','2025','2025'],['Sales','100','200']]
  b=[a[0],a[1],['Sales','200','100']]
  self.assertEqual(self.score(a,b)['f1'],0)
 def test_word_spacing_does_not_change_financial_association(self):
  a=[['','Fair Value'],['Option cost','100']];b=[['','FairValue'],['Optioncost','100']]
  self.assertEqual(self.score(a,b)['f1'],1)
 def test_units_caption_placement_preserves_scale(self):
  a=[['','2025','2024'],['','(In thousands)','(In thousands)'],['Sales','100','200']]
  b=[a[0],['','(In thousands)',''],a[2]]
  self.assertEqual(self.score(a,b)['f1'],1)
  b[1]=['','(In millions)',''];self.assertEqual(self.score(a,b)['f1'],0)
 def test_html_letter_footnote(self):
  from table_structure import label
  self.assertEqual(label('Latin America<sup>(a)</sup>'),label('Latin America'))
 def test_year_shaped_financial_values_are_not_headers(self):
  a=[['','2025','2024'],['Sales','2013','2014'],['Costs','100','200']]
  self.assertEqual(len(facts(self.grid(a))['facts']),4)
  b=[a[0],['Sales','2014','2013'],a[2]]
  self.assertEqual(self.score(a,b)['f1'],.5)
 def test_global_scale_in_inline_title(self):
  a=[['Quarter results','2025','2024'],['In billions, except per share','',''],['Sales','100','200']]
  b=[['Quarter results\nIn billions, except per share','2025','2024'],a[2]]
  self.assertEqual(self.score(a,b)['f1'],1)
 def test_currency_row_including_margin_retains_unit(self):
  a=[['','2025 £','2024 £'],['Sales','100','200']]
  b=[['','2025','2024'],['£','£','£'],a[1]]
  self.assertEqual(self.score(a,b)['f1'],1)
 def test_title_and_year_header_can_share_row(self):
  a=[['20 Borrowings','',''],['','2025','2024'],['Shares','100','200']]
  b=[['20 Borrowings','2025','2024'],a[2]]
  self.assertEqual(self.score(a,b)['f1'],1)
 def test_negative_percent_parenthesis_placement(self):
  self.assertEqual(value('(11%)'),value('(11)%'))
  self.assertEqual(value('(11%)'),'-11%')
 def test_relational_guidance_qualifiers_preserved(self):
  self.assertNotEqual(value('>100%'),value('100%'))
  self.assertIsNotNone(value('>100%'))
 def test_reference_inline_italics_do_not_turn_years_into_data(self):
  a=[['','US','International'],['<i>In thousands</i>','2025','2024'],['Sales','100','200']]
  b=[a[0],['In thousands','2025','2024'],a[2]]
  self.assertEqual(len(facts(self.grid(a))['facts']),2);self.assertEqual(self.score(a,b)['f1'],1)
 def test_leading_dash_data_row_is_not_header(self):
  a=[['','2025','2024'],['Other income','—','—'],['Sales','100','200']]
  self.assertEqual(len(facts(self.grid(a))['facts']),4)
 def test_unlabeled_note_column_is_metadata(self):
  a=[['','','2025','2024'],['Assets','13','100','200'],['Debtors','14','300','400'],['Capital','15','500','600']]
  b=[['','Note','2025','2024']]+a[1:]
  self.assertEqual(len(facts(self.grid(a))['facts']),6);self.assertEqual(self.score(a,b)['f1'],1)
 def test_attached_camel_case_scale_caption(self):
  a=[['Quarter Results In billions','2025','2024'],['Sales','100','200']]
  b=[['Quarter ResultsIn billions','2025','2024'],a[1]]
  self.assertEqual(self.score(a,b)['f1'],1)
 def test_global_period_caption_placement(self):
  a=[['','Division A','Division B'],['For the half-year ended 30 June 2025','',''],['Sales','100','200']]
  b=[a[0],[a[1][0]]*3,a[2]]
  self.assertEqual(self.score(a,b)['f1'],1)
  b[1]=[a[1][0].replace('2025','2024')]*3;self.assertEqual(self.score(a,b)['f1'],0)
 def test_header_only_margin_does_not_hide_row_label(self):
  a=[['20 Borrowings','',''],['','2025','2024'],['Shares','100','200']]
  b=[['20','Borrowings','',''],['','','2025','2024'],['','Shares','100','200']]
  self.assertEqual(self.score(a,b)['f1'],1)
 def test_invalid_spans_rejected(self):
  with self.assertRaises(ValueError):parse_otsl('<ucel><nl>')
 def test_numeric_normalization_preserves_sign_percent(self):
  self.assertEqual(value('(1,200.00)'),'-1200');self.assertEqual(value('2.0%'),'2%');self.assertIsNone(value('Note 2'))
 def test_omission_and_extra_values_penalized(self):
  a=[['','2025'],['Sales','100'],['Costs','200']]
  self.assertAlmostEqual(self.score(a,a[:2])['f1'],2/3)
 def test_grid_swapped_columns_not_perfect(self):
  a=[['','2025','2024'],['Sales','100','200']]
  self.assertLess(ordered_grid_score(a,[a[0],['Sales','200','100']])['f1'],1)
if __name__=='__main__':unittest.main()
