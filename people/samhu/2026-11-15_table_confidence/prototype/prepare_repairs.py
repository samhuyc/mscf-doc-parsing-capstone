"""Source-coordinate repairs; originals and human reviews are never rewritten."""
from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
from PIL import Image
from common import ROOT, OLD, RUN, read, write, sha, issuer
from core import SPONSOR

# Coordinates fixed after viewing original pages rendered at 200 dpi.
# Pixel-only shared-header reuse is explicit; no generated text is added.
REPAIRS = [
 ('hippodrome_2025_p030_t01', 'hippodrome_2025_p030_employees', [[220,550,1495,834]], 0),
 ('hippodrome_2025_p030_t01', 'hippodrome_2025_p030_staff_costs', [[220,900,1495,1192]], 1),
 ('hippodrome_2025_p030_t01', 'hippodrome_2025_p030_directors', [[220,1260,1495,1528]], 2),
 ('peterborough_2025_p009_t01', 'peterborough_2025_p009_debtors', [[180,446,1540,787]], 0),
 ('rolls_royce_2026h1_release_p025_t02', 'rolls_royce_2026h1_release_p025_2025_segments', [[82,487,1575,600],[82,954,1575,1288]], 0),
]

def main():
    old=read(OLD/'tables.json'); refs=read(ROOT/'assistant_table_review.json')['reviews']
    inventory={t['table_id']:t for t in old['tables']}
    out=RUN/'repairs';out.mkdir(parents=True,exist_ok=True)
    tables=[]; annotations={}; pages=[]
    with tempfile.TemporaryDirectory() as temp:
        rendered={}
        for old_id,tid,boxes,ref_index in REPAIRS:
            original=inventory[old_id]; doc,page=original['document'],original['page']
            key=(doc,page); pdf=SPONSOR/'inputs'/(doc+'.pdf')
            assert sha(pdf)==original['source_sha256']
            if key not in rendered:
                prefix=Path(temp)/f'{doc}_{page}'
                result=subprocess.run(['pdftoppm','-f',str(page),'-l',str(page),'-r','200','-singlefile','-png',str(pdf),str(prefix)],capture_output=True,check=True)
                rendered[key]=Image.open(str(prefix)+'.png').convert('RGB')
                (out/f'{doc}_{page}_render.log').write_bytes(result.stderr)
                preview=rendered[key].copy();preview.thumbnail((1200,1600));preview.save(out/f'{doc}_{page}_page.png')
                pages.append(dict(document=doc,page=page,status='success',overview=f'{doc}_{page}_page.png',source_sha256=sha(pdf)))
            parts=[rendered[key].crop(box) for box in boxes]
            image=Image.new('RGB',(max(p.width for p in parts),sum(p.height for p in parts)),'white')
            y=0
            for p in parts:image.paste(p,(0,y));y+=p.height
            image.save(out/(tid+'.png'))
            t=dict(table_id=tid,document=doc,page=page,source_sha256=sha(pdf),image=tid+'.png',
                   image_sha256=sha(out/(tid+'.png')),models={},parent_table_id=old_id,
                   bbox_px=boxes[0],source_boxes_px=boxes,render_dpi=200,
                   preprocessing='concatenate original shared header and target body pixels' if len(boxes)>1 else 'manual source-coordinate crop',
                   layout_score=None,financial_relevance='assistant_selected_financial_table')
            tables.append(t)
            ref=deepcopy(refs[old_id]['recovered_grids_from_full_page'][ref_index])
            annotations[tid]=dict(table_id=tid,grids=[ref],human_verified=False,
                                 reference_kind='assistant_source_checked',issuer=issuer(doc),
                                 image_sha256=t['image_sha256'],source_sha256=t['source_sha256'],
                                 context='Original source labels, periods and units are visible in this repaired input.')
    settings=dict(render_dpi=200,repair_version=1,selection=REPAIRS,original_bundle_sha256=sha(OLD/'tables.json'))
    bundle=dict(settings=settings,pages=pages,tables=tables)
    target=out/'tables.json'
    if target.exists() and read(target)!=bundle:raise ValueError('Repair inputs changed; use a new version')
    write(target,bundle);write(out/'references.json',annotations)
    write(RUN/'human_review_snapshot.json',dict(path=str(OLD/'review/financial_ground_truth.json'),sha256=sha(OLD/'review/financial_ground_truth.json')))
    print('Prepared',len(tables),'repaired inputs; original 19-crop run preserved.')

if __name__=='__main__':
    from pathlib import Path
    main()
