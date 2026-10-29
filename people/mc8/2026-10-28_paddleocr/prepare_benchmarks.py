"""Reproduce Sam's fixed eight-page dataset selections, never silently resample."""
import argparse
import json
from pathlib import Path
import shutil
import traceback

from common import ROOT, REFERENCE, dump, load
from prepare import fetch, sha

BENCH = ROOT/'benchmarks'


def verify_selection(dataset):
    filename = 'pilot_selection.json' if dataset == 'omni' else 'fin_selection.json'
    expected = json.loads((REFERENCE/'2026-09-20_evaluation'/filename).read_text())
    actual = json.loads((BENCH/filename).read_text())
    if actual['samples'] != expected['samples']:
        raise AssertionError(f'{dataset}: selection IDs or source/annotation hashes differ from Sam')
    upstream_hash='annotation_file_sha256' if dataset=='omni' else 'source_csv_sha256'
    if actual[upstream_hash]!=expected[upstream_hash]:
        raise AssertionError(f'{dataset}: complete upstream annotation/CSV checksum differs from Sam')
    return len(actual['samples'])


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--dataset', choices=['all','omni','fin'], default='all')
    cli.add_argument('--fin-folder', type=Path)
    args = cli.parse_args()
    BENCH.mkdir(exist_ok=True)
    prep = load('sam_prepare', REFERENCE/'2026-09-20_evaluation/prepare.py')
    prep.ROOT = BENCH
    records = json.loads((BENCH/'preparation.json').read_text()) if (BENCH/'preparation.json').exists() else {}
    for dataset in ['omni','fin']:
        if args.dataset not in {'all',dataset}:
            continue
        if dataset=='fin' and args.dataset=='all' and not args.fin_folder and records.get('fin',{}).get('status')=='blocked':
            print('fin: existing gated-input blocker retained; supply --fin-folder or explicitly retry --dataset fin',flush=True)
            continue
        try:
            existing=BENCH/'data'/dataset/'inputs.jsonl'
            references=BENCH/'data'/dataset/'references.jsonl'
            if records.get(dataset,{}).get('status')=='success' and existing.is_file() and references.is_file():
                count=verify_selection(dataset)
                for sample in [json.loads(s) for s in existing.read_text().splitlines() if s.strip()]:
                    for kind in ['image','image_pdf']:
                        if sha(BENCH/sample[kind])!=sample[kind+'_sha256']:
                            raise ValueError(f'Prepared {kind} changed: {sample["id"]}')
                print(dataset,'reusing',count,'hash-verified prepared image/PDF pairs',flush=True)
                continue
            if dataset == 'omni':
                prep.prepare_omni(8)
            else:
                folder = args.fin_folder
                if not folder:
                    # The pinned release requires an approved Hugging Face account.
                    # Use the recorded revision and normal hub authentication, if already configured.
                    from huggingface_hub import hf_hub_download
                    expected = json.loads((REFERENCE/'2026-09-20_evaluation/fin_selection.json').read_text())
                    folder = BENCH/'data/upstream/FinCriticalED'
                    paths = ['raw_input.csv'] + [f'gold_annotation_html/gold_{s["source_id"]}.txt' for s in expected['samples']]
                    for name in paths:
                        hf_hub_download(repo_id='TheFinAI/FinCriticalED', repo_type='dataset',
                                        revision=expected['revision'], filename=name, local_dir=folder)
                prep.prepare_fin(folder,8)
            records[dataset] = dict(status='success', pages=verify_selection(dataset))
        except Exception as exc:
            traceback.print_exc()
            records[dataset] = dict(status='blocked', error=repr(exc))
        dump(BENCH/'preparation.json', records)
        print(dataset,records[dataset],flush=True)
    from controls import main as check_input_layers
    check_input_layers()


if __name__ == '__main__':
    main()
