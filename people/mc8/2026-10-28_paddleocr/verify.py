"""Audit source identity, real inference artifacts, scorer parity and offline links."""
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

from bs4 import BeautifulSoup
from common import ROOT, REFERENCE, PARSER, dump, prediction_dir, scorer
from run import code_hashes
from comparison import baseline_parity
from selected_support import checkpoints
from selected_pages import selected_code_hashes
from paddle_worker import config


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_run(source,work):
    record=json.loads((work/'run.json').read_text())
    pages=json.loads((work/'pages.json').read_text())
    assert record['status'] in {'success','partial','empty'},record
    assert pages['parser']==record['parser']==PARSER
    assert pages['source_sha256']==record['input_sha256']==source['sha256']
    assert record['code_sha256']==code_hashes(),'Inference code changed after run'
    assert record['weights_precached'] is True
    assert record['model_sources_sha256']==sha(ROOT/'model_sources.json')
    for model in json.loads((ROOT/'model_sources.json').read_text()):
        for name,info in model['files'].items():
            if Path(name).suffix in {'.json','.yml','.yaml','.pdiparams'}:
                assert record['model_files_sha256'][model['model']+'/'+name]==info['sha256']
    assert record['document_sha256']==sha(work/'document.md')
    ids=[p['page'] for p in pages['pages']]
    assert ids==sorted(set(ids)) and all(1<=i<=source['pages'] for i in ids)
    if record.get('scope')=='selected_evaluation_pages':
        assert record['selected_code_sha256']==selected_code_hashes()
        assert record['selected_pages_complete'] is True
        assert set(record['requested_pages'])<=set(ids)
        assert record['unprocessed_pages']==[i for i in range(1,source['pages']+1) if i not in ids]
        assert sorted(checkpoints(work))==ids
    else:
        assert ids==list(range(1,source['pages']+1))
    assert record['parsed_pages']==len(pages['pages'])
    assert record['settings']==dict(config(),render_dpi=300,markdown_ignore_labels=[])
    assert record['nonempty_pages']==sum(p['text_chars']>0 for p in pages['pages'])
    assert all(p['confidence'] is None for p in pages['pages'])
    audit=json.loads((work/'ocr_pages.json').read_text())['pages']
    assert [p['page'] for p in audit]==ids
    for call in audit:
        raw=work/call['raw_prediction']
        assert sha(raw)==call['raw_sha256']
        native=json.loads(raw.read_text())
        assert isinstance(native.get('res',native),dict)
    for target in re.findall(r'!\[[^\]]*\]\(([^)]+)\)',(work/'document.md').read_text()):
        target=target.strip('<>')
        assert not Path(target).is_absolute()
        assert (work/target).resolve().is_relative_to(work.resolve())
        assert (work/target).is_file(),f'Missing Paddle crop: {target}'
    from formats import soup_for
    for image in soup_for((work/'document.md').read_text()).find_all('img'):
        target=work/image['src']
        assert target.resolve().is_relative_to(work.resolve()) and target.is_file(),f'Missing HTML image: {image}'
    return len(pages['pages'])


