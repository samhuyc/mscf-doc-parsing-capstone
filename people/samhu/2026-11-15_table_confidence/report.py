"""Portable source-first review report and compact machine-readable table scores."""
import base64
import csv
from html import escape
from pathlib import Path

from regions import table_summary
from core import read, write, sha, digest

LABELS = dict(paddle='PP-OCRv5 mobile', tesseract='Tesseract', mineru='MinerU recognition',
              paddle_vl='PaddleOCR-VL-1.6', glm='GLM-OCR', monkey='MonkeyOCR-pro-1.2B')

def image_uri(path):
    return 'data:image/png;base64,' + base64.b64encode(path.read_bytes()).decode()


def score(value):
    return 'No scored units' if value is None else f'{value:.6f}'


def build(root):
    root = Path(root)
    data = read(root / 'tables.json')
    batch_notice = ''
    if (root / 'batch_status.json').exists():
        batch = read(root / 'batch_status.json')
        stage_text = ' · '.join(f'{LABELS[s["engine"]]}: {s["status"]}' for s in batch['stages'])
        batch_notice = f'<p class="notice"><b>Recognition batch: {escape(batch["status"])}</b><br>{escape(stage_text)}<br>Report refreshes after the first crop and every ten crops per model. Reload this file to see updates.</p>'
    mineru_settings = root / 'mineru/settings.json'
    if mineru_settings.exists():
        metadata = read(mineru_settings)
        if metadata['source_bundle_sha256'] != sha(root / 'tables.json'):
            raise ValueError('MinerU results refer to a different region bundle')
        data['settings']['mineru'] = metadata
        for table in data['tables']:
            path = root / 'mineru' / (table['table_id'] + '.json')
            result = read(path) if path.exists() else dict(status='pending', confidence=table_summary([]))
            if path.exists() and (result['image_sha256'] != table['image_sha256'] or result['settings_sha256'] != digest(metadata)):
                raise ValueError('MinerU crop or settings mismatch')
            flags = ['table_structure_unverified', 'crop_context_unverified']
            if result.get('truncated'):
                flags.append('token_limit')
            if result.get('repetition_flag'):
                flags.append('repetition')
            if result.get('status') == 'failed':
                flags.append('recognition_failed')
            table['models']['mineru'] = dict(crop=result, flags=flags, full_page_region=dict(
                status='unavailable_no_spatial_token_mapping', confidence=table_summary([])))
    cards, rows, compact = [], [], []
    for engine in ('paddle_vl', 'glm', 'monkey'):
        folder = root / 'extra' / engine
        if not (folder / 'settings.json').exists():
            continue
        metadata = read(folder / 'settings.json')
        if metadata['source_bundle_sha256'] != sha(root / 'tables.json'):
            raise ValueError('Additional model region bundle mismatch')
        data['settings'][engine] = metadata
        for table in data['tables']:
            path = folder / (table['table_id'] + '.json')
            result = read(path) if path.exists() else dict(status='pending', confidence=table_summary([]))
            if path.exists() and any(result[k] != v for k,v in dict(
                image_sha256=table['image_sha256'], source_sha256=table['source_sha256'],
                settings_sha256=digest(metadata)).items()):
                raise ValueError('Additional model provenance mismatch')
            flags = ['table_structure_unverified', 'crop_context_unverified']
            if result.get('truncated'):
                flags.append('token_limit')
            if result['status'] == 'failed':
                flags.append('recognition_failed')
            table['models'][engine] = dict(crop=result, flags=flags, full_page_region=dict(
                status='unavailable_no_full_page_baseline', confidence=table_summary([])))
    for table in data['tables']:
        results = []
        compact_table = {k: v for k, v in table.items() if k != 'models'}
        compact_table['models'] = {}
        for engine, result in table['models'].items():
            crop, full = result['crop'], result['full_page_region']
            conf = crop['confidence']
            compact_table['models'][engine] = dict(
                crop={k: v for k, v in crop.items() if k not in ('units', 'confidence_units')},
                full_page_region={k: v for k, v in full.items() if k != 'confidence_units'},
                flags=result['flags'])
            row = dict(table_id=table['table_id'], document=table['document'], page=table['page'],
                       engine=engine, status=crop['status'], layout_score=table['layout_score'],
                       scored_units=conf['scored_units'], geometric_mean=conf['geometric_mean'],
                       arithmetic_mean=conf['mean'], p10=conf['p10'],
                       fraction_below_0_90=conf['fraction_below_0_90'],
                       full_page_region_geometric_mean=full['confidence']['geometric_mean'],
                       seconds=crop.get('seconds'), peak_mlx_gb=crop.get('peak_mlx_gb'),
                       process_peak_rss_gb=crop.get('process_peak_rss_gb'),
                       content_geometric_mean=crop.get('content_only',{}).get('confidence',{}).get('geometric_mean'),
                       flags=';'.join(result['flags']))
            rows.append(row)
            if crop['status'] != 'success':
                message = ('Waiting for this table to run; no extraction or score exists yet.'
                           if crop['status']=='pending' else crop.get('error','Recognition failed.'))
                results.append(f'<section class="model"><h3>{escape(LABELS[engine])}</h3><p>{escape(message)}</p></section>')
                continue
            kind = {'paddle':'CTC character scores', 'tesseract':'word certainty / 100',
                    'mineru':'all emitted token probabilities, including formatting'}.get(engine,
                    'all emitted token probabilities, including formatting')
            extra = ''
            if 'peak_mlx_gb' in crop:
                content = crop.get('content_only',{})
                content_note = (f'Content-token geometric mean: {score(content["confidence"]["geometric_mean"])}; '
                                f'{content["confidence"]["scored_units"]} of {conf["scored_units"]} tokens included; mixed content/markup tokens excluded.'
                                if content.get('status')=='available' else
                                'Content-only scoring cannot be aligned for this output; the all-token score above is valid.')
                extra = f'''<p class="muted">{content_note}<br>
Peak MLX allocation: {crop['peak_mlx_gb']:.2f} GB; process peak resident memory: {crop['process_peak_rss_gb']:.2f} GB.
These overlap and must not be added. Timing includes confidence collection.</p>'''
            baseline_html = ''
            if full['status']=='success' and full['confidence']['geometric_mean'] is not None:
                baseline_html = f'<details><summary>Existing full-page comparison · native score {score(full["confidence"]["geometric_mean"])}</summary><pre>{escape(full.get("text",""))}</pre></details>'
            results.append(f'''<section class="model"><h3>{escape(LABELS[engine])} <small>{kind}</small></h3>
<div class="scores"><div><span>Native confidence · geometric mean</span><strong>{score(conf['geometric_mean'])}</strong></div>
<div><span>10th percentile</span><strong>{score(conf['p10'])}</strong></div>
<div><span>Scored units</span><strong>{conf['scored_units']}</strong></div></div>
<p class="muted">Status: {escape(crop['status'])} · Recognition: {crop.get('seconds', '—')} s</p>
{extra}<details><summary>Table-crop transcription</summary><pre>{escape(crop.get('text', crop.get('error', 'No output')))}</pre></details>
{baseline_html}
<p class="muted">{escape(', '.join(result['flags']).replace('_', ' '))}</p></section>''')
        compact.append(compact_table)
        cards.append(f'''<article id="{escape(table['table_id'])}"><h2>{escape(table['document'])} · page {table['page']} · table {table['table_id'].rsplit('t',1)[1]}</h2>
<p class="muted">Layout detection score: {table['layout_score']:.4f} · Financial relevance: unreviewed</p>
<div class="tablebody"><div class="source"><img loading="lazy" decoding="async" alt="Source table crop" src="{image_uri(root / table['image'])}"></div><div>{''.join(results)}</div></div></article>''')
    overviews = []
    for page in data['pages']:
        if page['status'] == 'success':
            overviews.append(f'''<details><summary>{escape(page['document'])} · page {page['page']} · {page['tables']} detected table(s)</summary>
<img class="overview" loading="lazy" decoding="async" alt="Full page with detected table boxes" src="{image_uri(root / page['overview'])}"></details>''')
        else:
            overviews.append(f'<p>{escape(page["document"])} page {page["page"]}: FAILED — {escape(page["error"])}</p>')
    review = read(Path(__file__).resolve().parent / 'layout_review.json')
    inventory = []
    for engine in ('paddle_vl', 'glm', 'monkey'):
        if engine not in data['settings']:
            continue
        outputs = [t['models'][engine]['crop'] for t in data['tables']]
        successful = [r for r in outputs if r['status'] == 'success']
        peaks = [r['peak_mlx_gb'] for r in successful]
        memory = f'{min(peaks):.2f}–{max(peaks):.2f}' if peaks else 'Pending'
        inventory.append(f'<tr><td>{LABELS[engine]}</td><td>{data["settings"][engine]["checkpoint_bytes"]/1e9:.3f} GB</td>'
                         f'<td>{len(successful)}/{len(outputs)}</td><td>{memory} GB</td></tr>')
    model_inventory = ('<section class="inventory"><h2>Additional small models</h2><table><thead><tr><th>Model</th><th>Model files</th>'
                       '<th>Crops completed</th><th>Peak MLX allocation</th></tr></thead><tbody>'+''.join(inventory)+
                       '</tbody></table><p class="muted">4 GB limit applies to files. Running memory can exceed it. '
                       'DeepSeek-OCR-2 (6.79 GB) is excluded. Original weights; Apple MLX runtime; fixed greedy decoding. '
                       'Monkey’s publisher repetition penalty is disabled for this raw-logit trial. No accuracy ranking has been established.</p></section>') if inventory else ''
    findings = ''.join(f'<li><b>{escape(f["document"])} · page {f["page"]}:</b> {escape(f["detail"])}</li>'
                       for f in review['findings'] if any(p['document'] == f['document'] and p['page'] == f['page'] for p in data['pages']))
    from output_statistics import export
    statistics_section = export(root, data)
    accuracy_link = ('<p><a href="accuracy/report.html">View the 19-crop confidence versus numeric transcription comparison</a>. '
                     'Source references are assistant-reviewed; financial cell associations are not scored.</p>'
                     if (root/'accuracy/report.html').exists() else '')
    html = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Financial table confidence · development run</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f1f3f5;color:#1b2735;font:15px/1.5 system-ui,sans-serif}}main{{max-width:1480px;margin:auto;padding:32px}}
