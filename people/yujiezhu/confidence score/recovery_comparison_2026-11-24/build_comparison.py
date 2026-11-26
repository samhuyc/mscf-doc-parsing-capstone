"""Build an auditable saved-output recovery comparison. No model fitting/inference.

Run with ../.venv-score/bin/python build_comparison.py.
Manual review decisions live in manual_review.json; this script checks evidence
locators and numeric content, aggregates decisions, and builds the review HTML.
"""
import csv
import hashlib
import html
import json
import shutil
import sys
import time
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
DEMO = ROOT.parent / 'sponsor_demo_2026-11-10'
SPONSOR = ROOT.parents[2] / 'samhu' / '2026-09-29_sponsor_samples'
sys.path.insert(0, str(DEMO))
from build_demo import table_grid, header, norm


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


def yn(value):
    return 'Yes' if value else 'No'


def value_text(value):
    return ' / '.join(value) if isinstance(value, list) else value


def raw_cell(markdown, row, col):
    """Retrieve an origin cell at a span-expanded coordinate, preserving <br>."""
    table = BeautifulSoup(markdown, 'html.parser').find('table')
    occupied = set()
    for r, tr in enumerate(table.find_all('tr')):
        c = 0
        for tag in tr.find_all(['td', 'th'], recursive=False):
            while (r, c) in occupied:
                c += 1
            rs, cs = int(tag.get('rowspan', 1)), int(tag.get('colspan', 1))
            if (r, c) == (row, col):
                return str(tag), [s.strip() for s in tag.stripped_strings]
            occupied.update((r + dr, c + dc) for dr in range(rs) for dc in range(cs))
            c += cs
    raise ValueError(('No cell origin', row, col))