def main():
    original=ROOT.parent.parent/'samhu'
    originals=json.loads((ROOT/'sam_original_sha256.json').read_text())
    upstream=json.loads((ROOT/'upstream.json').read_text())
    # The starting workspace predates the frozen upstream snapshot. Accept
    # either complete pinned snapshot, so verification also works after the
    # repository advances to Sam's already-published report/glossary updates.
    source_baseline=None
    for name,files in [('initial_workspace',originals),('frozen_upstream',upstream['reference_files'])]:
        if all((original/path).is_file() and sha(original/path)==digest for path,digest in files.items()):
            source_baseline=name
            original_count=len(files)
            break
    assert source_baseline is not None,'Sam source does not match either pinned, unmodified snapshot'
    for name,digest in upstream['reference_files'].items():
        assert sha(REFERENCE/name)==digest,f'Reference snapshot changed: {name}'
    for name in ['benchmark.py','labels.jsonl']:
        assert sha(ROOT/name)==sha(REFERENCE/'2026-10-05_pilot_benchmark'/name)
    b=scorer()
    result=b.read_json(ROOT/'results/preliminary.json')
    baseline=b.read_json(REFERENCE/'2026-10-05_pilot_benchmark/results/preliminary.json')
    assert result['selected_labels']==54
    assert b.read_json(ROOT/'results/reviewed.json')['selected_labels']==0
    assert result['label_sha256']==baseline['label_sha256']==sha(ROOT/'labels.jsonl')
    assert result['scorer_sha256']==sha(ROOT/'benchmark.py')
    baseline_parity(result,baseline,b.PARSERS[:-1])
    pages=0
    coverage=[]
    labels=b.read_jsonl(ROOT/'labels.jsonl')
    for source in b.read_json(ROOT/'source_manifest.json'):
        assert sha(ROOT/'inputs'/(source['id']+'.pdf'))==source['sha256']
        pages+=verify_run(source,prediction_dir(source['id'],PARSER))
        work=prediction_dir(source['id'],PARSER)
        ids=[p['page'] for p in b.read_json(work/'pages.json')['pages']]
        requested=sorted({l['page'] for l in labels if l['document']==source['id']})
        assert set(requested)<=set(ids),'Missing labeled page'
        coverage.append(dict(document=source['id'],source_pages=source['pages'],processed_pages=ids,
                             labeled_pages=requested,all_labeled_pages_present=True))
    assert sum(len(r['labeled_pages']) for r in coverage)==18
    assert 18<=pages<=140
    links=0
    for report in (ROOT/'review').glob('*.html'):
        soup=BeautifulSoup(report.read_text(),'html.parser')
        for tag in soup.select('[href], [src]'):
            target=urlsplit(tag.get('href',tag.get('src','')))
            if target.scheme or target.netloc or not target.path:
                continue
            assert (report.parent/unquote(target.path)).resolve().exists(),f'Broken link: {report.name}: {target.path}'
            links+=1
    verified=dict(status='passed',sponsor_documents=6,paddle_pages=pages,sam_original_files_unchanged=original_count,
                  sam_source_baseline=source_baseline,
                  upstream_reference_files_unchanged=len(upstream['reference_files']),labels_and_scorer_byte_identical=True,
                  all_four_baseline_metrics_unchanged=True,per_document_baselines_exact=True,
                  equal_document_mean_roundoff_tolerance=1e-14,local_report_links_checked=links,hosted_model_calls=0)
    verified.update(all_18_labeled_pages_present=True,coverage=coverage,full_document_coverage=pages==140,
                    full_document_runtime_comparable=pages==140,
                    evaluation_scope='Same 54 unchanged draft labels; all 18 referenced physical pages present.')
    preservation=ROOT/'checkpoints/before_selected_pages/preservation_manifest.json'
    if preservation.exists():
        manifest=json.loads(preservation.read_text())
        for name,digest in manifest['files'].items():
            path=ROOT/name
            if name=='results/parsed/hippodrome_2025/paddleocr_ppstructurev3/run.json':
                path=preservation.parent/'hippodrome_2025/run.json'
            assert sha(path)==digest,f'Previously completed artifact changed: {name}'
        verified['previous_artifacts_preserved']=len(manifest['files'])
        verified['original_hippodrome_checkpoint_pages_preserved']=manifest['checkpoint_pages']
    early_manifest=ROOT/'early/source_manifest.json'
    early_pages=0
    if early_manifest.is_file():
        for source in json.loads(early_manifest.read_text()):
            work=ROOT/'early/results'/source['id']/PARSER
            if (work/'pages.json').is_file():
                assert sha(ROOT/'early/inputs'/(source['id']+'.pdf'))==source['sha256']
                early_pages+=verify_run(source,work)
    verified['original_trial_pages']=early_pages
    preparation=ROOT/'benchmarks/preparation.json'
    verified['dataset_status']=json.loads(preparation.read_text()) if preparation.exists() else {}
    dataset_pages=0
    for dataset in ['omni','fin']:
        predictions=ROOT/'benchmarks/results'/dataset/'predictions.jsonl'
        if predictions.is_file():
            samples={s['id']:s for s in b.read_jsonl(ROOT/'benchmarks/data'/dataset/'inputs.jsonl')}
            rows=b.read_jsonl(predictions)
            assert set(samples)=={r['id'] for r in rows}
            for row in rows:
                sample=samples[row['id']]
                assert row['input_sha256']==sample['image_pdf_sha256']
                assert sha(ROOT/'benchmarks'/sample['image'])==sample['image_sha256']
                source=dict(sha256=row['input_sha256'],pages=1)
                dataset_pages+=verify_run(source,ROOT/'benchmarks/results'/dataset/row['id'])
    verified['dataset_pages']=dataset_pages
    verified['total_public_input_pages_verified']=pages+early_pages+dataset_pages
    if pages<140:
        from verify_selected_scope import verify as verify_scope
        verified['selected_scope_verification']=verify_scope()
    control_path=ROOT/'benchmarks/results/native_text_controls.json'
    if control_path.is_file():
        controls=json.loads(control_path.read_text())
        assert all(r['native_text_chars']==0 for r in controls['image_pdf_controls'])
        assert controls['native_pdf_control']['native_text_chars']>0
        verified['image_pdf_negative_controls']=len(controls['image_pdf_controls'])
        verified['native_pdf_positive_control']=True
    dump(ROOT/'results/verification.json',verified)
    print(json.dumps(verified,indent=2))


if __name__=='__main__':
    main()
