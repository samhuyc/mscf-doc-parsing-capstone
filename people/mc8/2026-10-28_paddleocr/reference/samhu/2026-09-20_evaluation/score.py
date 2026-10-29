"""Transparent page diagnostics, not official OmniDocBench/TEDS/FFA scores."""
import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean

from apted import APTED, Config
from rapidfuzz.distance import Levenshtein
from scipy.optimize import linear_sum_assignment

from formats import NUMBER, digest, normalize, numeric_counts, numbers, plain_text, read_jsonl, soup_for

ROOT = Path(__file__).resolve().parent
METRICS = ('text_similarity', 'numeric_precision', 'numeric_recall', 'numeric_f1',
           'table_structure', 'table_content', 'table_numeric_cell_f1',
           'critical_span_recall', 'critical_context_recall')


def prf(gold, predicted):
    matches = sum((gold & predicted).values())
    ng, np = sum(gold.values()), sum(predicted.values())
    # No target and no predictions is not evidence of successful extraction.
    if not ng and not np:
        return None, None, None
    precision = matches / np if np else 0.0
    recall = matches / ng if ng else None
    f1 = 2 * matches / (ng + np)
    return precision, recall, f1


class Node:
    def __init__(self, label, children=()):
        self.label, self.children = label, list(children)

    def size(self):
        return 1 + sum(c.size() for c in self.children)


class TreeCosts(Config):
    def rename(self, a, b):
        if a.label[:3] != b.label[:3]:
            return 1
        return Levenshtein.normalized_distance(a.label[3], b.label[3])


def table_tree(table, structure=False):
    rows = []
    for row in table.find_all('tr'):
        if row.find_parent('table') is not table:
            continue
        cells = []
        for cell in row.find_all(['td', 'th'], recursive=False):
            label = ('cell', int(cell.get('rowspan', 1)), int(cell.get('colspan', 1)),
                     '' if structure else normalize(cell.get_text(' ')))
            cells.append(Node(label))
        rows.append(Node(('row', 1, 1, ''), cells))
    return Node(('table', 1, 1, ''), rows)


def table_similarity(a, b, structure=False):
    a, b = table_tree(a, structure), table_tree(b, structure)
    def signature(node):
        return node.label, tuple(signature(c) for c in node.children)
    if signature(a) == signature(b):
        return 1.0
    distance = APTED(a, b, TreeCosts()).compute_edit_distance()
    return max(0.0, 1 - distance / max(a.size(), b.size()))


def numeric_cells(table):
    """Use logical grid anchors, retaining row/column identity and merged spans."""
    occupied, result = set(), Counter()
    rows = [r for r in table.find_all('tr') if r.find_parent('table') is table]
    for ri, row in enumerate(rows):
        ci = 0
        for cell in row.find_all(['td', 'th'], recursive=False):
            while (ri, ci) in occupied:
                ci += 1
            rs, cs = int(cell.get('rowspan', 1)), int(cell.get('colspan', 1))
            for value, count in numeric_counts(cell.get_text(' ')).items():
                result[(ri, ci, rs, cs, value)] += count
            occupied.update((r, c) for r in range(ri, ri + rs) for c in range(ci, ci + cs))
            ci += cs
    return result


def valid_table(table):
    if table.find('table') or not table.find('tr'):
        return False
    try:
        return all(1 <= int(c.get(k, 1)) <= 1000 for c in table.find_all(['td', 'th'])
                   for k in ('rowspan', 'colspan'))
    except (ValueError, TypeError):
        return False


def table_scores(gold_html, content):
    gold = [soup_for(h, 'html').find('table') for h in gold_html]
    if any(t is None or not valid_table(t) for t in gold):
        raise ValueError('Unsupported reference table; do not silently repair gold')
    soup = soup_for(content)
    predicted = [t for t in soup.find_all('table') if t.find_parent('table') is None]
    malformed = len(re.findall(r'<table\b', content, re.I)) != len(re.findall(r'</table\s*>', content, re.I))
    valid = [valid_table(t) and not malformed for t in predicted]
    flags = []
    if malformed or not all(valid):
        flags.append('malformed_or_nested_table')
    if '\\begin{tabular}' in content or '\\begin{array}' in content:
        flags.append('unsupported_latex_table')
    denominator = max(len(gold), len(predicted))
    if not denominator:
        return dict(table_structure=None, table_content=None, table_numeric_cell_f1=None), [], flags
    totals = Counter()
    details = []
    if gold and predicted:
        content_matrix = [[table_similarity(g, p) if valid[j] else 0.0
                           for j, p in enumerate(predicted)] for g in gold]
        rr, cc = linear_sum_assignment(content_matrix, maximize=True)
        for i, j in zip(rr, cc):
            i, j = int(i), int(j)
            structure = table_similarity(gold[i], predicted[j], True) if valid[j] else 0.0
            ng = numeric_cells(gold[i])
            np = numeric_cells(predicted[j]) if valid[j] else Counter()
            _, _, nf = prf(ng, np)
            totals['table_structure'] += structure
            totals['table_content'] += content_matrix[i][j]
            details.append(dict(gold_table=i, predicted_table=j, structure=structure,
                                content=content_matrix[i][j], numeric_cell_f1=nf,
                                numeric_expected=sum(ng.values()), numeric_observed=sum(np.values()),
                                numeric_matched=sum((ng & np).values())))
    # Micro F1 across tables. Unmatched and invalid tables contribute unmatched values.
    ng = sum(sum(numeric_cells(t).values()) for t in gold)
    np = sum(sum(numeric_cells(t).values()) if valid[j] else sum(numeric_counts(t.get_text(' ')).values())
             for j, t in enumerate(predicted))
    matched = sum(d['numeric_matched'] for d in details)
    scores = {k: totals[k] / denominator for k in ('table_structure', 'table_content')}
    scores['table_numeric_cell_f1'] = 2 * matched / (ng + np) if ng + np else None
    details.append(dict(gold_tables=len(gold), predicted_tables=len(predicted), matched_tables=len(details)))
    return scores, details, flags


