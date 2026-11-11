"""Reproducible offline extraction-evidence pilot; run with ../.venv-score/bin/python.

Predictors read parser exports only. Review labels enter fit/evaluation later.
This is a diagnostic retrospective demo, not validated production calibration.
"""
import csv
import hashlib
import html
import json
import math
import re
import shutil
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent
SPONSOR = ROOT.parents[2] / 'samhu' / '2026-09-29_sponsor_samples'


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean(value):
    return re.sub(r'\s+', ' ', value).strip()


def norm(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFC', value)).replace('−', '-').casefold()


def label_norm(value):
    value = unicodedata.normalize('NFKC', value)
    return norm(re.sub(r'[\s\d,]+$', '', value))


def single_number(value):
    return bool(re.fullmatch(r'[$£€]?\(?-?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?\)?(?:%|pts|p)?', norm(value)))


def table_grid(markdown):
    table = BeautifulSoup(markdown, 'html.parser').find('table')
    if table is None:
        return [], []
    rows = table.find_all('tr')
    occupied = {}
    origins = []
    for r, row in enumerate(rows):
        c = 0
        for tag in row.find_all(['td', 'th'], recursive=False):
            while (r, c) in occupied:
                c += 1
            rs, cs = int(tag.get('rowspan', 1)), int(tag.get('colspan', 1))
            cell = dict(text=clean(tag.get_text(' ')), row=r, col=c, rowspan=rs, colspan=cs)
            origins.append(cell)
            for dr in range(rs):
                for dc in range(cs):
                    if (r+dr, c+dc) in occupied:
                        raise ValueError('Overlapping HTML spans')
                    occupied[r+dr, c+dc] = cell
            c += cs
    width = max((c for r, c in occupied), default=-1) + 1
    empty = dict(text='', row=-1, col=-1, rowspan=1, colspan=1)
    grid = [[occupied.get((r, c), empty) for c in range(width)] for r in range(len(rows))]
    return grid, origins


def header(grid, col, count):
    seen, parts = set(), []
    merged = False
    for row in grid[:count]:
        cell = row[col]
        key = (cell['row'], cell['col'])
        if cell['text'] and key not in seen:
            parts.append(cell['text'])
            # A top-level grouping header is allowed; its last level must be unique.
            merged = cell['colspan'] != 1
            seen.add(key)
    return ' / '.join(parts), bool(parts) and not merged


def predictions(primary_md, comparison_md, config):
    grid, origins = table_grid(primary_md)
    other, _ = table_grid(comparison_md)
    output = []
    for cell in origins:
        r, c = cell['row'], cell['col']
        if r < config['header_rows'] or c < config['value_start'] or not cell['text']:
            continue
        row_cell = grid[r][0]
        h, bound = header(grid, c, config['header_rows'])
        candidates = [row for row in other[config['comparison_header_rows']:]
                      if label_norm(row[0]['text']) == label_norm(row_cell['text']) and row[0]['text']]
        ordinal = c - config['value_start']
        oc = config['comparison_value_start'] + ordinal
        compare_value, compare_header = None, None
        if len(candidates) == 1 and oc < len(candidates[0]):
            compare_value = candidates[0][oc]['text']
            compare_header, _ = header(other, oc, config['comparison_header_rows'])
        features = dict(single_numeric_value=single_number(cell['text']),
                        row_label_unmerged=row_cell['rowspan'] == row_cell['colspan'] == 1,
                        value_cell_unmerged=cell['rowspan'] == cell['colspan'] == 1,
                        unique_comparison_row=len(candidates) == 1,
                        value_agreement=compare_value is not None and norm(compare_value) == norm(cell['text']),
                        column_header_bound=bound,
                        column_header_agreement=compare_header is not None and norm(h) == norm(compare_header))
        output.append(dict(sample_id=f"{config['id']}:{len(output)+1:02}", document=config['id'],
                           page=config['page'], split=config['split'],
                           table=0, html_row=r, html_col=c, row_label=row_cell['text'],
                           column_header=h, extracted_value=cell['text'], comparison_value=compare_value,
                           comparison_header=compare_header, features=features,
                           evidence_group='stronger' if all(features.values()) else 'weaker',
                           reasons=[k for k,v in features.items() if not v]))
        if len(output) == 10:
            break
    return output


def expand_labels(doc):
    labels = []
    for row in doc['rows']:
        for c, value in enumerate(row['values']):
            flags = {key: row.get(key, doc.get(key)) for key in
                     ['numeric_correct', 'row_correct', 'column_correct', 'unit_correct']}
            assert all(isinstance(v, bool) for v in flags.values())
            labels.append(dict(reference_value=value, reference_row=row['label'],
                               reference_column=doc['column_headers'][c],
                               reference_unit=row['unit'][c] if isinstance(row['unit'], list) else row['unit'],
                               **flags, correct=all(flags.values()), review_note=doc['note']))
    return labels


def fit(records):
    result = {}
    for group in ['stronger', 'weaker']:
        rows = [r for r in records if r['split'] == 'development' and r['evidence_group'] == group]
        n, k = len(rows), sum(r['correct'] for r in rows)
        result[group] = dict(n=n, correct=k, documents=sorted({r['document'] for r in rows}),
                             observed_rate=k/n if n else None)
    return result


def summarize(records, estimates):
    result = dict(groups=estimates, sample_count=len(records), development_count=sum(r['split']=='development' for r in records),
                  replay_count=sum(r['split']=='replay' for r in records),
                  numeric_correct=sum(r['numeric_correct'] for r in records),
                  structured_correct=sum(r['correct'] for r in records),
                  independent_human_review=False)
    result['by_document'] = [dict(document=d, count=len(group), correct=sum(x['correct'] for x in group),
                                  numeric_correct=sum(x['numeric_correct'] for x in group),
                                  groups=sorted({x['evidence_group'] for x in group}))
                             for d in dict.fromkeys(r['document'] for r in records)
                             for group in [[x for x in records if x['document']==d]]]
    replay = [r for r in records if r['split']=='replay']
    result['replay_groups'] = [dict(group=g, n=len(rows), correct=sum(r['correct'] for r in rows))
                               for g in estimates
                               for rows in [[r for r in replay if r['evidence_group']==g]]]
    result['confidence_status'] = 'not_estimated_insufficient_validation'
    return result


def render_report(records, summary, protocol):
    e = html.escape
    cards = ''.join(f'<div class="card"><h3>{group.title()} evidence</h3><strong>{v["correct"]}/{v["n"]}</strong><p>Observed development cells passing the strict contract.</p><p>{len(v["documents"])} document(s). This count is not a probability for a new cell.</p></div>' for group,v in summary['groups'].items())
    rows = ''
    for r in records:
        rows += f'<tr><td>{e(r["sample_id"])}<br>{r["split"]}, p. {r["page"]}</td><td>{e(r["row_label"])}<br><small>{e(r["column_header"])}</small></td><td>{e(r["extracted_value"])}</td><td>{r["evidence_group"]}<br><small>Probability: not estimated</small></td><td>{"Pass" if r["correct"] else "Needs repair"}<br><small>{e(", ".join(k.replace("_correct", "") for k in ["numeric_correct","row_correct","column_correct","unit_correct"] if not r[k]))}</small></td></tr>'
    galleries = ''.join(f'<details><summary>{e(c["short"])} · source page {c["page"]}</summary><img src="assets/{c["id"]}_{c["page"]:03}.png" alt="Source page for {e(c["short"])}"></details>' for c in protocol['documents'])
    replay = ''.join(f'<li>{r["group"].title()} evidence: {r["correct"]}/{r["n"]} replay cells pass the strict contract.</li>' for r in summary['replay_groups'])
    content = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Extraction evidence — probability not yet estimated</title><style>
body{{font:17px/1.55 system-ui,sans-serif;color:#172c3e;background:#f3f6f8;margin:0}}main{{max-width:1160px;margin:auto;padding:48px 28px}}h1{{font-size:40px;line-height:1.12}}h2{{margin-top:36px}}.cards{{display:flex;gap:20px}}.card{{background:white;border-top:5px solid #168378;padding:24px;flex:1;border-radius:8px}}strong{{font-size:40px}}.notice{{background:#fff3d9;padding:18px;border-left:4px solid #b87c17}}table{{border-collapse:collapse;background:white;width:100%;font-size:13px;table-layout:fixed}}td,th{{border-bottom:1px solid #dbe3e9;padding:10px;text-align:left;overflow-wrap:anywhere}}small{{color:#5a6b76}}img{{max-width:100%;max-height:1000px}}details{{background:white;margin:10px 0;padding:14px}}a{{color:#00776f}}
</style><main><p>Corrected sponsor demonstration · 10 November 2026</p><h1>Extraction evidence before probability calibration</h1><p>50 sampled cells from five sponsor documents. MinerU OCR output compared with another parser and existing source-page renders.</p>
<p class="notice">Correction: the previous two smoothed group rates have been withdrawn as per-cell confidence scores. All cells now have confidence = null. Evidence strength and observed correctness remain available. Labels were reviewed by the assistant, not an independent human.</p><div class="cards">{cards}</div>
<h2>Two different questions</h2><p>Is the numeric content correct? Does the exported cell also preserve the correct row, column and unit context? Here, {summary['numeric_correct']}/50 cells preserve numeric content and {summary['structured_correct']}/50 pass the stricter structured-cell contract. These are sample counts, not probabilities assigned to individual cells.</p>
<h2>Observable evidence</h2><p>Stronger evidence requires one well-formed value, unmerged value/row cells, a unique comparison row and agreement on value and a bound column header. Otherwise evidence is weaker. Unit correctness is reviewed but has no independent predictive feature in this version. Agreement can occur when both parsers are wrong.</p>
<h2>Separate-document replay</h2><p>30 development cells and 20 retrospective replay cells. Both related Rolls-Royce documents remain together. Earlier reports were known; this is not a blind test.</p><ul>{replay}</ul><p>All ten sampled release numbers are right, but the primary export merges their period headers. A strict structural failure is not proof of a numerically wrong value. Table-level errors make the cell observations correlated.</p>
<h2>Separate correctness models are now implemented</h2><p><a href="model_results/MODEL_REPORT.md">Model results and validation audit</a> · <a href="model_results/review_queue.csv">Human-review queue</a></p><p>The new pipeline fits individual-feature logistic models for numeric transcription and row/column association, with document-family validation and separate calibration support. Numeric validation covers 40/50 cells but zero of the five errors: holding EDF out removes all failures from training. Association validation covers all 50 cells but struggles on the Rolls-Royce merged headers. These are exploratory diagnostics; public probabilities remain unavailable.</p><h2>What would make a probability meaningful?</h2><p>Define numeric correctness separately from association correctness. Collect independent labels across representative documents, retain individual evidence features, fit a correctness model, and evaluate/calibrate it on document-separated data. On genuinely new documents, items assigned probabilities near 0.95 should be correct approximately 95% of the time. More distinct scores alone do not establish this property.</p>
<h2>When the system cannot form a cell</h2><p>Peterborough page 2 collapses to one column: review required, confidence null. It is outside the 50-cell denominator. Missing values and whole-document completeness are not measured.</p><details><summary>Peterborough source page</summary><img src="assets/peterborough_2025_002.png" alt="Peterborough source page"></details>
<h2>Audit trail</h2><p><a href="CONFIDENCE_DEMO.pdf">Corrected presentation</a> · <a href="SPEAKER_NOTES.md">Speaker notes</a> · <a href="reviewed_cells.csv">50 cells (CSV)</a> · <a href="README.md">Method</a></p><table><thead><tr><th>Sample</th><th>Extracted context</th><th>Value</th><th>Evidence / probability</th><th>Source review</th></tr></thead><tbody>{rows}</tbody></table><h2>Source-page evidence</h2>{galleries}</main></html>'''
    (ROOT/'REPORT.html').write_text(content)


def main():
    protocol = read(ROOT/'protocol.json')
    reviews = read(ROOT/'review_labels.json')['documents']
    sources = {s['id']:s for s in read(SPONSOR/'source_manifest.json')}
    (ROOT/'assets').mkdir(exist_ok=True)
    all_predictions, provenance = [], []
    for cfg in protocol['documents']:
        texts = {}
        for parser in ['mineru_ocr','pymupdf4llm']:
            path = SPONSOR/'results'/cfg['id']/parser/'pages.json'
            export = read(path)
            assert export['source_sha256'] == sources[cfg['id']]['sha256']
            page = next(p for p in export['pages'] if p['page']==cfg['page'])
            texts[parser] = page['markdown']
            snapshot = ROOT/'assets'/f"{cfg['id']}_{parser}.json"
            write(snapshot, dict(page=cfg['page'], markdown=page['markdown'], source_sha256=export['source_sha256']))
            provenance.append(dict(document=cfg['id'], parser=parser, source_path=str(path.relative_to(ROOT.parents[3])),
                                   export_sha256=sha(path), snapshot_sha256=sha(snapshot), source_pdf_sha256=export['source_sha256']))
        generated = predictions(texts['mineru_ocr'], texts['pymupdf4llm'], cfg)
        assert len(generated)==10, cfg['id']
        all_predictions.extend(generated)
    # Persist the label-free output separately: correctness cannot enter these features.
    write(ROOT/'predictions_without_labels.json', all_predictions)
    records = []
    for cfg in protocol['documents']:
        generated = [r for r in all_predictions if r['document']==cfg['id']]
        labels = expand_labels(reviews[cfg['id']])
        assert len(labels)==len(generated)
        for pred, label in zip(generated, labels):
            if label['numeric_correct']:
                assert isinstance(label['reference_value'],str)
                assert norm(pred['extracted_value'])==norm(label['reference_value']), pred['sample_id']
            records.append(dict(**pred, **label, reviewer='assistant', human_verified=False))
    estimates = fit(records)
    for r in records:
        r['confidence'] = None
        r['confidence_status'] = 'not_estimated_insufficient_validation'
    summary = summarize(records, estimates)
    for cfg in [*protocol['documents'], protocol['abstention_example']]:
        filename = f"{cfg['id']}_{cfg['page']:03}.png"
        source_image = SPONSOR/'evaluation'/'source_pages'/filename
        shutil.copyfile(source_image, ROOT/'assets'/filename)
        provenance.append(dict(document=cfg['id'], source_image=filename, image_sha256=sha(source_image), source_url=sources[cfg['id']]['url']))
    # Check the abstention condition using raw output, not source labels.
    abst = protocol['abstention_example']
    raw = read(SPONSOR/'results'/abst['id']/'mineru_ocr'/'pages.json')
    page = next(p for p in raw['pages'] if p['page']==abst['page'])
    grid, _ = table_grid(page['markdown'])
    assert max(map(len, grid))==1
    write(ROOT/'assets'/'peterborough_2025_mineru_ocr.json', page)
    write(ROOT/'abstentions.json', [dict(document=abst['id'], page=abst['page'], confidence=None,
          status='review_required', reason=abst['reason'])])
    write(ROOT/'reviewed_cells.json', records)
    write(ROOT/'summary.json', summary)
    write(ROOT/'provenance.json', dict(inputs=provenance, protocol_sha256=sha(ROOT/'protocol.json'),
          review_labels_sha256=sha(ROOT/'review_labels.json'), predictor_sha256=sha(Path(__file__))))
    fields = ['sample_id','document','page','split','html_row','html_col','row_label','column_header',
              'extracted_value','comparison_value','reference_value','reference_row','reference_column',
              'reference_unit','evidence_group','confidence','confidence_status','numeric_correct','row_correct','column_correct',
              'unit_correct','correct','human_verified','reasons','review_note']
    with (ROOT/'reviewed_cells.csv').open('w',newline='') as f:
        writer = csv.DictWriter(f,fieldnames=fields)
        writer.writeheader()
        for r in records:
            writer.writerow({k:json.dumps(r[k],ensure_ascii=False) if isinstance(r[k],(list,dict)) else r[k] for k in fields})
    render_report(records, summary, protocol)
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
