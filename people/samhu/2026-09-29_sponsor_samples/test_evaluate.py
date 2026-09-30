import unittest
from evaluate import check_row, numeric_counts

class RowChecks(unittest.TestCase):
    def test_pdf_whitespace_is_collapsed_before_numeric_matching(self):
        self.assertEqual(numeric_counts('Profit' + ' ' * 10000 + '\n10'), {'10': 1})

    def test_swapped_values_fail_row_but_survive_page(self):
        result = check_row('<table><tr><td>Profit</td><td>20</td><td>10</td></tr></table>', dict(label='Profit',values=['10','20']))
        self.assertEqual(result['values_retained'], 2)
        self.assertFalse(result['exact_row_cells'])

    def test_sign_loss_fails(self):
        result = check_row('<table><tr><td>Profit</td><td>10</td></tr></table>', dict(label='Profit',values=['(10)']))
        self.assertEqual(result['values_retained'], 0)
        self.assertFalse(result['exact_row_cells'])

    def test_empty_is_failure(self):
        result = check_row('', dict(label='Profit',values=['10']))
        self.assertEqual(result['values_retained'], 0)
        self.assertFalse(result['exact_row_cells'])

    def test_note_column_is_not_a_value_column(self):
        result = check_row('<table><tr><td>Profit</td><td>2</td><td>10</td><td>(20)</td></tr></table>', dict(label='Profit',values=['10','(20)']))
        self.assertTrue(result['exact_row_cells'])

if __name__ == '__main__':
    unittest.main()
