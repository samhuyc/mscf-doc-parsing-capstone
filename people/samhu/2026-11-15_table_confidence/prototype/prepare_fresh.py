"""Freeze public table inputs after visual layout review, before inference."""
from copy import deepcopy
from PIL import Image
from common import ROOT,RUN,read,write,sha

def main():
 source=RUN/'fresh_layout';out=RUN/'fresh_public';out.mkdir(parents=True,exist_ok=True)
 bundle=read(source/'tables.json');tables=[]
 for t in bundle['tables']:
  t=deepcopy(t);t['image']=str((source/t['image']).resolve());t['issuer']=t['document'].split('_')[0]
  corrections={'unilever_fy2025_release_p014_t02':[69,1685,1572,2039],'unilever_fy2025_release_p020_t01':[67,149,1574,1610]}
  if t['table_id'] in corrections:
   t['original_bbox_px']=t['bbox_px'];t['bbox_px']=corrections[t['table_id']]
   page=source/f"{t['document']}_p{t['page']:03d}.png"
   crop=Image.open(page).convert('RGB').crop(t['bbox_px']);image=out/(t['table_id']+'.png');crop.save(image)
   t['image']=image.name;t['image_sha256']=sha(image);t['preprocessing']='Visual boundary repair before inference'
  tables.append(t)
 # One visually confirmed complete miss by the shared detector.
 tid='harrods_fy2025_accounts_p026_cash_flow';box=[200,430,1460,2000]
 image=Image.open(source/'harrods_fy2025_accounts_p026.png').convert('RGB').crop(box);image.save(out/(tid+'.png'))
 pdf=ROOT/'work/public_source_samples/harrods_fy2025_accounts.pdf'
 tables.append(dict(table_id=tid,document='harrods_fy2025_accounts',page=26,issuer='harrods',image=tid+'.png',image_sha256=sha(out/(tid+'.png')),source_sha256=sha(pdf),bbox_px=box,layout_score=None,models={},preprocessing='Manual recovery of a visually verified detector miss'))
 settings=deepcopy(bundle['settings']);settings.update(phase='Frozen fresh public inputs before recognition',manual_recoveries=1)
 write(out/'tables.json',dict(settings=settings,pages=bundle['pages'],tables=tables))
 write(out/'layout_audit.json',dict(pages_inspected=16,table_pages=15,non_table_pages=1,detected_candidates=16,manual_recoveries=[tid],
  observations=['Unilever p8 groups two financial subtables in one candidate.','Harrods p26 cash flow was entirely missed.','Dyson p36 is narrative; zero detections is correct.'],
  scope='Targeted source inspection; not a representative layout-recall benchmark.'))
 print('Frozen',len(tables),'fresh public table crops across four issuers.')
if __name__=='__main__':main()