h1{{font-size:32px;line-height:1.2}}h2{{font-size:20px}}h3{{font-size:18px}}small{{font-size:12px;color:#586777;font-weight:400}}
.notice{{background:#fff4da;border-left:4px solid #a46a00;padding:16px}}article,.inventory{{background:white;padding:24px;margin:24px 0;border-radius:10px;border:1px solid #d9e0e7}}
.tablebody{{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,1fr);gap:28px}}img{{max-width:100%;height:auto}}.source{{align-self:start;position:sticky;top:16px}}
.scores{{display:flex;gap:22px;flex-wrap:wrap}}.scores span{{display:block;font-size:12px;color:#586777}}.scores strong{{font-size:23px;font-variant-numeric:tabular-nums}}
.model+.model{{border-top:1px solid #d9e0e7;margin-top:24px}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;max-height:320px;overflow:auto;background:#f6f7f9;padding:14px;font:12px/1.6 ui-monospace,monospace}}
.muted{{color:#586777;font-size:13px}}summary{{cursor:pointer;padding:6px 0}}.overview{{max-height:1000px;width:auto}}
table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;padding:8px;border-bottom:1px solid #d9e0e7}}
@media(max-width:900px){{main{{padding:14px}}.tablebody{{grid-template-columns:1fr}}.source{{position:static}}article{{padding:16px}}}}
</style><main><h1>Financial table confidence</h1><p>{len(data['tables'])} table candidates across {len(data['pages'])} selected pages · shared PP-DocLayout_plus-L detector · development run</p>
{batch_notice}
{statistics_section}
{accuracy_link}
<p class="notice">These are raw native recognition scores, not probabilities that a table is correct. Scores are not comparable across engines. Table structure, omitted content, financial relevance and crop context still require review.</p>
{model_inventory}
<p>Each model receives the same source crop, then applies its recorded resizing. Paddle's existing page baseline uses 200 DPI; Tesseract's uses 300 DPI, while this shared-crop pilot uses {data['settings']['render_dpi']} DPI. Baseline differences do not establish accuracy changes. Primary summary: geometric mean, fixed before new correctness review.</p>
<details open class="notice"><summary>Known layout limitations · assistant visual review</summary><ul>{findings}</ul></details>
<section class="inventory"><h2>Page coverage and missed-table review</h2><p>Inspect the whole page for missed tables, detached headers, units and footnotes. Zero detections does not establish that a page has no tables.</p>{''.join(overviews)}</section>
{''.join(cards)}</main></html>'''
    (root / 'report.html').write_text(html)
    fields = ['table_id', 'document', 'page', 'engine', 'status', 'layout_score', 'scored_units',
              'geometric_mean', 'arithmetic_mean', 'p10', 'fraction_below_0_90',
              'full_page_region_geometric_mean', 'seconds', 'peak_mlx_gb', 'process_peak_rss_gb',
              'content_geometric_mean', 'flags']
    with (root / 'table_scores.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    # Never overwrite human decisions when regenerating the report.
    review_path = root / 'review_queue.csv'
    existing = []
    if review_path.exists():
        with review_path.open(newline='') as stream:
            existing = list(csv.DictReader(stream))
    existing_keys = {(r['table_id'], r['engine']) for r in existing}
    additions = [dict(table_id=r['table_id'], engine=r['engine']) for r in rows
                 if (r['table_id'], r['engine']) not in existing_keys]
    if additions or not review_path.exists():
        with review_path.open('w', newline='') as stream:
            fields = ['table_id', 'engine', 'financially_relevant', 'crop_complete_with_headers_units',
                      'transcription_correct', 'numeric_errors', 'association_correct', 'reviewer', 'notes']
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(existing + additions)
    write(root / 'summary.json', dict(settings=data['settings'], pages=data['pages'], tables=compact, layout_review=review))


if __name__ == '__main__':
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('root', type=Path)
    build(cli.parse_args().root)
