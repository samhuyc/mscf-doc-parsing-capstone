"""Retrospective native-confidence utility checks; no fitting or new inference."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path

NATIVE = Path(__file__).resolve().parents[1] / '2026-11-10_native_confidence'
def ranks(values):
    ordered = sorted(range(len(values)), key=lambda i: values[i])
    ranked = [0.0] * len(values)
    start = 0
    while start < len(values):
        end = start + 1
        while end < len(values) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        for i in ordered[start:end]:
            ranked[i] = (start + end - 1)/2 + 1
        start = end
    return ranked


def pearson(x, y):
    if len(x) != len(y):
        raise ValueError('Unaligned vectors')
    if len(x) < 3:
        return None
    a, b = sum(x)/len(x), sum(y)/len(y)
    denominator = math.sqrt(sum((v-a)**2 for v in x)*sum((v-b)**2 for v in y))
    return sum((v-a)*(w-b) for v,w in zip(x,y))/denominator if denominator else None

METRICS = ('character_weighted_mean', 'geometric_mean', 'p10', 'fraction_below_0_90')


def family(document):
    return 'rolls_royce' if document.startswith('rolls_royce_') else document


def score(row, metric):
    value = row['confidence'].get(metric)
    if value is None or not math.isfinite(value):
        return None
    return -value if metric == 'fraction_below_0_90' else value


def risk(rows):
    if not rows:
        return {'pages': 0, 'mean_page_error_proxy': None, 'micro_cer': None}
    return {'pages': len(rows),
            'mean_page_error_proxy': sum(1-r['character_accuracy_proxy'] for r in rows)/len(rows),
            'micro_cer': sum(r['edit_errors'] for r in rows)/sum(r['reference_characters'] for r in rows),
            'truncated_pages': sum(bool(r['truncated']) for r in rows)}


def selection(rows, metric, coverage):
    """Select by score alone, including every tie at the cutoff."""
    if not 0 < coverage <= 1:
        raise ValueError('Coverage must be in (0, 1]')
    scored = [r for r in rows if score(r, metric) is not None]
    if not scored:
        return {'requested_coverage': coverage, 'actual_coverage': 0, 'missing_scores': len(rows), **risk([])}
    ordered = sorted(scored, key=lambda r: score(r, metric), reverse=True)
    threshold = score(ordered[math.ceil(coverage*len(ordered))-1], metric)
    kept = [r for r in ordered if score(r, metric) >= threshold]
    return {'requested_coverage': coverage, 'actual_coverage': len(kept)/len(rows),
            'missing_scores': len(rows)-len(scored), 'oriented_score_threshold': threshold,
            **risk(kept)}


def correlation(rows, metric):
    scored = [r for r in rows if score(r, metric) is not None]
    return {'pages': len(scored), 'spearman': pearson(
        ranks([score(r, metric) for r in scored]),
        ranks([r['character_accuracy_proxy'] for r in scored]))}


def analyze(data):
    output = {}
    for engine in sorted({r['engine'] for r in data['rows']}):
        rows = [r for r in data['rows'] if r['engine'] == engine]
        subsets = {'all': rows, 'exclude_truncated': [r for r in rows if not r['truncated']]}
        for kind, key in [('document', lambda r: r['document']), ('family', lambda r: family(r['document']))]:
            for value in sorted({key(r) for r in rows}):
                subsets[f'omit_{kind}:{value}'] = [r for r in rows if key(r) != value]
        output[engine] = {
            'baseline': risk(rows),
            'sensitivity': {label: {m: correlation(items, m) for m in METRICS} for label, items in subsets.items()},
            'selection': {m: [selection(rows, m, c) for c in (.5, .8, 1)] for m in METRICS}}
    return output


def report(result):
    lines = ['# Does native confidence help select better pages?', '',
        'Retrospective diagnostic on the same 23 selected pages, four PDFs, three issuers. '
        'No new inference, verified labels, fitted calibration or held-out validation.', '',
        'Spearman compares higher confidence with better full-page text agreement. '
        'Leave-one-family-out below means deleting a family and recomputing the statistic; no model is trained.', '',
        '| Engine | Summary | All pages | Without truncated pages | Omit-one-family range |',
        '|---|---|---:|---:|---:|']
    fmt = lambda x: 'undefined' if x is None else f'{x:.3f}'
    for engine, item in result['engines'].items():
        for metric in METRICS:
            s = item['sensitivity']
            values = [v[metric]['spearman'] for k,v in s.items() if k.startswith('omit_family:') and v[metric]['spearman'] is not None]
            span = f'{min(values):.3f} to {max(values):.3f}' if values else 'undefined'
            lines.append(f"| {engine} | {metric} | {fmt(s['all'][metric]['spearman'])} | {fmt(s['exclude_truncated'][metric]['spearman'])} | {span} |")
    lines += ['', '## Selecting the most confident half', '',
        'Lower error is better. The baseline is keeping all pages (also the expected mean error of a uniformly random subset). '
        'Error is 1 − clipped text agreement, averaged per page. Micro CER in the JSON remains uncapped so repetition is visible. '
        'All ties at the threshold are included. The 50% target is rounded up; missing scores are excluded, never set to zero.', '',
        '| Engine | Summary | Pages retained | Selected mean error | All-page mean error | Selected micro CER |',
        '|---|---|---:|---:|---:|---:|']
    for engine, item in result['engines'].items():
        for metric, curve in item['selection'].items():
            v = curve[0]
            lines.append(f"| {engine} | {metric} | {v['pages']} | {fmt(v['mean_page_error_proxy'])} | {fmt(item['baseline']['mean_page_error_proxy'])} | {fmt(v['micro_cer'])} |")
    lines += ['', '## Interpretation limits', '',
        '- Embedded PDF text is unreviewed and reading order/markup can affect error.',
        '- Only three issuer families are represented; these sensitivity ranges are not confidence intervals.',
        '- Selection and truncation removal are diagnostics on already inspected data, not new test results.',
        '- The fraction-below-0.90 score is sign-reversed for ranking: fewer low-confidence units ranks higher.',
        '- No aggregation is selected as a winner here. A future evaluation must freeze its primary metric before inspecting new labels.',
        '- Native token certainty does not cover omitted text or validate page structure. A calibrated page score needs an explicit correctness target and separate families for fitting and testing.', '']
    return '\n'.join(lines)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=NATIVE/'results/v2/page_evaluation.json')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent/'results')
    args = parser.parse_args()
    source = args.input.read_bytes()
    result = {'source_sha256': hashlib.sha256(source).hexdigest(), 'source': os.path.relpath(args.input.resolve(), NATIVE.parent),
              'engines': analyze(json.loads(source))}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'diagnostics.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    (args.output/'REPORT.md').write_text(report(result))
    print(report(result))
