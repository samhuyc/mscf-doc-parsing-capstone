import unittest
from numeric_accuracy import numbers,numeric_score


class TestNumericAccuracy(unittest.TestCase):
    def test_signs_and_empty_cell(self):
        self.assertEqual(numbers('<td>-</td><td>679</td> (1,234.50) −8'),['679','-1234.5','-8'])

    def test_markup_numbers_are_not_content(self):
        self.assertEqual(numbers('<td rowspan="2">12</td><fcel>3<nl>'),['12','3'])

    def test_currency_header_is_not_a_year_suffix(self):
        self.assertEqual(numbers('30 June 2026 £m (£1,200) $98.9'),['30','2026','-1200','98.9'])

    def test_compact_date_is_not_an_ocr_error(self):
        self.assertEqual(numbers('30Jun2026'),numbers('30 June 2026'))

    def test_units_dates_and_note_markers(self):
        self.assertEqual(numbers('H1 2025¹ 1.6pts 22.0% 115-120% 000s'),['2025','1','1.6pts','22%','115','120%'])

    def test_repeated_values_require_repeated_matches(self):
        s=numeric_score(['1','1','2'],['1','2'])
        self.assertEqual(s['matched_numbers'],2)
        self.assertEqual(s['missing'],['1'])

    def test_extra_numbers_reduce_precision(self):
        self.assertEqual(numeric_score(['1'],['1','9'])['f1'],2/3)

    def test_sign_error_is_error(self):
        self.assertEqual(numeric_score(['-10'],['10'])['f1'],0)

    def test_column_swaps_not_detected(self):
        self.assertEqual(numeric_score(['1','2'],['2','1'])['f1'],1)


if __name__=='__main__':unittest.main()
