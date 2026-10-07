"""Offline sponsor pilot: explicit references, conservative matching, no LLM calls."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
from html import escape
import json
from pathlib import Path
import re
import time
import unicodedata

from bs4 import BeautifulSoup
from markdown_it import MarkdownIt
from rapidfuzz import fuzz
from rapidfuzz.distance import Levenshtein

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / '2026-09-29_sponsor_samples'
PARSERS = ('mineru_ocr', 'mineru_vlm', 'pymupdf4llm', 'pymupdf4llm_vlm')
MD = MarkdownIt('commonmark', {'html': True}).enable('table')
KINDS = {'table', 'text', 'reading_order', 'visual_fact', 'footnote', 'metadata'}
REVIEW_STATES = {'draft', 'human_verified', 'adjudicated', 'excluded'}
NUMBER = re.compile(r"(?<![\w.])(?:\(\s*)?[+−-]?\s*[$£€]?\s*[+−-]?\s*\d+(?:,\d{3})*(?:\.\d+)?\s*(?:%|bn|pts|p)?\s*\)?(?![\w.])")


def read_json(path):
    return json.loads(Path(path).read_text())


def read_jsonl(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def write_jsonl(path, values):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(v, ensure_ascii=False) + '\n' for v in values))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def norm(text):
    text = unicodedata.normalize('NFKC', str(text)).replace('−', '-').replace('’', "'")
    return re.sub(r'\s+', ' ', text).strip().casefold()


def contains(text, phrase):
    return bool(re.search(r'(?<!\w)' + re.escape(norm(phrase)) + r'(?!\w)', norm(text)))


def number_key(text):
    """UK/US pilot notation only. Blank != dash != zero; no scale inference."""
    s = norm(text).replace(' ', '')
    if not s:
        return ('blank',)
    if s in ('-', '–', '—'):
        return ('dash',)
    m = re.fullmatch(r'(\()?([+-]?)([$£€]?)([+-]?)(\d+(?:,\d{3})*(?:\.\d+)?)(%|bn|pts|p)?(\))?', s)
    if not m or bool(m[1]) != bool(m[7]):
        return ('text', s)
    try:
        value = Decimal(m[5].replace(',', ''))
    except InvalidOperation:
        return ('text', s)
    if m[1] or m[2] == '-' or m[4] == '-':
        value = -value
    return ('number', str(value.normalize()), m[3], m[6] or '')


def amount_key(text):
    key = number_key(text)
    return (key[0], key[1], key[3]) if key[0] == 'number' else key


def soup_for(markdown):
    soup = BeautifulSoup(MD.render(markdown), 'html.parser')
    for tag in soup(['script', 'style', 'head']):
        tag.decompose()
    return soup


def text_of(soup):
    # Images/alt text are not recognized numeric/text evidence.
    return ' '.join(soup.stripped_strings)


def table_grid(table):
    """Expand explicit spans, retaining origin cells. Never guess blank columns."""
    grid, origins = {}, []
    if table.find('table'):
        raise ValueError('nested_table')
    rows = [r for r in table.find_all('tr') if r.find_parent('table') is table]
    if len(rows) > 1000:
        raise ValueError('oversized_table')
    for r, row in enumerate(rows):
        c = 0
        for cell in row.find_all(['td', 'th'], recursive=False):
            while (r, c) in grid:
                c += 1
            rs, cs = int(cell.get('rowspan', 1)), int(cell.get('colspan', 1))
            if not (1 <= rs <= 100 and 1 <= cs <= 100) or r + rs > len(rows):
                raise ValueError('invalid_span')
            clean = BeautifulSoup(str(cell), 'html.parser')
            for sup in clean.find_all('sup'):
                sup.decompose()
            obj = dict(r=r, c=c, rowspan=rs, colspan=cs, text=clean.get_text(' ', strip=True),
                       raw_text=cell.get_text(' ', strip=True))
            origins.append(obj)
            for rr in range(r, r + rs):
                for cc in range(c, c + cs):
                    if (rr, cc) in grid:
                        raise ValueError('overlapping_span')
                    grid[(rr, cc)] = obj
            c += cs
    return dict(grid=grid, cells=origins, rows=len(rows))


def extract_tables(soup):
    result, errors = [], []
    for i, table in enumerate(soup.find_all('table')):
        try:
            result.append(dict(index=i, text=table.get_text(' ', strip=True), **table_grid(table)))
        except (ValueError, TypeError) as e:
            errors.append(dict(index=i, error=str(e)))
    return result, errors


def matches_label(text, label):
    return norm(text) == norm(label)


def header_matches(table, cell, path):
    """Each header must cover the value's column, in top-to-bottom order."""
    preceding = []
    for r in range(cell['r']):
        obj = table['grid'].get((r, cell['c']))
        if obj and obj not in preceding:
            preceding.append(obj)
    def header_text(value):
        s = norm(value)
        s = re.sub(r'\bhalf[- ]year to\s*', '', s)
        s = re.sub(r'[$£€]\s*(?:million|billion|m|bn)?', '', s)
        return s.strip()
    joined = ' | '.join(header_text(o['text']) for o in preceding)
    cursor = 0
    for index, header in enumerate(path):
        # Start at a cell boundary, then consume consecutive header components.
        # This prevents Domestic matching Non Domestic and Net matching Gross Net.
        prefix = r'(?:^|\|)\s*' if index == 0 else r'^[\s|]*'
        pattern = prefix + re.escape(header_text(header)) + r'(?!\w)'
        found = re.search(pattern, joined[cursor:])
        if found is None:
            return False
        cursor += found.end()
    # A percent-change column is not the absolute-change column with a cosmetic suffix.
    if '%' not in path[-1] and re.match(r'\s*%', joined[cursor:]):
        return False
    return True


