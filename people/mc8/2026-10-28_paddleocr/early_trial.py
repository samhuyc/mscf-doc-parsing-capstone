"""Reproduce the original September 9 full-PDF trial with PaddleOCR."""
import argparse
import json

from common import ROOT, PARSER, dump
from prepare import fetch, sha
from run import run

SOURCES = [
    dict(id='lamray_2012', title='Lamray Holdings Limited 2012 annual report', pages=23,
         url='https://find-and-update.company-information.service.gov.uk/company/01415057/filing-history/MzA4MTc5NTUwNGFkaXF6a2N4/document?format=pdf&download=0', sample_pages=[4,8,9,16]),
    dict(id='apple_2026q3', title='Apple Inc. Form 10-Q, quarter ended June 27, 2026', pages=32,
         url='https://d18rn0p25nwr6d.cloudfront.net/CIK-0000320193/e0dac020-713e-47ce-809a-f58dd78dfa91.pdf', sample_pages=[4,6,10,24]),
]


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--prepare-only',action='store_true')
    cli.add_argument('--skip-existing',action='store_true')
    args=cli.parse_args()
    import pymupdf
    manifest=ROOT/'early/source_manifest.json'
    prior={s['id']:s.get('sha256') for s in json.loads(manifest.read_text())} if manifest.is_file() else {}
    records=[]
    for source in SOURCES:
        source=dict(source)
        try:
            path=fetch(source['url'],ROOT/'early/inputs'/(source['id']+'.pdf'),prior.get(source['id']))
            with pymupdf.open(path) as pdf:
                if len(pdf)!=source['pages']:
                    raise ValueError('Original trial PDF page count differs')
                source.update(sha256=sha(path),outline=pdf.get_toc(),metadata=pdf.metadata)
            source.update(status='success',identity_note='Original trial records URLs and page counts, but no original PDF hashes were committed. Current downloaded hash recorded here.')
            if not args.prepare_only:
                record=run(source,path,ROOT/'early/results'/source['id']/PARSER,args.skip_existing)
                source['run_status']=record['status']
        except Exception as exc:
            source.update(status='failed',error=repr(exc))
        records.append(source)
        dump(ROOT/'early/source_manifest.json',records)
        print(source['id'],source['status'],source.get('run_status',source.get('error','prepared')),flush=True)
    if any(r['status']=='failed' for r in records):
        raise SystemExit(1)


if __name__=='__main__':
    main()
