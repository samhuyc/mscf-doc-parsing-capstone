"""Freeze 2,000 source tables, including Sam's 71. No model execution."""
import argparse
from collections import Counter
from html import escape
import io
import hashlib
import random
import re
import urllib.parse
from common import HERE, SAM, LOCAL, DATA, config, read, write, sha, digest, sam_paths
from download_assets import get_json, download


def issuer_id(value):
    return re.sub('[^A-Z0-9]', '', value.upper())


def restore_html(row):
    cells=iter(row['cells'][0])
    def fill(match): return match.group(0)+escape(''.join(next(cells)['tokens']))
    html=re.sub(r'<td\b[^>]*>',fill,''.join(row['html_restored']))
    if next(cells,None) is not None: raise ValueError('Unconsumed reference cells')
    return '<table>'+html+'</table>'


def parquet_rows():
    import pyarrow.parquet as pq
    index=0
    paths=sorted((LOCAL/'parquet').glob('*.parquet'))
    if not paths: raise RuntimeError('Download the test Parquet split first')
    for path in paths:
        for batch in pq.ParquetFile(path).iter_batches(batch_size=32):
            for row in batch.to_pylist():
                yield index,row
                index+=1


def eligible(row):
    from PIL import Image
    if not (3<=row['rows']<=45 and 2<=row['cols']<=14 and row['rows']*row['cols']<=250): return False
    image=row['image']
    with Image.open(io.BytesIO(image['bytes'])) as im:
        if im.width<200 or im.height<80:return False
    text=' '.join(''.join(c['tokens']) for c in row['cells'][0])
    return len(re.findall(r'\d+',text))>=6