def choose_table(tables, label):
    scores = []
    for table in tables:
        hits = sum(any(matches_label(c['text'], row['label']) for c in table['cells']) for row in label['rows'])
        if hits:
            scores.append((hits, table))
    if not scores:
        return None, 'missing_table_or_unmatched_labels'
    best = max(x[0] for x in scores)
    candidates = [t for n, t in scores if n == best]
    if len(candidates) != 1:
        return None, 'ambiguous_table_match'
    return candidates[0], None


def locate_cell(table, row_label, path):
    if table is None:
        return None, 'missing_table'
    row_cells = [c for c in table['cells'] if matches_label(c['text'], row_label)]
    candidates = []
    for rc in row_cells:
        for c in table['cells']:
            if c['r'] == rc['r'] and c['c'] >= rc['c'] + rc['colspan'] and header_matches(table, c, path):
                candidates.append(c)
    # Empty spacing cells without header coverage cannot displace a value. Empty cells
    # that DO share its header stay ambiguous; never delete them to force a match.
    unique = {(c['r'], c['c']): c for c in candidates}
    if len(unique) == 1:
        return next(iter(unique.values())), None
    return None, 'ambiguous_cell' if unique else 'missing_row_or_header'


def table_html(label):
    paths = [c['header_path'] for c in label['columns']]
    depth = max(map(len, paths))
    lines = ['<table>']
    for level in range(depth):
        lines.append('<tr>')
        if level == 0:
            lines.append(f'<th rowspan="{depth}"></th>')
        i = 0
        while i < len(paths):
            if level >= len(paths[i]):
                i += 1
                continue
            end = i + 1
            while end < len(paths) and paths[end][:level + 1] == paths[i][:level + 1]:
                end += 1
            rs = depth - level if level == len(paths[i]) - 1 else 1
            lines.append(f'<th colspan="{end-i}" rowspan="{rs}">{escape(paths[i][level])}</th>')
            i = end
        lines.append('</tr>')
    for row in label['rows']:
        lines.append('<tr><th>' + escape(row['label']) + '</th>' + ''.join('<td>' + escape(v) + '</td>' for v in row['values']) + '</tr>')
    lines.append('</table>')
    return '\n'.join(lines)


