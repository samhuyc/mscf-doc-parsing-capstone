"""Small source-row checks plus coverage and text-layer agreement diagnostics."""
import csv
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / '2026-09-20_evaluation'))
from formats import plain_text, soup_for, numeric_counts as legacy_numeric_counts

PARSERS = ('mineru_ocr', 'mineru_vlm', 'pymupdf4llm')

def numeric_counts(text):
    # Raw PDF extraction can contain thousands of consecutive spaces/newlines.
    # Collapse these before the legacy lexical regex to avoid backtracking.
    return legacy_numeric_counts(re.sub(r'\s+', ' ', text).strip())

def norm(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', value)).replace('−', '-')

def check_row(markdown, check):
    soup = soup_for(markdown)
    text = soup.get_text(' ')
    # Match lexical tokens rather than substrings (98.9 must not match 198.9).
    counts = numeric_counts(text)
    expected = Counter(norm(v) for v in check['values'])
    retained = sum((counts & expected).values())
    label = re.sub(r'\s+', ' ', check['label']).strip().casefold()
    candidates = []
    for row in soup.find_all('tr'):
        cells = [re.sub(r'\s+', ' ', c.get_text(' ')).strip() for c in row.find_all(['td', 'th'], recursive=False)]
        if not cells:
            continue
        first = cells[0].casefold()
        if first == label or re.fullmatch(re.escape(label) + r'\s*[\d, ]+', first):
            candidates.append(cells)
    # Repeated identical rows can occur on statements (e.g. profit attribution).
    exact = any([norm(v) for v in c[-len(check['values']):]] == [norm(v) for v in check['values']] for c in candidates)
    return dict(**check, values_retained=retained, values_expected=sum(expected.values()),
                exact_row_cells=exact, candidate_rows=candidates)


def main():
    sources = json.loads((ROOT / 'source_manifest.json').read_text())
    checks = json.loads((ROOT / 'checks.json').read_text())['checks']
    rows = []
    audits = []
    for source in sources:
        with pymupdf.open(ROOT / 'inputs' / (source['id'] + '.pdf')) as doc:
            reference = [p.get_text(sort=True) for p in doc]
        for parser in PARSERS:
            work = ROOT / 'results' / source['id'] / parser
            run = json.loads((work / 'run.json').read_text()) if (work / 'run.json').exists() else dict(status='not_run')
            pages = json.loads((work / 'pages.json').read_text())['pages'] if (work / 'pages.json').exists() else []
            md_by_page = {p['page']:p['markdown'] for p in pages}
            subset = [check_row(md_by_page.get(c['page'], ''), c) for c in checks if c['document'] == source['id']]
            audits.extend(dict(parser=parser, **c) for c in subset)
            ref_words = pred_words = common_words = 0
            ref_numbers = pred_numbers = common_numbers = 0
            applicable = 0
            for i, ref in enumerate(reference, 1):
                if len(ref.strip()) < 30:
                    continue
                applicable += 1
                pred = plain_text(md_by_page.get(i, ''))
                a,b = [Counter(re.findall(r'\w+', s.casefold())) for s in (ref, pred)]
                ref_words += a.total(); pred_words += b.total(); common_words += (a & b).total()
                a,b = [numeric_counts(s) for s in (ref, pred)]
                ref_numbers += a.total(); pred_numbers += b.total(); common_numbers += (a & b).total()
            full = '\n\n'.join(md_by_page.values())
            tables = soup_for(full).find_all('table')
            row = dict(document=source['id'], parser=parser, status=run['status'], pages=source['pages'],
                       processed_pages=run.get('parsed_pages', 0),
                       nonempty_pages=sum(bool(plain_text(p['markdown'])) for p in pages),
                       elapsed_seconds=run.get('elapsed_seconds'), pages_per_second=run.get('pages_per_second'),
                       html_tables=len(tables), extracted_chars=len(plain_text(full)), native_text_pages=applicable,
                       native_word_recall=common_words / ref_words if ref_words else None,
                       native_numeric_f1=2*common_numbers/(ref_numbers+pred_numbers) if ref_numbers else None,
                       checked_values_retained=sum(c['values_retained'] for c in subset),
                       checked_values_total=sum(c['values_expected'] for c in subset),
                       checked_rows_exact=sum(c['exact_row_cells'] for c in subset), checked_rows_total=len(subset))
            rows.append(row)
    aggregates = []
    for parser in PARSERS:
        group = [r for r in rows if r['parser'] == parser]
        seconds = sum(r['elapsed_seconds'] or 0 for r in group)
        values = sum(r['checked_values_total'] for r in group)
        aggregates.append(dict(parser=parser, documents=len(group), completed=sum(r['status'] in ('success','partial','empty') for r in group),
                               nonempty_pages=sum(r['nonempty_pages'] for r in group), pages=sum(r['pages'] for r in group),
                               elapsed_seconds=round(seconds,3), pages_per_second=sum(r['processed_pages'] for r in group)/seconds if seconds else None,
                               checked_value_recall=sum(r['checked_values_retained'] for r in group)/values,
                               checked_exact_row_rate=sum(r['checked_rows_exact'] for r in group)/sum(r['checked_rows_total'] for r in group)))
    out = ROOT / 'evaluation'
    out.mkdir(exist_ok=True)
    (out / 'metrics.json').write_text(json.dumps(dict(aggregate=aggregates, documents=rows, checks=audits), indent=2) + '\n')
    with (out / 'metrics.csv').open('w') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    print(json.dumps(aggregates, indent=2))

if __name__ == '__main__':
    main()
