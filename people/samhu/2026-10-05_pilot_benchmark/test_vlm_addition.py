"""Focused integration checks for the new OCR path and untrusted-output viewer."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import importlib.util
HAS_PYMUPDF = importlib.util.find_spec("pymupdf") is not None
from review_addition import rendered


class VlmAdditionTests(unittest.TestCase):
    @unittest.skipUnless(HAS_PYMUPDF, "OCR integration test needs the sponsor PyMuPDF environment")
    def test_scanned_page_gets_recognizer_text_through_real_pymupdf_callback(self):
        import pymupdf
        import run_pymupdf_vlm as runner
        # The fake recognizes deliberately different text: success proves the
        # real extraction/export consumes callback text, not embedded text/OCR.
        class Recognizer:
            info={'model':'fixture-vlm'}
            def __init__(self,*args): pass
            def recognize(self,image,output):
                pix=pymupdf.Pixmap(str(image))
                result={'status':'success','elapsed_seconds':0,'predictions':[
                    {'box':[[120,120],[900,120],[900,200],[120,200]],
                     'text':'VLM RECOGNIZED 123.45','confidence':None}]}
                output.write_text(json.dumps(result))
                return result
            def close(self): pass
        with TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source';(source/'inputs').mkdir(parents=True)
            original=pymupdf.open();p=original.new_page();p.insert_text((30,40),'PIXELS ONLY',fontsize=20)
            pix=p.get_pixmap(dpi=150)
            scan=pymupdf.open();scan.new_page().insert_image(p.rect,pixmap=pix)
            pdf=source/'inputs/fixture.pdf';scan.save(pdf)
            manifest={'id':'fixture','sha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'pages':1,'outline':[]}
            args=SimpleNamespace(skip_existing=False,mineru_python=Path('unused'),model_config=Path('unused'))
            with patch.object(runner,'ROOT',root),patch.object(runner,'SOURCE',source),patch.object(runner,'LocalRecognizer',Recognizer),patch.object(runner,'code_hashes',return_value={}):
                record=runner.run(manifest,args)
            self.assertEqual(record['status'],'success')
            self.assertEqual(record['vlm_pages'],[1])
            self.assertEqual(record['recognized_regions'],1)
            work=root/'results/parsed/fixture/pymupdf4llm_vlm'
            document=(work/'document.md').read_text()
            self.assertIn('VLM RECOGNIZED',document)
            self.assertIn('123.45',document)
            self.assertNotIn('PIXELS ONLY',document)
            self.assertEqual(json.loads((work/'pages.json').read_text())['source_sha256'],manifest['sha256'])

    @unittest.skipUnless(HAS_PYMUPDF, "Export integration needs the sponsor PyMuPDF environment")
    def test_image_paths_portable_without_changing_recognized_text(self):
        import export_vlm
        with TemporaryDirectory() as folder:
            root=Path(folder);work=root/'results/parsed/fixture/pymupdf4llm_vlm'
            (work/'images').mkdir(parents=True)
            (work/'images/test.png').write_bytes(b'fixture')
            relative='results/parsed/fixture/pymupdf4llm_vlm/images/test.png'
            text=f'Profit (84.6) ![figure]({relative}) ![figure]({work}/images/test.png)'
            with patch.object(export_vlm,'ROOT',root):
                actual=export_vlm.portable_markdown(text,work)
            self.assertEqual(actual,'Profit (84.6) ![figure](images/test.png) ![figure](images/test.png)')

    def test_renderer_drops_active_html_and_outside_images(self):
        with TemporaryDirectory() as folder:
            text='<script>alert(1)</script><iframe src="https://example.com"></iframe><table><tr><td colspan="2" onclick="bad()">12</td></tr></table><img src="https://example.com/tracker"><a href="javascript:alert(1)">x</a>'
            clean=rendered(text,Path(folder))
            for forbidden in ['script','iframe','onclick','https://','javascript:']:
                self.assertNotIn(forbidden,clean)
            self.assertIn('colspan="2"',clean)
            self.assertIn('12',clean)

if __name__=='__main__':
    unittest.main()