def validate(labels, sources):
    ids, docs = set(), {s['id']: s for s in sources}
    for x in labels:
        assert x['id'] not in ids, f"Duplicate label {x['id']}"
        ids.add(x['id'])
        assert x['document'] in docs and 1 <= x['page'] <= docs[x['document']]['pages']
        assert x['kind'] in KINDS and x['review_status'] in REVIEW_STATES
        assert x['source_sha256'] == docs[x['document']]['sha256']
        assert x['evidence']['region'] and x['importance'] in {'critical', 'supporting', 'cosmetic'}
        if x['review_status'] in {'human_verified', 'adjudicated'}:
            assert x.get('reviewer') and x.get('reviewed_at'), 'Human status requires reviewer and date'
        if x['kind'] == 'table':
            assert x['rows'] and x['columns']
            assert len({tuple(c['header_path']) for c in x['columns']}) == len(x['columns'])
            assert len({r['label'] for r in x['rows']}) == len(x['rows']), 'Disambiguate repeated row labels'
            for row in x['rows']:
                assert len(row['values']) == len(x['columns'])
            assert x['coverage'] in {'complete_data_matrix', 'selected_rows'}
        elif x['kind'] in {'text', 'footnote'}:
            assert x['text']
        elif x['kind'] == 'reading_order':
            assert x['before'] and x['after']
        elif x['kind'] == 'visual_fact':
            assert x['label'] and x['value'] and x['next_label']
        elif x['kind'] == 'metadata':
            assert x['field'] and x['value'] and x['evidence_text']
    return len(ids)


def prepare(render=False):
    import pymupdf
    sources = read_json(SOURCE / 'source_manifest.json')
    labels = read_jsonl(ROOT / 'labels.jsonl')
    validate(labels, sources)
    pages, documents = [], []
    (ROOT / 'reference_tables').mkdir(exist_ok=True)
    for source in sources:
        pdf_path = SOURCE / 'inputs' / (source['id'] + '.pdf')
        assert sha(pdf_path) == source['sha256'], f"Source changed: {source['id']}"
        doc_labels = [x for x in labels if x['document'] == source['id']]
        documents.append({k: source[k] for k in ('id', 'title', 'url', 'pages', 'sha256')})
        documents[-1]['source_pdf'] = str(pdf_path.relative_to(ROOT.parent))
        with pymupdf.open(pdf_path) as pdf:
            assert len(pdf) == source['pages']
            for p, page in enumerate(pdf, 1):
                selected = [x for x in doc_labels if x['page'] == p]
                pages.append(dict(document=source['id'], page=p, source_sha256=source['sha256'],
                                  width=page.rect.width, height=page.rect.height,
                                  embedded_text_chars=len(page.get_text().strip()),
                                  annotation_coverage='selected_regions' if selected else 'unannotated',
                                  label_ids=[x['id'] for x in selected],
                                  human_verified_labels=sum(x['review_status'] in {'human_verified', 'adjudicated'} for x in selected)))
                if selected and render:
                    out = ROOT / 'review' / 'assets' / f"{source['id']}_{p}.png"
                    out.parent.mkdir(parents=True, exist_ok=True)
                    page.get_pixmap(matrix=pymupdf.Matrix(1400/page.rect.width, 1400/page.rect.width)).save(out)
    write_json(ROOT / 'documents.json', documents)
    write_jsonl(ROOT / 'pages.jsonl', pages)
    return refresh_annotations()


def refresh_annotations():
    """Refresh references and review counts using the checked-in page inventory.

    No original PDFs are needed when teammates import review decisions.
    Use prepare --render to recheck source PDFs and regenerate previews.
    """
    documents = read_json(ROOT / 'documents.json')
    pages = read_jsonl(ROOT / 'pages.jsonl')
    labels = read_jsonl(ROOT / 'labels.jsonl')
    validate(labels, documents)
    by_page = defaultdict(list)
    for label in labels:
        by_page[(label['document'], label['page'])].append(label)
    for page in pages:
        selected = by_page[(page['document'], page['page'])]
        page.update(annotation_coverage='selected_regions' if selected else 'unannotated',
                    label_ids=[x['id'] for x in selected],
                    human_verified_labels=sum(x['review_status'] in {'human_verified', 'adjudicated'} for x in selected))
    (ROOT / 'reference_tables').mkdir(exist_ok=True)
    for label in labels:
        if label['kind'] == 'table':
            (ROOT / 'reference_tables' / (label['id'] + '.html')).write_text(table_html(label))
    write_jsonl(ROOT / 'pages.jsonl', pages)
    summary = dict(documents=len(documents), source_pages=len(pages), annotated_pages=sum(bool(p['label_ids']) for p in pages),
                   labels=len(labels), kinds=dict(Counter(x['kind'] for x in labels)),
                   review_status=dict(Counter(x['review_status'] for x in labels)),
                   table_facts=sum(len(x['rows'])*len(x['columns']) for x in labels if x['kind'] == 'table'),
                   hosted_model_calls=0, parser_reruns=0)
    write_json(ROOT / 'coverage.json', summary)
    return summary


