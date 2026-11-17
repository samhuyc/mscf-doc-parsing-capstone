"""Run one local recognizer on a crop and export native confidence + quality.

Example: work/extra-env/bin/python prototype/predict_crop.py --image crop.png
Uses the same checkpoints, prompts and passive score capture as evaluation.
"""
import argparse
from pathlib import Path
import subprocess
from PIL import Image
from common import ROOT,RUN,RESULTS,read,write,sha
from score import score_record as legacy_score
from score_round2 import score_record,load_frozen

def main():
 p=argparse.ArgumentParser();p.add_argument('--image',type=Path,required=True);p.add_argument('--engine',default='glm',choices=['paddle_vl','glm','monkey','mineru','mineru_table']);a=p.parse_args()
 image=a.image.resolve()
 with Image.open(image) as im:im.verify()
 source_sha=sha(image);root=RUN/'demo'/a.engine/source_sha[:16];root.mkdir(parents=True,exist_ok=True)
 crop=root/'input.png'
 if not crop.exists():
  with Image.open(image) as im:im.convert('RGB').save(crop)
 tid='local_crop_'+source_sha[:16]
 manifest=dict(settings=dict(source_kind='user_provided_table_crop',source_file_sha256=source_sha,recognition='Unchanged evaluated adapter'),pages=[],tables=[dict(table_id=tid,document='local_crop',page=1,image='input.png',image_sha256=sha(crop),source_sha256=source_sha,models={})])
 if (root/'tables.json').exists() and read(root/'tables.json')!=manifest:raise RuntimeError('Existing crop manifest differs')
 write(root/'tables.json',manifest)
 subprocess.run([str(ROOT/'work/extra-env/bin/python'),str(ROOT/'prototype/run_batch.py'),'--root',str(root),'--engines',a.engine],cwd=ROOT,check=True)
 record=root/(a.engine if a.engine.startswith('mineru') else 'extra/'+a.engine)/(tid+'.json')
 frozen=read(RESULTS/'calibrators_frozen.json') if (RESULTS/'calibrators_frozen.json').exists() else {}
 if frozen and frozen['code_sha256']['native_evidence.py']!=sha(ROOT/'prototype/native_evidence.py'):raise RuntimeError('Native feature version differs from calibration')
 result=score_record(read(record),a.engine,load_frozen()) if a.engine in ('paddle_vl','glm','monkey','mineru_table') else legacy_score(read(record),a.engine,frozen)
 write(root/'confidence.json',result)
 print('Saved:',root/'confidence.json')
 print('Native numeric:',result['native']['native_numeric'],'Review priority:',result['review_priority'])
 for q in result['quality_estimates']:print(q['target'],'expected score:',q['expected_score'])
if __name__=='__main__':main()
