"""Re-score one saved prediction against its original, hash-checked reference."""
import argparse
import gzip
import json
import sys
import urllib.request
from pathlib import Path

from reproduce import HERE, rows
from score_prediction import filing_scores, table_scores, to_markup

PROTOTYPE = HERE.parents[2] / 'people/samhu/2026-11-15_table_confidence/prototype'
sys.path.insert(0, str(PROTOTYPE))
from download_benchmark import digest, parse_grids, restore_html


def financial_table_reference(sample, local_row):
    if local_row:
        annotation = json.loads(local_row.read_text(encoding='utf-8'))
    else:
        with urllib.request.urlopen(sample['source'], timeout=45) as response:
            record = json.load(response)['rows'][0]
        if record['truncated_cells']:
            raise ValueError('The upstream row is truncated. Supply the complete cached --annotation-json.')
        annotation = {k: v for k, v in record['row'].items() if k != 'image'}
    if digest(annotation) != sample['annotation_sha']:
        raise ValueError('The annotation differs from the version used in the benchmark.')
    markup = restore_html(annotation)
    return {'html': markup, 'grids': parse_grids(markup)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sample_id')
    parser.add_argument('model', choices=('paddle_vl','glm','monkey','mineru_vlm','pymupdf'))
    parser.add_argument('--annotation-json', type=Path, help='Cached FinTabNet test row without its image')
    args = parser.parse_args()
    base = HERE / 'evidence'
    inputs = {r['id']: r for r in rows(base, 'inputs.csv')}
    if args.sample_id not in inputs:
        parser.error('Look up a sample ID in evidence/inputs.csv.')
    sample = inputs[args.sample_id]
    with gzip.open(base/'predictions.jsonl.gz', 'rt', encoding='utf-8') as f:
        record = next((r for line in f if (r := json.loads(line))['id'] == args.sample_id and r['parser'] == args.model), None)
    if record is None:
        parser.error('No distributable raw output for this pair. See the evidence column in observations.csv.')
    raw = record['native_text']
    if sample['ds'] in ('ak', 'aq', 'uk'):
        result = filing_scores(sample['id'], raw)
    elif sample['ds'] in ('ft', 'hold', 'ukcrop'):
        if sample['ds'] == 'ukcrop':
            reference = json.loads((base/'uk_table_references.json').read_text())[sample['id']]
        else:
            reference = financial_table_reference(sample, args.annotation_json)
        prediction = to_markup(raw, 'markdown') if args.model in ('mineru_vlm','pymupdf') else raw
        result = table_scores(reference, prediction)
    else:
        parser.error('For FinCriticalED, use score_prediction.py page with the approved source files.')
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