def score_label(label, soup, tables):
    results = []
    text = text_of(soup)

    def add(metric, passed, detail=None, suffix=''):
        results.append(dict(label_id=label['id'] + suffix, metric=metric, passed=passed,
                            detail=detail, review_status=label['review_status'], importance=label['importance']))

    kind = label['kind']
    if kind == 'table':
        table, error = choose_table(tables, label)
        add('table_detected_by_row_labels', table is not None, error)
        for ri, row in enumerate(label['rows']):
            for ci, (expected, column) in enumerate(zip(row['values'], label['columns'])):
                suffix = f'/r{ri+1}/c{ci+1}'
                cell, reason = locate_cell(table, row['label'], column['header_path'])
                actual = cell['text'] if cell else None
                detail = dict(row=row['label'], header_path=column['header_path'], expected=expected, actual=actual, reason=reason)
                # Presence ignores associations intentionally; unique zero/blank counts are not inferred.
                if number_key(expected)[0] == 'number':
                    tokens = [m.group() for m in NUMBER.finditer(text)]
                    add('selected_value_presence', any(amount_key(t) == amount_key(expected) for t in tokens), detail, suffix)
                add('row_header_resolved', cell is not None, detail, suffix)
                add('associated_value_accuracy', cell is not None and amount_key(actual) == amount_key(expected), detail, suffix)
                add('display_form_accuracy', cell is not None and norm(actual) == norm(expected), detail, suffix)
                key = number_key(expected)
                if key[0] == 'number' and (key[2] or key[3]):
                    actual_key = number_key(actual) if cell else ()
                    add('inline_currency_unit_accuracy', len(actual_key) == 4 and actual_key[2:] == key[2:], detail, suffix)
                if number_key(expected)[0] == 'number' and Decimal(number_key(expected)[1]) < 0:
                    add('negative_value_accuracy', cell is not None and amount_key(actual) == amount_key(expected), detail, suffix)
        # Presence of declared unit text is a separate diagnostic, NOT unit-to-value accuracy.
        for i, unit in enumerate(label.get('unit_evidence', [])):
            add('unit_evidence_retention', contains(text, unit), dict(expected=unit), f'/unit{i}')
        for i, span in enumerate(label.get('header_spans', [])):
            ok = table is not None and any(matches_label(c['text'], span['text']) and c['colspan'] == span['colspan']
                                           and c['rowspan'] == span.get('rowspan', 1) for c in table['cells'])
            add('explicit_header_span_accuracy', ok, span, f'/span{i}')
        if label['coverage'] == 'complete_data_matrix':
            expected = Counter(amount_key(v) for row in label['rows'] for v in row['values'] if number_key(v)[0] == 'number')
            observed = Counter()
            if table:
                data_rows = [c['r'] for c in table['cells'] if any(matches_label(c['text'], row['label']) for row in label['rows'])]
                if data_rows:
                    for cell in table['cells']:
                        if cell['r'] >= min(data_rows) and number_key(cell['text'])[0] == 'number' and any(header_matches(table, cell, col['header_path']) for col in label['columns']):
                            observed[amount_key(cell['text'])] += 1
            common = sum((expected & observed).values())
            for metric, numerator, denominator in [('complete_matrix_numeric_precision',common,sum(observed.values())),
                                                    ('complete_matrix_numeric_recall',common,sum(expected.values()))]:
                results.append(dict(label_id=label['id'], metric=metric, numerator=numerator, denominator=denominator,
                                    review_status=label['review_status'], importance=label['importance'],
                                    detail='Numeric multiset within declared data columns; ignores association. Empty prediction precision is undefined.'))
    elif kind in {'text', 'footnote'}:
        exact = contains(text, label['text'])
        add('footnote_text_retention' if kind == 'footnote' else 'text_span_retention', exact)
        reference, prediction = norm(label['text']), norm(text)
        if prediction:
            alignment = fuzz.partial_ratio_alignment(reference, prediction)
            matched = prediction[alignment.dest_start:alignment.dest_end]
        else:
            matched = ''
        results.append(dict(label_id=label['id'], metric='matched_span_character_error_rate',
                            errors=Levenshtein.distance(reference, matched), reference_chars=len(reference),
                            matched_text=matched, review_status=label['review_status'], importance=label['importance']))
        if kind == 'footnote' and label.get('target'):
            add('footnote_target_association', None, 'Stored for review; co-occurrence does not prove attachment.')
    elif kind == 'reading_order':
        a, b = norm(label['before']), norm(label['after'])
        s = norm(text)
        pa = [m.start() for m in re.finditer(r'(?<!\w)' + re.escape(a) + r'(?!\w)', s)]
        pb = [m.start() for m in re.finditer(r'(?<!\w)' + re.escape(b) + r'(?!\w)', s)]
        unique = len(pa) == len(pb) == 1
        add('reading_order_accuracy', unique and pa[0] < pb[0], dict(before_positions=pa, after_positions=pb,
                                                                   reason=None if unique else 'missing_or_ambiguous_anchor'))
    elif kind == 'visual_fact':
        # Conservative sequence diagnostic. Never claim that textual proximity proves visual association.
        s, a, b = norm(text), norm(label['label']), norm(label['next_label'])
        starts = [m.end() for m in re.finditer(r'(?<!\w)' + re.escape(a) + r'(?!\w)', s)]
        actual = None
        if len(starts) == 1:
            end = s.find(b, starts[0])
            if end >= 0:
                region = s[starts[0]:min(end, starts[0]+label.get('max_chars', 120))]
                tokens = [m.group() for m in NUMBER.finditer(region)]
                # A plain superscript footnote digit may precede the value; do not discard numeric tokens.
                actual = tokens
        add('visual_value_presence', any(amount_key(m.group()) == amount_key(label['value']) for m in NUMBER.finditer(text)))
        add('visual_label_value_sequence', actual is not None and any(number_key(v) == number_key(label['value']) for v in actual),
            dict(expected=label['value'], tokens_between_labels=actual))
        add('visual_semantic_association', None, 'Source relationship labeled; human review or separately validated reader required.')
    elif kind == 'metadata':
        add('metadata_evidence_retention', contains(text, label['evidence_text']), dict(field=label['field'], expected=label['evidence_text']))
        add('metadata_field_accuracy', None, 'Existing metadata.json contains source-manifest fields; not independent predictions.')
    return results


