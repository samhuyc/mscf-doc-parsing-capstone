"""Cache native numeric/structure summaries with source and code hashes."""
import argparse
from pathlib import Path
from common import ROOT,OLD,RUN,RESULTS,read,write,sha,digest
from native_evidence import features

ENGINES=('paddle','tesseract','paddle_vl','glm','monkey','mineru','mineru_table')
def outputs(root,table):
 for e in ENGINES:
  if e in table.get('models',{}):yield e,table['models'][e]['crop'],dict(source_bundle_sha256=sha(root/'tables.json'))
  else:
   path=root/('baseline/'+e if e in ('paddle','tesseract') else e if e in ('mineru','mineru_table') else 'extra/'+e)/(table['table_id']+'.json')
   if path.exists():yield e,read(path),dict(record_sha256=sha(path))

def main():
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=OLD);p.add_argument('--selected-only',action='store_true');a=p.parse_args()
 root=a.root.resolve()
 if root.name=='fresh_public' and not (RESULTS/'calibrators_frozen.json').exists():raise RuntimeError('Freeze calibration before inspecting fresh native evidence')
 selected=set(read(ROOT/'assistant_table_review.json')['reviews'])
 dest=RUN/'evidence'/root.name;dest.mkdir(parents=True,exist_ok=True);audit=[]
 code=sha(ROOT/'prototype/native_evidence.py')
 for table in read(root/'tables.json')['tables']:
  if a.selected_only and table['table_id'] not in selected:continue
  for engine,result,identity in outputs(root,table):
   target=dest/engine/(table['table_id']+'.json');provenance=dict(**identity,code_sha256=code,image_sha256=table['image_sha256'])
   if result.get('status')!='success':continue
   if target.exists() and read(target).get('provenance')==provenance and read(target)['status']=='success':continue
   try:
    feature,alignment=features(result,engine)
    record=dict(status='success',engine=engine,table_id=table['table_id'],provenance=provenance,features=feature,aligned_units=alignment['units'])
   except Exception as exc:
    record=dict(status='failed',engine=engine,table_id=table['table_id'],provenance=provenance,error=f'{type(exc).__name__}: {exc}')
   write(target,record);audit.append({k:v for k,v in record.items() if k not in ('features','aligned_units')})
   print(engine,table['table_id'],record['status'],record.get('error',''),flush=True)
 write(dest/'last_audit.json',audit)

if __name__=='__main__':main()
