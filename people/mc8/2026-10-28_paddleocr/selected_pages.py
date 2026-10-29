"""Finish all unchanged 54-label checks, reusing every complete page prediction."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from common import ROOT,PARSER,dump,environment
from paddle_worker import config
from run import code_hashes
from selected_support import atomic_dump,checkpoints,export_sparse,sha


def selected_code_hashes():
    return {name:sha(ROOT/name) for name in ('selected_pages.py','selected_worker.py','selected_support.py')}


def plan():
    labels=[json.loads(line) for line in (ROOT/'labels.jsonl').read_text().splitlines() if line.strip()]
    sources=json.loads((ROOT/'source_manifest.json').read_text())
    result=[]
    for source in sources:
        work=ROOT/'results/parsed'/source['id']/PARSER
        wanted=sorted({l['page'] for l in labels if l['document']==source['id']})
        completed=checkpoints(work)
        result.append(dict(document=source['id'],source_pages=source['pages'],requested_pages=wanted,
                    completed_pages=sorted(completed),remaining_pages=[i for i in wanted if i not in completed]))
    return result


def execute(source,entry):
    work=ROOT/'results/parsed'/source['id']/PARSER
    pdf=ROOT/'inputs'/(source['id']+'.pdf')
    if sha(pdf)!=source['sha256']:
        raise ValueError('Source PDF hash changed')
    prior=json.loads((work/'run.json').read_text()) if (work/'run.json').is_file() else {}
    if prior and prior.get('code_sha256')!=code_hashes():
        raise ValueError('Original inference code changed')
    if prior.get('status') in {'success','partial','empty'} and not entry['remaining_pages']:
        if prior['document_sha256']!=sha(work/'document.md'):
            raise ValueError('Completed document changed')
        if prior['settings']!=dict(config(),render_dpi=300,markdown_ignore_labels=[]):
            raise ValueError('Completed run settings differ')
        print('Reusing all completed outputs:',source['id'],flush=True)
        return
    work.mkdir(parents=True,exist_ok=True)
    if prior and not (work/'run_before_selected.json').exists():
        shutil.copy2(work/'run.json',work/'run_before_selected.json')
    record=dict(prior)
    record.update(parser=PARSER,document=source['id'],input_sha256=source['sha256'],expected_pages=source['pages'],
        status='started',scope='selected_evaluation_pages',requested_pages=entry['requested_pages'],
        reused_pages=entry['completed_pages'],new_pages=entry['remaining_pages'],
        code_sha256=code_hashes(),selected_code_sha256=selected_code_hashes(),hosted_model_calls=0,
        weights_precached=True,model_sources_sha256=sha(ROOT/'model_sources.json'),
        selected_started_at_utc=datetime.now(timezone.utc).isoformat(),
        timing_note='Resumed selected evaluation pages. Preserves previous page predictions. Full-document runtime is incomplete and not comparable.')
    record.pop('error',None)
    atomic_dump(work/'run.json',record)
    started=time.perf_counter()
    if entry['remaining_pages']:
        command=[sys.executable,str(ROOT/'selected_worker.py'),str(pdf),str(work),'--pages',*map(str,entry['requested_pages'])]
        with (work/'selected_parser.log').open('a') as log:
            result=subprocess.run(command,cwd=ROOT,env=environment(),stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:
            record.update(status='interrupted',error=f'Selected worker exited {result.returncode}; complete page checkpoints retained')
            atomic_dump(work/'run.json',record)
            raise RuntimeError(record['error'])
    worker=json.loads((work/'selected_worker.json').read_text())
    if worker['settings']!=dict(config(),render_dpi=300,markdown_ignore_labels=[]):
        raise ValueError('Selected worker configuration changed')
    completed=checkpoints(work)
    if not set(entry['requested_pages'])<=set(completed):
        raise ValueError('Requested evaluation pages are missing')
    pages=export_sparse(work,completed,source)
    nonempty=sum(p['text_chars']>0 for p in pages)
    record.update(status='success' if nonempty==len(pages) else ('partial' if nonempty else 'empty'),
        parsed_pages=len(pages),nonempty_pages=nonempty,ocr_pages=sorted(completed),
        selected_pages_complete=True,unprocessed_pages=[i for i in range(1,source['pages']+1) if i not in completed],
        settings=worker['settings'],versions=worker['versions'],model_files_sha256=worker['model_files_sha256'],
        selected_elapsed_seconds=round(time.perf_counter()-started,3),
        elapsed_seconds=round(sum(x['audit']['elapsed_seconds'] for x in completed.values()),3),
        pages_per_second=None,full_document_runtime_comparable=False,document_sha256=sha(work/'document.md'))
    atomic_dump(work/'run.json',record)
    print(source['id'],'evaluation pages complete; retained',sorted(completed),flush=True)


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--plan-only',action='store_true')
    args=cli.parse_args()
    entries=plan()
    dump(ROOT/'results/selected_plan.json',dict(labels=54,selected_pages=18,
         source_sha256=sha(ROOT/'labels.jsonl'),documents=entries,
         remaining_pages=sum(len(e['remaining_pages']) for e in entries)))
    print(json.dumps(entries,indent=2),flush=True)
    if args.plan_only:
        return
    sources={s['id']:s for s in json.loads((ROOT/'source_manifest.json').read_text())}
    for entry in entries:
        execute(sources[entry['document']],entry)
        dump(ROOT/'results/selected_progress.json',plan())
    dump(ROOT/'results/selected_completion.json',dict(status='success',labels=54,selected_pages=18,
         all_selected_pages_complete=all(not x['remaining_pages'] for x in plan()),documents=plan(),
         non_evaluation_pages_skipped=True,original_trial_and_dataset_runs_deferred=True))


if __name__=='__main__':
    main()
