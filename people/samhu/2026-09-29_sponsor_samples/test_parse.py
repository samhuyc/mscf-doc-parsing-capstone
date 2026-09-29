import json
import tempfile
import unittest
from pathlib import Path
from parse import block_md, export_pages

class ContractTests(unittest.TestCase):
    def test_chart_crop_is_preserved_without_inventing_data(self):
        self.assertIn('](images/chart.jpg)', block_md(dict(type='chart', img_path='images/chart.jpg', content='')))

    def test_table_spans_preserved(self):
        body = '<table><tr><td colspan="2">(1,234)</td></tr></table>'
        self.assertEqual(block_md(dict(type='table', table_body=body)), body)

    def test_pages_include_empty_and_convert_tables(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            pages = export_pages(work, [dict(text='# Revenue\n\n| Item | 2025 |\n|---|---|\n| Profit | (1,234) |\n'), dict(text='')], dict(sha256='test', outline=[]), 'test')
            self.assertEqual(len(pages), 2)
            self.assertEqual(pages[1]['text_chars'], 0)
            self.assertIn('<table>', pages[0]['markdown'])
            self.assertIn('(1,234)', pages[0]['markdown'])
            self.assertIsNone(pages[0]['confidence'])
            self.assertEqual(json.loads((work / 'metadata.json').read_text())['generated_heading_index'][0]['page'], 1)

    def test_image_paths_remain_portable(self):
        with tempfile.TemporaryDirectory() as folder:
            work = Path(folder)
            pages = export_pages(work, [dict(text=f'![x]({work}/images/a.png)')], dict(sha256='test', outline=[]), 'test')
            self.assertIn('](images/a.png)', pages[0]['markdown'])
            self.assertEqual(pages[0]['text_chars'], 0)

if __name__ == '__main__':
    unittest.main()
