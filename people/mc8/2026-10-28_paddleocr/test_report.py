"""Regression checks for actual Paddle HTML wrappers in the offline viewer."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from bs4 import BeautifulSoup
from common import ROOT,REFERENCE,load
from report import render_prediction


class ViewerTests(unittest.TestCase):
    def setUp(self):
        self.renderer=load('sam_renderer_test',REFERENCE/'2026-10-05_pilot_benchmark/review_addition.py')
        self.renderer.ROOT=ROOT

    def test_native_paddle_wrappers_keep_table_values_and_spans(self):
        source='<div style="text-align:center"><html><body><table><tr><td colspan="2">Profit (84.6)</td></tr></table></body></html></div>'
        with TemporaryDirectory() as folder:
            actual=BeautifulSoup(render_prediction(source,Path(folder),self.renderer),'html.parser')
        self.assertEqual(len(actual.find_all('table')),1)
        self.assertEqual(actual.find('td').get('colspan'),'2')
        self.assertEqual(actual.find('td').get_text(),'Profit (84.6)')

    def test_untrusted_active_content_and_remote_images_still_removed(self):
        source='<div><script>bad()</script><iframe src="https://example.com"></iframe><table><tr><td onclick="bad()">12</td></tr></table><img src="https://example.com/tracker"></div>'
        with TemporaryDirectory() as folder:
            actual=render_prediction(source,Path(folder),self.renderer)
        for value in ['script','iframe','onclick','https://']:
            self.assertNotIn(value,actual)
        self.assertIn('<td>12</td>',actual)


if __name__=='__main__':
    unittest.main()