def main():
    start = time.perf_counter()
    review = read(ROOT / 'manual_review.json')
    originals = {x['sample_id']: x for x in read(DEMO / 'reviewed_cells.json')}
    diagnostics = read(DEMO / 'model_results/diagnostics.json')
    scores = {target: {x['sample_id']: x for x in d['predictions']}
              for target, d in diagnostics.items()}
    assets = ROOT / 'assets'
    assets.mkdir(exist_ok=True)
    inputs = {ROOT / 'manual_review.json', DEMO / 'reviewed_cells.json',
              DEMO / 'model_results/diagnostics.json', DEMO / 'build_demo.py'}
    rows, runs = [], {}
    for selected in review['samples']:
        old = originals[selected['sample_id']]
        doc, page = old['document'], old['page']
        source = f'{doc}_{page:03}.png'
        srcpath = DEMO / 'assets' / source
        shutil.copy2(srcpath, assets / source)
        inputs.add(srcpath)
        exports = {}
        for parser in ['mineru_ocr', 'pymupdf4llm']:
            path = DEMO / 'assets' / f'{doc}_{parser}.json'
            exports[parser] = read(path)
            assert exports[parser]['page'] == page
            shutil.copy2(path, assets / path.name)
            inputs.add(path)
        assert exports['mineru_ocr']['source_sha256'] == exports['pymupdf4llm']['source_sha256']
        before, after = exports['mineru_ocr']['markdown'], exports['pymupdf4llm']['markdown']
        oldgrid, _ = table_grid(before)
        assert oldgrid[old['html_row']][old['html_col']]['text'] == old['extracted_value']
        grid, _ = table_grid(after)
        r, c = selected['retry_row'], selected['retry_col']
        retry_value = grid[r][c]['text']
        retry_header, bound = header(grid, c, selected['header_rows'])
        retry_html, tokens = raw_cell(after, r, c)
        original_html, _ = raw_cell(before, old['html_row'], old['html_col'])
        reference = old['reference_value']
        expected = reference if isinstance(reference, list) else [reference]
        numeric_match = [norm(t) for t in tokens] == [norm(t) for t in expected]
        assert numeric_match == selected['retry_numeric_content_correct']
        if selected['retry_association_correct']:
            assert bound and len(tokens) == 1
            assert norm(retry_header) == norm(old['reference_column'])
        assoc = scores['association'][old['sample_id']]
        numeric = scores['numeric'][old['sample_id']]
        assert assoc['actual'] == int(old['row_correct'] and old['column_correct'])
        score = assoc['diagnostic_probability']
        retry_correct = all(selected[k] for k in ['retry_numeric_content_correct',
                            'retry_association_correct', 'retry_unit_correct'])
        row = dict(**selected, document=doc, page=page, source_image='assets/' + source,
                   source_sha256=exports['mineru_ocr']['source_sha256'],
                   association_score=score, numeric_score=numeric['diagnostic_probability'],
                   numeric_score_status=numeric['status'], score_band='low' if score < .5 else 'high',
                   original_value=old['extracted_value'], original_row=old['row_label'],
                   original_header=old['column_header'], original_cell_html=original_html,
                   original_numeric_correct=old['numeric_correct'],
                   original_association_correct=old['row_correct'] and old['column_correct'],
                   original_unit_correct=old['unit_correct'], original_correct=old['correct'],
                   reference_value=reference, reference_row=old['reference_row'],
                   reference_column=old['reference_column'], reference_unit=old['reference_unit'],
                   retry_value=retry_value, retry_value_tokens=tokens, retry_cell_html=retry_html,
                   retry_row_label=grid[r][0]['text'], retry_header=retry_header,
                   retry_correct=retry_correct,
                   outcome='corrected' if retry_correct and not old['correct'] else
                   'regression' if old['correct'] and not retry_correct else
                   'retained' if retry_correct else 'partial; still fails strict contract')
        rows.append(row)
        if doc not in runs:
            path = SPONSOR / 'results' / doc / 'pymupdf4llm' / 'run.json'
            run = read(path)
            assert run['input_sha256'] == row['source_sha256']
            shutil.copy2(path, assets / f'{doc}_pymupdf4llm_run.json')
            inputs.add(path)
            runs[doc] = {k: run[k] for k in ['elapsed_seconds', 'expected_pages',
                         'started_at_utc', 'versions', 'settings', 'timing_note']}

    strata = {f'{band}_{state}': 0 for band in ['low', 'high'] for state in ['correct', 'incorrect']}
    for sid, old in originals.items():
        s = scores['association'][sid]['diagnostic_probability']
        assert s is not None
        band = 'low' if s < .5 else 'high'
        strata[f"{band}_{'correct' if old['correct'] else 'incorrect'}"] += 1
    summary = dict(records=len(rows), documents=len(runs), pool_records=len(originals),
                   pool_strata=strata, selected_source_numeric_values=sum(
                       len(x['reference_value']) if isinstance(x['reference_value'], list) else 1 for x in rows),
                   original_errors=sum(not x['original_correct'] for x in rows),
                   corrected=sum(x['outcome'] == 'corrected' for x in rows),
                   new_errors=sum(x['outcome'] == 'regression' for x in rows),
                   original_correct=sum(x['original_correct'] for x in rows),
                   retry_correct=sum(x['retry_correct'] for x in rows),
                   remaining_errors=sum(not x['retry_correct'] for x in rows),
                   numeric_content_improved=sum(not x['original_numeric_correct'] and
                                                x['retry_numeric_content_correct'] for x in rows),
                   selected_high_score_errors=sum(x['score_band'] == 'high' and not x['original_correct'] for x in rows),
                   historical_parser_runs=runs, fresh_parser_inference=False,
                   independent_human_review=False,
                   build_elapsed_seconds=round(time.perf_counter()-start, 6))
    write(ROOT / 'comparison.json', dict(protocol={k:v for k,v in review.items() if k != 'samples'},
                                          summary=summary, samples=rows))
    fields = ['id','sample_id','score_band','association_score','numeric_score','original_value',
              'reference_value','retry_value','original_correct','retry_correct','original_numeric_correct',
              'retry_numeric_content_correct','original_association_correct','retry_association_correct',
              'retry_unit_correct','outcome','note']
    with (ROOT / 'comparison.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in rows: writer.writerow({k:value_text(row[k]) if isinstance(row[k],list) else row[k] for k in fields})
    provenance = []
    for path in sorted(inputs):
        provenance.append(dict(path=str(path.relative_to(ROOT.parents[3])),
                               sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    write(ROOT / 'provenance.json', dict(review_date=review['review_date'], inputs=provenance,
                                        generation='No new parser calls; saved output replay with manual source review.'))
    e = html.escape
    table_rows = ''.join(f"<tr><td><a href='#{x['id']}'>{x['id']} — {e(x['short_name'])}</a></td>"
                         f"<td>{x['score_band']} / {x['association_score']:.4f}</td>"
                         f"<td>{yn(x['original_correct'])}</td><td>{yn(x['retry_correct'])}</td>"
                         f"<td>{e(x['outcome'])}</td></tr>" for x in rows)
    details=[]
    for x in rows:
        details.append(f"""<section id='{x['id']}'><h2>{x['id']} — {e(x['short_name'])}</h2>
        <p><code>{x['sample_id']}</code> · physical page {x['page']} · association score {x['association_score']:.4f}
        · numeric score {f"{x['numeric_score']:.4f}" if x['numeric_score'] is not None else 'unavailable (failed training fold)'}</p>
        <p><b>Reference:</b> {e(value_text(x['reference_value']))} · {e(x['reference_row'])} · {e(x['reference_column'])} · {e(x['reference_unit'])}</p>
        <div class='columns'><article><h3>Original: MinerU OCR</h3><p>Value: <b>{e(x['original_value'])}</b></p>
        <p>Row: {e(x['original_row'])}</p><p>Header: {e(x['original_header'])}</p><pre>{e(x['original_cell_html'])}</pre>
        <p>Fully correct? <b>{yn(x['original_correct'])}</b></p></article>
        <article><h3>Alternative: PyMuPDF4LLM</h3><p>Value: <b>{e(' ↵ '.join(x['retry_value_tokens']))}</b></p>
        <p>Row: {e(x['retry_row_label'])}</p><p>Header: {e(x['retry_header'])}</p><pre>{e(x['retry_cell_html'])}</pre>
        <p>Numeric content readable: {yn(x['retry_numeric_content_correct'])}; association: {yn(x['retry_association_correct'])};
        separately usable unit context: {yn(x['retry_unit_correct'])}.<br>Fully correct? <b>{yn(x['retry_correct'])}</b></p></article></div>
        <p>{e(x['note'])}</p><details><summary>Inspect original document page</summary><img src='{x['source_image']}' alt='Source page for {e(x['short_name'])}'></details>
        <p>Saved page exports: <a href='assets/{x['document']}_mineru_ocr.json'>MinerU OCR</a> ·
        <a href='assets/{x['document']}_pymupdf4llm.json'>PyMuPDF4LLM</a></p></section>""")
    runtime_rows=''.join(f"<tr><td>{doc}</td><td>{run['expected_pages']}</td><td>{run['elapsed_seconds']:.3f} s</td></tr>" for doc,run in runs.items())
    report=f"""<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>Recovery comparison — 24 November 2026</title><style>
    body{{font:17px/1.55 system-ui,sans-serif;background:#f2f5f8;color:#172c3e;max-width:1180px;margin:35px auto;padding:0 24px}}
    h1{{font-size:36px;line-height:1.15}} h2{{font-size:25px}} a{{color:#076e72}} section,header{{background:white;border-radius:12px;padding:25px;margin:22px 0}}
    table{{border-collapse:collapse;width:100%;font-size:15px}}td,th{{padding:12px;text-align:left;border-bottom:1px solid #dce5eb}}th{{background:#e7f0f3}}
    .columns{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}article{{padding:18px;background:#f2f5f8;border-radius:8px;min-width:0}}
    pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}}img{{max-width:100%;max-height:1000px}}.note{{color:#895308}}.stats{{font-size:23px;font-weight:700;color:#087f75}}
    @media(max-width:750px){{.columns{{grid-template-columns:1fr}}table{{font-size:12px}}td,th{{padding:6px}}}}
    @media print{{details{{display:block}}section{{break-inside:avoid}}body{{font-size:12px}}}}
    </style><header><p>24 NOVEMBER 2026 · PRELIMINARY SOURCE-REVIEWED CASE STUDY</p><h1>Alternative parsing fully recovers 3 of 6 selected errors</h1>
    <p class='stats'>8 records · 4 documents · 3 corrected · 0 new errors · 3 still need repair</p>
    <p>MinerU OCR → saved PyMuPDF4LLM output. No fresh inference or new scoring model. <a href='UPDATE_SLIDES.pdf'>Two update slides</a> · <a href='comparison.csv'>CSV</a> · <a href='comparison.json'>Full evidence JSON</a></p>
    <p class='note'>Scores are existing uncalibrated association model outputs, not correctness probabilities. Labels and this review are assistant-authored, not independently human-verified.</p></header>
    <section><h2>Selection and correctness contract</h2><p>{e(review['primary_contract'])}</p>
    <p>Across all 50 existing records: 10 low-score errors, 0 low-score fully-correct records, 10 high-score errors and 30 high-score correct records (low &lt; 0.5; high ≥ 0.5). Selected A–D: four low-score errors; E–F: two high-score errors; G–H: two high-score correct controls.</p>
    <p>There is no low-score fully-correct example to include. Some EDF numbers are numerically right with low association scores, but their associations are wrong; these are not false alarms for association. Three selected EDF records each combine two source values: 8 extraction records cover 11 source numeric values.</p>
    <p>Selection uses already-known outcomes. Related cells share table-level errors. This comparison is illustrative, not a random sample, blind test, confidence calibration, or measured success rate on unseen documents. PyMuPDF4LLM also supplied agreement features in the existing model, so the alternative is not independent evidence for validating the score.</p></section>
    <section><h2>Actual recovery comparison</h2><table><thead><tr><th>Sample</th><th>Association score</th><th>Original correct?</th><th>Retry correct?</th><th>Outcome</th></tr></thead><tbody>{table_rows}</tbody></table>
    <p><b>Strict correctness: 2/8 → 5/8.</b> Three of six original errors become fully correct; the other three improve numeric readability but remain merged. No new errors among the two originally correct controls.</p>
    <p><b>High scores did accompany incorrect associations:</b> both selected Rolls-Royce records score 0.8837 despite unresolved year bindings. Their digits are already correct. The five original numeric errors in the full dataset have no out-of-family numeric score; this experiment does not demonstrate a high-scoring wrong number.</p></section>
    {''.join(details)}<section><h2>Runtime and provenance</h2><p>No fresh parser latency was measured. These are saved full-document PyMuPDF4LLM runtimes from Sam's September 30 runs; they are not per-cell retry times or measurements on this machine.</p>
    <table><tr><th>Document</th><th>Pages</th><th>Historical full-document runtime</th></tr>{runtime_rows}</table>
    <p>Historical timing includes child-process startup; excludes downloads, export and scoring. Original PDFs are not copied into this comparison; the existing source-page renders were visually checked against the saved reference labels. Input hashes: <a href='provenance.json'>provenance.json</a>. Manual decisions: <a href='manual_review.json'>manual_review.json</a>.</p>
    <p>The local evidence build took {summary['build_elapsed_seconds']:.3f} seconds before report rendering. It is file processing time, not extraction latency.</p></section></html>"""
    (ROOT/'REPORT.html').write_text(report)
    print(json.dumps({k:v for k,v in summary.items() if k!='historical_parser_runs'},indent=2))


if __name__ == '__main__':
    main()
