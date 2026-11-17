"""Shared pinned layout detector on fresh digital and scanned public reports."""
import argparse
from pathlib import Path
import subprocess
from common import ROOT,RUN,read,write,sha,digest
from run_tables import environment,LAYOUT_NAME
from regions import deduplicate_tables,padded_box

SELECTION={'nestle_fy2025_presentation':[63,64,66,70],
           'unilever_fy2025_release':[5,8,14,20],
           'harrods_fy2025_accounts':[22,23,24,26],
           'dyson_2024_accounts':[28,29,30,36]}
def main():
 environment()
 import numpy as np
 from PIL import Image,ImageDraw
 from paddleocr import LayoutDetection
 out=RUN/'fresh_layout';out.mkdir(parents=True,exist_ok=True)
 model_dir=ROOT/'work/models'/LAYOUT_NAME;provenance=read(model_dir/'provenance.json')
 for name,entry in provenance['files'].items():assert sha(model_dir/name)==entry['sha256']
 model=LayoutDetection(model_name=LAYOUT_NAME,model_dir=str(model_dir),device='cpu',cpu_threads=4,enable_mkldnn=False)
 pages=[];tables=[]
 for doc,selected in SELECTION.items():
  pdf=ROOT/'work/public_source_samples'/(doc+'.pdf')
  for page in selected:
   page_id=f'{doc}_p{page:03d}';prefix=out/page_id
   if not prefix.with_suffix('.png').exists():subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-r','200','-singlefile','-png',str(pdf),str(prefix)],capture_output=True,check=True)
   image=Image.open(prefix.with_suffix('.png')).convert('RGB')
   cache=out/(page_id+'_layout.json')
   if cache.exists():raw=read(cache)
   else:
    prediction=list(model.predict(np.asarray(image)[:,:,::-1].copy(),batch_size=1,threshold=.5,layout_nms=True))[0].json
    raw=prediction.get('res',prediction);write(cache,raw)
   boxes,suppressed=deduplicate_tables([b for b in raw['boxes'] if b['label']=='table'])
   preview=image.copy();draw=ImageDraw.Draw(preview)
   for i,box in enumerate(boxes,1):
    tid=f'{page_id}_t{i:02d}';rect=padded_box(box['coordinate'],*image.size,.02);crop=image.crop(rect);crop.save(out/(tid+'.png'))
    draw.rectangle(rect,outline='#e4472e',width=4);draw.text((rect[0],max(0,rect[1]-26)),str(i),fill='#e4472e',font_size=22)
    tables.append(dict(table_id=tid,document=doc,page=page,image=tid+'.png',image_sha256=sha(out/(tid+'.png')),source_sha256=sha(pdf),bbox_px=rect,detector_bbox_px=box['coordinate'],layout_score=box['score'],models={}))
   preview.thumbnail((1400,1600));preview.save(out/(page_id+'_overview.png'))
   pages.append(dict(document=doc,page=page,source_sha256=sha(pdf),status='success',overview=page_id+'_overview.png',width=image.width,height=image.height,suppressed=suppressed))
   print(page_id,len(boxes),'tables',flush=True)
 write(out/'tables.json',dict(settings=dict(render_dpi=200,selection=SELECTION,layout=dict(name=LAYOUT_NAME,provenance=provenance)),pages=pages,tables=tables))
if __name__=='__main__':main()
