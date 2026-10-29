"""Protect physical-page scoring and recovery of already completed inference."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from selected_support import checkpoints, export_sparse


class SelectedPagesTests(unittest.TestCase):
    def test_sparse_export_preserves_physical_numbers_and_heading_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp)
            source=dict(id='sparse',pages=39,sha256='original-pdf',outline=[])
            completed={i:dict(chunk=dict(text=f'# Physical {i}\n\nValue {i}',native=dict(page_index=i-1)),
                         audit=dict(page=i)) for i in (1,20,21)}
            pages=export_sparse(work,completed,source)
            self.assertEqual([p['page'] for p in pages],[1,20,21])
            self.assertIn('Value 20',pages[1]['markdown'])
            self.assertTrue(all(p['confidence'] is None for p in pages))
            metadata=json.loads((work/'metadata.json').read_text())
            self.assertEqual([h['page'] for h in metadata['generated_heading_index']],[1,20,21])
            self.assertNotIn('<!-- source page 2 -->',(work/'document.md').read_text())
            self.assertEqual(json.loads((work/'pages.json').read_text())['source_sha256'],'original-pdf')

    def test_legacy_recovery_keeps_native_output_and_portable_image_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp)
            (work/'raw').mkdir()
            (work/'images/page_020').mkdir(parents=True)
            (work/'images/page_020/figure.png').write_bytes(b'untouched crop')
            native='{"res":{"parsing_res_list":[]}}\n'
            (work/'raw/page_020.json').write_text(native)
            markdown='![Figure](imgs/figure.png)\n\n20'
            (work/'raw/page_020.md').write_text(markdown)
            audit=dict(page=20,raw_prediction='raw/page_020.json',raw_sha256=hashlib.sha256(native.encode()).hexdigest())
            (work/'progress.json').write_text(json.dumps(dict(pages=[audit])))
            recovered=checkpoints(work)
            self.assertEqual(list(recovered),[20])
            self.assertEqual(recovered[20]['chunk']['native']['page_index'],19)
            self.assertIn('images/page_020/figure.png',recovered[20]['chunk']['text'])
            self.assertEqual((work/'raw/page_020.md').read_text(),markdown)
            (work/'raw/page_020.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                checkpoints(work)


if __name__=='__main__':
    unittest.main()