def span_count(text, span):
    if NUMBER.fullmatch(span):
        return numbers(text).count(numbers(span)[0])
    return len(re.findall(r'(?<!\w)' + re.escape(span) + r'(?!\w|[.,]\d|%)', text)) if span else 0


def score_page(ref, content):
    expected = plain_text(ref['content'], ref['format'])
    actual = plain_text(content)
    if not expected:
        raise ValueError('Empty reference text')
    p, r, f = prf(numeric_counts(expected), numeric_counts(actual))
    result = dict(text_similarity=1 - Levenshtein.normalized_distance(expected, actual),
                  numeric_precision=p, numeric_recall=r, numeric_f1=f)
    missing = numeric_counts(expected) - numeric_counts(actual)
    extra = numeric_counts(actual) - numeric_counts(expected)
    details = dict(numeric_missing_count=sum(missing.values()), numeric_extra_count=sum(extra.values()),
                   numeric_missing_examples=dict(missing.most_common(10)),
                   numeric_extra_examples=dict(extra.most_common(10)))
    if ref.get('tables') is None:
        result.update(table_structure=None, table_content=None, table_numeric_cell_f1=None)
        flags = ['table_labels_unavailable']
    else:
        scores, details['table_matches'], flags = table_scores(ref['tables'], content)
        result.update(scores)
    groups = ref.get('fact_groups', [])
    facts = Counter(f['text'] for group in groups for f in group['facts'])
    if facts:
        total = sum(facts.values())
        matched = sum(min(count, span_count(actual, text)) for text, count in facts.items())
        # Strict full annotated context matching; measures preservation, not semantic entailment.
        available = {normalize(g['context']): span_count(actual, normalize(g['context'])) for g in groups}
        context_matched = 0
        for group in groups:
            context = normalize(group['context'])
            if available[context] > 0:
                context_matched += len(group['facts'])
                available[context] -= 1
        result.update(critical_span_recall=matched / total, critical_context_recall=context_matched / total)
        details['critical_fields'] = dict(expected=total, span_matched=matched, context_matched=context_matched)
    else:
        result.update(critical_span_recall=None, critical_context_recall=None)
    return result, details, flags


def evaluate(manifest, references, predictions):
    samples, refs, preds = read_jsonl(manifest), read_jsonl(references), read_jsonl(predictions)
    ids = {s['id'] for s in samples}
    refs, preds = {r['id']: r for r in refs}, {r['id']: r for r in preds}
    if set(refs) != ids or set(preds) - ids:
        raise ValueError('Reference IDs must equal inputs; predictions may not contain extra IDs')
    kinds = {p['input_kind'] for p in preds.values() if p.get('input_kind')}
    if len(kinds) > 1:
        raise ValueError('Evaluate different input kinds separately')
    rows = []
    for sample in samples:
        sid = sample['id']
        pred = preds.get(sid, {'status': 'missing'})
        content = ''
        if pred['status'] == 'success':
            kind = pred['input_kind']
            if pred.get('input_sha256') != sample.get(kind + '_sha256'):
                raise ValueError(f'Prediction input checksum mismatch: {sid}')
            content = (ROOT / pred['markdown']).read_text()
        metrics, details, flags = score_page(refs[sid], content)
        rows.append(dict(id=sid, dataset=sample['dataset'], input_kind=pred.get('input_kind', 'missing'),
                         status=pred['status'], elapsed_seconds=pred.get('elapsed_seconds'),
                         output_sha256=hashlib.sha256(content.encode()).hexdigest(),
                         metrics=metrics, details=details, flags=flags,
                         source_id=sample['source_id'], attributes=sample.get('attributes', {})))
    groups = {}
    for dataset in sorted({r['dataset'] for r in rows}):
        selected = [r for r in rows if r['dataset'] == dataset]
        metrics = {}
        for key in METRICS:
            values = [r['metrics'][key] for r in selected if r['metrics'][key] is not None]
            metrics[key] = dict(mean=mean(values) if values else None, scored_pages=len(values))
        timings = [r['elapsed_seconds'] for r in selected if r['elapsed_seconds'] is not None]
        groups[dataset] = dict(pages=len(selected), input_kind=next(iter(kinds), None),
            successful=sum(r['status'] == 'success' for r in selected), metrics=metrics,
            total_seconds=sum(timings) if timings else None)
    metadata_path = Path(predictions).parent / 'run.json'
    return dict(metric_version='prototype-1', note='Custom diagnostics; not official leaderboard metrics. Higher is better.',
                run=json.loads(metadata_path.read_text()) if metadata_path.exists() else None,
                provenance={k: digest(p) for k, p in [('inputs', manifest), ('references', references), ('predictions', predictions)]},
                summary=groups, pages=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('references')
    parser.add_argument('predictions')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    result = evaluate(args.manifest, args.references, args.predictions)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(result['summary'], indent=2))
