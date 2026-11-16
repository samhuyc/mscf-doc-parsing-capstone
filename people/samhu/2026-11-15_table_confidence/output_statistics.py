"""Observed output statistics, explicitly separating pending and empty results."""
from datetime import datetime, timezone
from html import escape
from pathlib import Path
import statistics

from regions import table_summary
from core import read, write

LABELS = dict(paddle='PP-OCRv5', tesseract='Tesseract', paddle_vl='PaddleOCR-VL',
              glm='GLM-OCR', monkey='MonkeyOCR', mineru='MinerU')


def median(values):
    return statistics.median(values) if values else None


def summarize_outputs(records, expected):
    success = [r for r in records if r['status']=='success']
    values = sorted(r['confidence']['geometric_mean'] for r in success
                    if r['confidence']['geometric_mean'] is not None)
    times = [r['seconds'] for r in success if r.get('seconds') is not None]
    return dict(expected=expected, completed=len(success),
        failed=sum(r['status']=='failed' for r in records),
        pending=expected-sum(r['status'] in ('success','failed') for r in records),
        empty_text=sum(not r.get('text','').strip() for r in success),
        truncated=sum(r.get('truncated',False) for r in success),
        scored_tables=len(values), median_table_confidence=median(values),
        p10_table_confidence=values[int((len(values)-1)*.1)] if values else None,
        minimum_table_confidence=min(values) if values else None,
        below_0_90=sum(v<.90 for v in values), at_least_0_99=sum(v>=.99 for v in values),
        zero_geometric_mean_tables=sum(v==0 for v in values),
        median_table_arithmetic_mean=median([r['confidence']['mean'] for r in success if r['confidence']['mean'] is not None]),
        median_seconds=median(times), total_recognition_seconds=sum(times),
        total_scored_units=sum(r['confidence']['scored_units'] for r in success))


def export(root, data):
    root=Path(root)
    batch=read(root/'batch_status.json') if (root/'batch_status.json').exists() else {}
    stages={s['engine']:s['status'] for s in batch.get('stages',[])}
    names=[n for n in LABELS if n in stages or any(n in t['models'] for t in data['tables'])]
    models={}
    for name in names:
        records=[t['models'][name]['crop'] for t in data['tables'] if name in t['models']]
        models[name]=summarize_outputs(records,len(data['tables']))
        models[name]['status']=('completed' if models[name]['completed']==len(data['tables']) else stages.get(name,'partial'))
    result=dict(snapshot_utc=datetime.now(timezone.utc).isoformat(), pages=len(data['pages']),
        table_candidates=len(data['tables']), pages_with_tables=sum((p.get('tables') or 0)>0 for p in data['pages']),
        models=models, correctness_accuracy=None,
        correctness_status='Not measured: independently checked transcription/cell labels are not yet available',
        summary_definition='Median across per-table geometric means; each table has equal weight; raw model-specific scores are not accuracy',
        timing_definition='Measured recognition seconds include confidence collection; partial runs are not matched-corpus speed comparisons')
    write(root/'output_statistics.json',result)
    rows=[]
    percent=lambda v: 'Not run yet' if v is None else f'{v*100:.2f}%'
    for name,s in models.items():
        duration='Not run yet' if s['median_seconds'] is None else f'{s["median_seconds"]:.2f} s'
        rows.append(f'<tr><td>{LABELS[name]}</td><td>{s["completed"]}/{s["expected"]} · {escape(s["status"])}</td>'
                    f'<td>{percent(s["median_table_confidence"])}</td><td>{percent(s["p10_table_confidence"])}</td>'
                    f'<td>{duration}</td><td>{s["empty_text"]} / {s["failed"]} / {s["truncated"]}</td></tr>')
    notices=[]
    for name,s in models.items():
        if s['scored_tables']:
            notices.append(f'<li>{LABELS[name]}: {s["at_least_0_99"]}/{s["scored_tables"]} scored tables have native confidence ≥99%; {s["below_0_90"]} are below 90%.</li>')
        if s['zero_geometric_mean_tables']:
            notices.append(f'<li>{LABELS[name]} has {s["zero_geometric_mean_tables"]} zero geometric means. A single zero-scored unit makes this aggregate zero; this does not mean the entire transcription is empty or wrong.</li>')
    section=f'''<section class="inventory"><h2>Observed output statistics</h2>
<p>{result['pages']} pages · {result['table_candidates']} table candidates on {result['pages_with_tables']} pages.
Snapshot: {escape(result['snapshot_utc'])}.</p>
<table><thead><tr><th>Model</th><th>Finished</th><th>Median native confidence</th><th>10th percentile across tables</th><th>Median time/table</th><th>Empty / Failed / Truncated</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<ul>{''.join(notices)}</ul>
<p>Confidence is the median of table-level geometric means, not extraction accuracy. Different models use different score definitions.
Partial runs cover different subsets; times include confidence collection. Queued models have no full-corpus results yet.</p>
<p><b>Why some fields were missing:</b> pending runs, full-page comparisons not available for these models, or correctness probabilities that have not been calibrated. Completed native scores are shown above.</p></section>'''
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Table extraction statistics</title>
<style>body{font:16px/1.5 system-ui;color:#192b3b;background:#f4f6f8;margin:0}main{max-width:1200px;padding:28px;margin:auto}section{background:white;padding:24px;border-radius:12px}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:12px;border-bottom:1px solid #ddd}th{font-size:13px}p,li{color:#45576b}table{font-variant-numeric:tabular-nums}@media(max-width:700px){main{padding:10px}section{padding:12px;overflow:auto}}</style><main>'''+section+'</main></html>'
    (root/'statistics.html').write_text(page)
    return section
