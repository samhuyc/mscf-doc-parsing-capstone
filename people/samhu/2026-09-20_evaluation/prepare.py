"""Prepare existing benchmark labels and separate model-visible input manifests."""
import argparse
import base64
import csv
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pymupdf

from formats import digest, fact_groups, write_jsonl

ROOT = Path(__file__).resolve().parent
OMNI_REV = 'aa1ee96d106dbe53d0ae59474d75c6e6d9b53fec'
FIN_REV = '2ac95f3dc2f0b55caf35f3d942bb5d32945f7c3e'


def fetch(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with urllib.request.urlopen(url, timeout=90) as response:
            path.write_bytes(response.read())
    return path


def image_pdf(image, pdf):
    with pymupdf.open(image) as image_doc:
        pdf.write_bytes(image_doc.convert_to_pdf())
    with pymupdf.open(pdf) as document:
        assert len(document) == 1 and not document[0].get_text().strip()


def input_record(sample_id, image, dataset, revision, attributes, source_id, page_no=None):
    pdf = image.with_suffix('.pdf')
    image_pdf(image, pdf)
    return dict(id=sample_id, dataset=dataset, revision=revision, source_id=source_id,
                upstream_page_no=page_no, attributes=attributes,
                image=str(image.relative_to(ROOT)), image_sha256=digest(image),
                image_pdf=str(pdf.relative_to(ROOT)), image_pdf_sha256=digest(pdf),
                input_origin='published_page_image', pdf_has_native_text=False)


def prepare_omni(count):
    url = f'https://huggingface.co/datasets/opendatalab/OmniDocBench/resolve/{OMNI_REV}/'
    source = fetch(url + 'OmniDocBench.json', ROOT / 'data/upstream/OmniDocBench.json')
    rows = json.loads(source.read_text())
    eligible = [r for r in rows if r['page_info']['page_attribute'].get('data_source') == 'research_report'
                and any(b['category_type'] == 'table' and b.get('html') and not b.get('ignore')
                        for b in r['layout_dets'])]
    # Coverage sample, selected without observing any parser output.
    eligible.sort(key=lambda r: hashlib.sha256(r['page_info']['image_path'].encode()).hexdigest())
    english = [r for r in eligible if r['page_info']['page_attribute']['language'] in ('english', 'en')]
    multi = [r for r in eligible if r['page_info']['page_attribute']['layout'] != 'single_column']
    hard = [r for r in eligible if r['page_info']['page_attribute'].get('subset') == 'table_hard']
    chosen, seen = [], set()
    for row in english[:1] + multi[:2] + hard[:3] + eligible:
        name = row['page_info']['image_path']
        group = re.sub(r'(?:_page_\d+|_\d+)\.(?:png|jpg)$', '', name)
        if group not in seen:
            chosen.append(row)
            seen.add(group)
        if len(chosen) >= count:
            break
    inputs, refs = [], []
    for row in chosen:
        page = row['page_info']
        name = Path(page['image_path']).name
        sid = 'omni_' + hashlib.sha256(name.encode()).hexdigest()[:12]
        image = fetch(url + 'images/' + urllib.parse.quote(name), ROOT / 'data/omni/images' / name)
        inputs.append(input_record(sid, image, 'omnidocbench', OMNI_REV,
                                   page['page_attribute'], name, page.get('page_no')))
        blocks = sorted([b for b in row['layout_dets'] if not b.get('ignore')],
                        key=lambda b: b.get('order') if isinstance(b.get('order'), (int, float)) else 99999)
        content = '\n\n'.join(b.get('html') or b.get('text') or b.get('latex') or '' for b in blocks)
        refs.append(dict(id=sid, content=content, format='markdown',
                         tables=[b['html'] for b in blocks if b['category_type'] == 'table' and b.get('html')],
                         fact_groups=[], annotation_sha256=hashlib.sha256(json.dumps(row, sort_keys=True).encode()).hexdigest(),
                         original=row))
    out = ROOT / 'data/omni'
    write_jsonl(out / 'inputs.jsonl', inputs)
    write_jsonl(out / 'references.jsonl', refs)
    selection = dict(dataset='opendatalab/OmniDocBench', revision=OMNI_REV,
                     annotation_file_sha256=digest(source), eligible_pages=len(eligible),
                     selection='sha256 filename ordering; English 1, multi-column 2, table_hard 3, then fill; deduplicate identifiable source names',
                     samples=[{k: r[k] for k in ('id', 'source_id', 'attributes', 'image_sha256')} for r in inputs])
    (ROOT / 'pilot_selection.json').write_text(json.dumps(selection, indent=2, ensure_ascii=False) + '\n')
    print(f'Prepared {len(inputs)} OmniDocBench pages in {out}')


def prepare_fin(folder, count):
    folder = Path(folder).expanduser().resolve()
    csv.field_size_limit(sys.maxsize)
    inputs, refs = [], []
    csv_hash = digest(folder / 'raw_input.csv')
    eligible = []
    for gold in (folder / 'gold_annotation_html').glob('gold_*.txt'):
        html = gold.read_text()
        if len(re.findall(r'<number\b', html, re.I)) >= 5:
            eligible.append(gold.stem.removeprefix('gold_'))
    eligible.sort(key=lambda sid: hashlib.sha256(sid.encode()).hexdigest())
    with (folder / 'raw_input.csv').open(newline='', encoding='utf-8-sig') as stream:
        available = {row['id'] for row in csv.DictReader(stream)}
    selected = set([sid for sid in eligible if sid in available][:count])
    metadata = folder / '.cache/huggingface/download/raw_input.csv.metadata'
    revision = metadata.read_text().splitlines()[0] if metadata.exists() else 'local-download'
    with (folder / 'raw_input.csv').open(newline='', encoding='utf-8-sig') as stream:
        for row in csv.DictReader(stream):
            source_id = str(row['id'])
            if source_id not in selected:
                continue
            if not source_id.isdigit():
                raise ValueError(f'Invalid FinCriticalED ID: {source_id}')
            gold = folder / 'gold_annotation_html' / f'gold_{source_id}.txt'
            if not gold.exists():
                raise FileNotFoundError(f'Missing reference: {gold}')
            html = gold.read_text()
            groups = fact_groups(html)
            if not groups:
                raise ValueError(f'No recognized critical-field annotations: {gold}')
            sid = f'fin_{source_id}'
            image = ROOT / 'data/fin/images' / f'{sid}.png'
            image.parent.mkdir(parents=True, exist_ok=True)
            encoded = row['image']
            if encoded.startswith('data:'):
                encoded = encoded.split(',', 1)[1]
            image.write_bytes(base64.b64decode(encoded))
            inputs.append(input_record(sid, image, 'fincriticaled', revision,
                                       {'language': 'english'}, source_id))
            refs.append(dict(id=sid, content=html, format='html', fact_groups=groups,
                             tables=None,  # SEC source HTML includes layout tables, not verified table gold.
                             source_csv_sha256=csv_hash,
                             annotation_sha256=digest(gold)))
            if len(inputs) >= count:
                break
    if not inputs:
        raise ValueError('No FinCriticalED samples found')
    write_jsonl(ROOT / 'data/fin/inputs.jsonl', inputs)
    write_jsonl(ROOT / 'data/fin/references.jsonl', refs)
    (ROOT / 'fin_selection.json').write_text(json.dumps(dict(
        dataset='TheFinAI/FinCriticalED', revision=revision, source_csv_sha256=csv_hash,
        selection='at least 5 existing number annotations; sha256 ID ordering; available release rows only',
        eligible_pages=len(set(eligible) & available),
        samples=[dict(id=r['id'], source_id=r['source_id'], image_sha256=r['image_sha256'],
                      annotation_sha256=ref['annotation_sha256']) for r, ref in zip(inputs, refs)]), indent=2) + '\n')
    print(f'Prepared {len(inputs)} FinCriticalED pages; coverage pilot, not a representative sample.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('dataset', choices=['omni', 'fin'])
    parser.add_argument('--count', type=int, default=8)
    parser.add_argument('--folder', help='Approved FinCriticalED download containing raw_input.csv and gold_annotation_html/')
    args = parser.parse_args()
    if args.count < 1 or (args.dataset == 'fin' and not args.folder):
        parser.error('Positive --count required; fin also requires --folder')
    if args.dataset == 'omni':
        prepare_omni(args.count)
    else:
        prepare_fin(args.folder, args.count)