def summarize(records):
    groups = defaultdict(list)
    for r in records:
        groups[r['metric']].append(r)
    result = {}
    for metric, items in sorted(groups.items()):
        if 'numerator' in items[0]:
            numerator, denominator = sum(x['numerator'] for x in items), sum(x['denominator'] for x in items)
            result[metric] = dict(value=numerator/denominator if denominator else None, numerator=numerator, denominator=denominator, tables=len(items))
        elif metric == 'matched_span_character_error_rate':
            errors, chars = sum(x['errors'] for x in items), sum(x['reference_chars'] for x in items)
            result[metric] = dict(value=errors/chars if chars else None, character_errors=errors, reference_chars=chars, checks=len(items))
        else:
            applicable = [x for x in items if x['passed'] is not None]
            passed = sum(x['passed'] for x in applicable)
            result[metric] = dict(value=passed/len(applicable) if applicable else None, passed=passed,
                                  total=len(applicable), not_automatically_scored=len(items)-len(applicable))
    return result


def prediction_dir(document, parser, output_root=None):
    if output_root is not None:
        return Path(output_root) / document / parser
    base = ROOT / 'results/parsed' if parser == 'pymupdf4llm_vlm' else SOURCE / 'results'
    return base / document / parser


def score(include_drafts=False, output_root=None):
    started = time.perf_counter()
    sources = read_json(ROOT / 'documents.json')
    all_labels = read_jsonl(ROOT / 'labels.jsonl')
    validate(all_labels, sources)
    labels = [x for x in all_labels if x['review_status'] in ({'draft', 'human_verified', 'adjudicated'} if include_drafts else {'human_verified', 'adjudicated'})]
    details, runs, documents, inputs = [], [], [], []
    for parser in PARSERS:
        for source in sources:
            work = prediction_dir(source['id'], parser, output_root)
            pages_path, run_path = work / 'pages.json', work / 'run.json'
            pages_data = read_json(pages_path) if pages_path.exists() else None
            run = read_json(run_path) if run_path.exists() else {}
            if pages_data:
                assert pages_data['source_sha256'] == source['sha256'], 'Prediction source hash mismatch'
                assert pages_data['parser'] == parser, 'Prediction parser mismatch'
            if run:
                assert run['input_sha256'] == source['sha256'], 'Run source hash mismatch'
            pages = pages_data['pages'] if pages_data else []
            ids = [p['page'] for p in pages]
            assert len(ids) == len(set(ids)) and all(1 <= n <= source['pages'] for n in ids), 'Invalid prediction page IDs'
            by_page = {p['page']: p['markdown'] for p in pages}
            inputs.append(dict(document=source['id'], parser=parser, pages_sha256=sha(pages_path) if pages_path.exists() else None,
                               run_sha256=sha(run_path) if run_path.exists() else None))
            run_record = dict(document=source['id'], parser=parser, status=run.get('status', 'missing'),
                              elapsed_seconds=run.get('elapsed_seconds'), pages_per_second=run.get('pages_per_second'),
                              source_pages=source['pages'], exported_pages=len(pages),
                              nonempty_pages=sum(bool(text_of(soup_for(m)).strip()) for m in by_page.values()),
                              versions=run.get('versions'), settings=run.get('settings'),
                              timing_note=run.get('timing_note'), peak_memory_mb=None,
                              memory_note='Not instrumented in saved runs; scoring does not rerun parsers.')
            runs.append(run_record)
            selected = [x for x in labels if x['document'] == source['id']]
            cache, per_document = {}, []
            for label in selected:
                p = label['page']
                if p not in cache:
                    soup = soup_for(by_page.get(p, ''))
                    tables, errors = extract_tables(soup)
                    cache[p] = soup, tables, errors
                soup, tables, errors = cache[p]
                for r in score_label(label, soup, tables):
                    r.update(document=source['id'], parser=parser, page=p,
                             prediction_missing=p not in by_page, table_parse_errors=errors)
                    per_document.append(r)
            details.extend(per_document)
            documents.append(dict(document=source['id'], parser=parser, metrics=summarize(per_document)))
    aggregated = {p: summarize([r for r in details if r['parser'] == p]) for p in PARSERS}
    # No combined score. Equal-document averages accompany pooled check counts.
    for parser, metrics in aggregated.items():
        for name, metric in metrics.items():
            vals = [d['metrics'][name]['value'] for d in documents if d['parser'] == parser and name in d['metrics'] and d['metrics'][name]['value'] is not None]
            metric['equal_document_mean'] = sum(vals)/len(vals) if vals else None
            metric['documents_with_metric'] = len(vals)
    result = dict(schema_version=1, label_sha256=sha(ROOT/'labels.jsonl'), scorer_sha256=sha(Path(__file__)),
                  evaluation_status='PRELIMINARY_ASSISTANT_DRAFTS' if include_drafts else 'REVIEWED_LABELS_ONLY',
                  selected_labels=len(labels), total_labels=len(all_labels), inputs=inputs,
                  aggregate=aggregated, documents=documents, runs=runs,
                  by_importance={p: {tier: summarize([r for r in details if r['parser'] == p and r['importance'] == tier])
                                     for tier in ('critical', 'supporting', 'cosmetic')} for p in PARSERS},
                  evaluation_seconds=round(time.perf_counter()-started, 3), hosted_model_calls=0, parser_reruns=0,
                  limitations=['Six previously inspected documents; development case study, not held-out generalization.',
                               'Association scores require explicit HTML/Markdown table relationships; flattened prose may contain recoverable facts.',
                               'Unit evidence and visual sequence checks are proxies, not semantic association scores.',
                               'Sparse labels do not measure global hallucination precision.',
                               'Draft labels are not independently human-verified gold.'])
    name = 'preliminary' if include_drafts else 'reviewed'
    write_json(ROOT/'results'/f'{name}.json', result)
    write_jsonl(ROOT/'results'/f'{name}_checks.jsonl', details)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'refresh', 'validate', 'score'])
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--include-drafts', action='store_true', help='Explicitly opt into preliminary assistant-label scores')
    parser.add_argument('--output-root', type=Path, help='Read cached parser outputs from this directory')
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare(args.render)
    elif args.command == 'refresh':
        result = refresh_annotations()
    elif args.command == 'validate':
        result = dict(validated_labels=validate(read_jsonl(ROOT/'labels.jsonl'), read_json(SOURCE/'source_manifest.json')))
    else:
        scored = score(args.include_drafts, args.output_root)
        result = {k: scored[k] for k in ('evaluation_status', 'selected_labels', 'evaluation_seconds', 'hosted_model_calls', 'parser_reruns')}
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
