"""Apply existing unchanged Paddle/Tesseract adapters to a fixed input bundle."""
import argparse
from pathlib import Path
import time
from common import ROOT, read, write, sha, digest
from regions import NATIVE
from run_tables import environment, PADDLE_CONFIG, paddle_crop, tesseract_crop, file_manifest

def main():
    cli=argparse.ArgumentParser();cli.add_argument('--root',type=Path,required=True);args=cli.parse_args()
    environment()
    import numpy as np
    from PIL import Image
    from paddleocr import PaddleOCR
    root=args.root.resolve();bundle=read(root/'tables.json');ocr=NATIVE/'work/paddlex/official_models'
    model=PaddleOCR(**PADDLE_CONFIG,text_detection_model_dir=str(ocr/'PP-OCRv5_mobile_det'),text_recognition_model_dir=str(ocr/'PP-OCRv5_mobile_rec'))
    settings=dict(adapter='existing run_tables crop adapters',source_bundle_sha256=sha(root/'tables.json'),paddle=PADDLE_CONFIG,
                  model_files={n:file_manifest(ocr/n) for n in ('PP-OCRv5_mobile_det','PP-OCRv5_mobile_rec')})
    verified=False
    for table in bundle['tables']:
        image=root/table['image'];assert sha(image)==table['image_sha256']
        for engine in ('paddle','tesseract'):
            folder=root/'baseline'/engine;output=folder/(table['table_id']+'.json')
            write(folder/'settings.json',settings)
            if output.exists():
                previous=read(output)
                assert previous['image_sha256']==table['image_sha256'] and previous['settings_sha256']==digest(settings)
                if previous['status']=='success':verified|=bool(previous.get('hook_equivalence_passed'));continue
            try:
                result=paddle_crop(model,np.asarray(Image.open(image).convert('RGB'))[:,:,::-1].copy(),not verified) if engine=='paddle' else tesseract_crop(image,200)
                if engine=='paddle':verified|=bool(result.get('hook_equivalence_passed'))
            except Exception as exc:result=dict(status='failed',error=f'{type(exc).__name__}: {exc}',text='',confidence_units=[])
            result.update(table_id=table['table_id'],image_sha256=table['image_sha256'],source_sha256=table['source_sha256'],settings_sha256=digest(settings))
            write(output,result);print(engine,table['table_id'],result['status'],result.get('seconds'),flush=True)

if __name__=='__main__':main()
