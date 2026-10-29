"""Same image-PDF inputs and unchanged September 20 page-level scorer."""
import argparse
import json
from pathlib import Path

from common import ROOT, REFERENCE, PARSER, dump, load
from formats import digest, read_jsonl, write_jsonl
from run import run

BENCH = ROOT/'benchmarks'


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--dataset', choices=['all','omni','fin'], default='all')
    cli.add_argument('--skip-existing', action='store_true')
    args = cli.parse_args()
    statuses = json.loads((BENCH/'preparation.json').read_text())
    for dataset in ['omni','fin']:
        if args.dataset not in {'all',dataset} or statuses.get(dataset,{}).get('status') != 'success':
            continue
        manifest = BENCH/'data'/dataset/'inputs.jsonl'
        destination = BENCH/'results'/dataset
        destination.mkdir(parents=True,exist_ok=True)
        records = []
        for sample in read_jsonl(manifest):
            pdf = BENCH/sample['image_pdf']
            work = destination/sample['id']
            source = dict(id=sample['id'],sha256=digest(pdf),pages=1,outline=[],
                          image_sha256=sample['image_sha256'],origin='published page image wrapped in PDF without text')
            try:
                record = run(source,pdf,work,args.skip_existing)
                status = record['status']
                prediction = dict(id=sample['id'],status=status,input_kind='image_pdf',
                                  input_sha256=source['sha256'],elapsed_seconds=record['elapsed_seconds'],
                                  markdown=str((work/'document.md').relative_to(BENCH)))
            except Exception as exc:
                prediction = dict(id=sample['id'],status='failed',input_kind='image_pdf',error=repr(exc),elapsed_seconds=None)
            records.append(prediction)
            write_jsonl(destination/'predictions.jsonl',records)
        dump(destination/'run.json',dict(parser=PARSER,input_kind='image_pdf',manifest_sha256=digest(manifest),
                                       samples=len(records),note='Same fixed images and unchanged Sam scorer; all failures retained.'))
        score = load('sam_page_score',REFERENCE/'2026-09-20_evaluation/score.py')
        score.ROOT = BENCH
        result = score.evaluate(manifest,BENCH/'data'/dataset/'references.jsonl',destination/'predictions.jsonl')
        dump(BENCH/'results'/f'{dataset}_paddleocr.json',result)
        print(json.dumps(result['summary'],indent=2),flush=True)


if __name__ == '__main__':
    main()