def main():
    p=argparse.ArgumentParser(description=__doc__);p.parse_args()
    cfg=config();target=cfg['tables']
    manifest=DATA/'tables.json'
    if manifest.exists():
        bundle=read(manifest)
        if bundle['settings']['config_sha256']!=sha(HERE/'config.json'):raise RuntimeError('Config changed; create a new dataset version')
        for t in bundle['tables']:
            if sha(DATA/t['image'])!=t['image_sha256']:raise ValueError(t['table_id'])
        print('Verified existing sealed',len(bundle['tables']),'table dataset; no resampling.')
        return
    original=read(SAM/'results/native_prototype/input_manifest.json')['tables']
    sam={t['source_filename']:t for t in original if t['cohort'] in ('benchmark','confirmatory')}
    if len(sam)!=71:raise ValueError('Expected exactly 71 original FinTabNet inputs')
    prior={issuer_id(t['issuer']) for t in original}
    # The sponsor/fresh reports use names while FinTabNet filenames use tickers.
    prior|={'CVS','EDF','RR','ROLLSROYCE','NSRGY','NESN','NESTLE','UL','ULVR','UNILEVER','HARRODS','DYSON','HIPPODROME','PETERBOROUGH'}
    candidates=[];found={}
    for index,row in parquet_rows():
        filename=row['filename'];family=issuer_id(filename.split('.')[0])
        is_sam=filename in sam
        if is_sam or eligible(row):
            item=dict(index=index,filename=filename,issuer=family,is_sam=is_sam)
            candidates.append(item)
            if is_sam:found[filename]=item
    if set(found)!=set(sam):raise ValueError('Original Sam filenames absent from this dataset revision')
    rng=random.Random(cfg['seed'])
    unseen=sorted({r['issuer'] for r in candidates}-prior);rng.shuffle(unseen)
    # Sam already used 45 of this split's 50 issuers. Reserve all five
    # remaining companies; report this limited independent-company count.
    test_issuers=set(unseen)
    old=sorted(found.values(),key=lambda r:r['index'])
    additional=[r for r in candidates if not r['is_sam']];rng.shuffle(additional)
    wanted_test=round(target*(1-cfg['dataset']['development_table_fraction']));selected=list(old);counts=Counter(r['issuer'] for r in selected)
    # Preserve all original samples, then cap additional issuer concentration.
    for split,wanted in [('test',wanted_test),('development',target-wanted_test-len(old))]:
        subset=[]
        for r in additional:
            if (r['issuer'] in test_issuers)!=(split=='test'):continue
            if counts[r['issuer']]>=cfg['dataset']['max_tables_per_issuer']:continue
            subset.append(r);counts[r['issuer']]+=1
            if len(subset)==wanted:break
        if len(subset)!=wanted:raise RuntimeError(f'Only {len(subset)} eligible {split} rows; requested {wanted}. Revise the explicit selection policy.')
        selected.extend(subset)
    selected.sort(key=lambda r:r['index'])
    wanted={r['index']:r for r in selected};tables=[];references={};sam_paths()
    from table_structure_v2 import parse_html
    for index,row in parquet_rows():
        if index not in wanted:continue
        item=wanted[index];tid=f'fintabnet_test_{index:05d}'
        from PIL import Image
        image_bytes=row['image']['bytes'];image_path=DATA/'images'/(tid+'.jpg')
        image_path.parent.mkdir(parents=True,exist_ok=True)
        raw_sha=hashlib.sha256(image_bytes).hexdigest()
        # The dataset viewer used by Sam emits JPEG quality 75 / 4:2:0.
        # Reproduce those bytes offline and apply the same encoding to all
        # new images, avoiding a JPEG-vs-PNG cohort confound and flaky API.
        encoded=io.BytesIO()
        with Image.open(io.BytesIO(image_bytes)) as im:im.convert('RGB').save(encoded,format='JPEG',quality=75,subsampling=2)
        image_path.write_bytes(encoded.getvalue())
        byte_source='pinned_parquet_jpeg75_viewer_encoding'
        if item['is_sam']:
            old_t=sam[item['filename']]
            if sha(image_path)!=old_t['image_sha256']:
                # Match the exact viewer-encoded bytes Sam saved, when different
                # from Parquet storage. Never silently substitute his input.
                url='https://datasets-server.huggingface.co/rows?'+urllib.parse.urlencode(dict(dataset=cfg['dataset']['repository'],config='default',split='test',offset=index,length=1))
                public=get_json(url)['rows'][0]['row']
                if public['filename']!=item['filename']:raise ValueError('Dataset row order changed')
                image_path.unlink()
                download(dict(path=str(image_path),url=public['image']['src'],sha256=old_t['image_sha256']))
                byte_source='sam_exact_viewer_encoding'
            else:byte_source='sam_exact_viewer_encoding_reproduced_jpeg75'
        stable={k:v for k,v in row.items() if k!='image'}
        if item['is_sam'] and digest(stable)!=sam[item['filename']]['source_sha256']:raise ValueError('Original Sam annotation changed')
        html=restore_html(row)
        table=dict(table_id=tid,document='fintabnet_'+row['filename'].split('.page')[0],page=1,
                   issuer=item['issuer'],image=str(image_path.relative_to(DATA)),image_sha256=sha(image_path),
                   parquet_image_sha256=raw_sha,image_byte_source=byte_source,source_sha256=digest(stable),
                   source_dataset=cfg['dataset']['repository'],source_row=index,source_filename=row['filename'],
                   split='test' if item['issuer'] in test_issuers else 'development',
                   sam_original=item['is_sam'],sam_original_table_id=sam[item['filename']]['table_id'] if item['is_sam'] else None,
                   models={},layout_score=None)
        tables.append(table)
        references[tid]=dict(table_id=tid,issuer=table['issuer'],grids=parse_html(html),html=html,
                             reference_kind='public_benchmark_annotation',human_verified=False,
                             image_sha256=table['image_sha256'],source_sha256=table['source_sha256'],
                             measurement_flags=['Sam flagged reference/header interpretation; retained, requires audit'] if tid in ('fintabnet_test_02146','fintabnet_test_09879') else [])
        write(DATA/'annotations'/(tid+'.json'),stable)
        if len(tables)%100==0:print('Prepared',len(tables),'/',target,flush=True)
    assert len(tables)==target and sum(t['sam_original'] for t in tables)==71
    dev={t['issuer'] for t in tables if t['split']=='development'}
    test={t['issuer'] for t in tables if t['split']=='test'}
    assert not dev&test and not prior&test
    settings=dict(config_sha256=sha(HERE/'config.json'),dataset=cfg['dataset'],seed=cfg['seed'],
                  selected_before_inference=True,raw_split='test',render_dpi=200,
                  selection='all Sam 71 + seeded geometry/numeric-filtered rows; max 100 total per issuer except mandatory originals; all five unseen issuers reserved for test',
                  reference_policy='Public labels, no independent human verification; no recognizer weights trained',
                  sources=read(LOCAL/'sources/docling-project--FinTabNet_OTSL.json')['sha'])
    write(DATA/'references.json',references)
    write(manifest,dict(settings=settings,pages=[],tables=tables))
    write(HERE/'cohort-summary.json',dict(total=len(tables),sam_original=71,additional=target-71,
          development=sum(t['split']=='development' for t in tables),test=sum(t['split']=='test' for t in tables),
          development_issuers=sorted(dev),test_issuers=sorted(test),issuer_overlap=[],
          tables_sha256=sha(manifest),references_sha256=sha(DATA/'references.json'),
          dataset_revision=settings['sources'],inference_run=False,
          source='data/fintabnet_2000/tables.json'))
    write(HERE/'sam-included-71.json',[{k:t[k] for k in ('table_id','source_filename','source_row','issuer','image_sha256','source_sha256','split')} for t in tables if t['sam_original']])
    write(DATA/'seal.json',dict(tables_sha256=sha(manifest),references_sha256=sha(DATA/'references.json'),
                              config_sha256=sha(HERE/'config.json'),inference_started=False))
    print('Sealed',target,'tables, including all Sam 71; no inference.',flush=True)


if __name__=='__main__':main()
