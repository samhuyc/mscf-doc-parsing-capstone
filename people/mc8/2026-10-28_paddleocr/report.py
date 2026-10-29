"""Offline comparisons using Sam's metric definitions and saved predictions."""
import csv
from html import escape as e
import json
import os
from pathlib import Path
import shutil
from urllib.parse import quote

from common import ROOT, REFERENCE, PARSER, load, prediction_dir, scorer

NAMES = {'mineru_ocr':'MinerU OCR','mineru_vlm':'MinerU VLM','pymupdf4llm':'PyMuPDF4LLM + Tesseract',
         'pymupdf4llm_vlm':'PyMuPDF4LLM + VLM',PARSER:'PaddleOCR PP-StructureV3 (CPU)'}


def href(path):
    return quote(os.path.relpath(path,ROOT/'review'),safe='/')


def render_prediction(markdown,directory,renderer):
    from benchmark import soup_for
    soup=soup_for(markdown)
    # Paddle's native Markdown wraps tables/images in inert centered divs.
    # Sam's allowlist would delete those containers AND their children.
    # Unwrap only these containers, then apply his original safety renderer.
    for container in list(soup.find_all(['div','html','body'])):
        container.unwrap()
    return renderer.rendered(str(soup),directory)


def main():
    b=scorer()
    definitions=load('sam_report_definitions',REFERENCE/'2026-10-05_pilot_benchmark/report.py')
    definitions.PARSERS=b.PARSERS
    definitions.NAMES=NAMES
    renderer=load('sam_safe_renderer',REFERENCE/'2026-10-05_pilot_benchmark/review_addition.py')
    renderer.ROOT=ROOT
    result=b.read_json(ROOT/'results/preliminary.json')
    paddle_runs=[r for r in result['runs'] if r['parser']==PARSER]
    processed=sum(r['exported_pages'] for r in paddle_runs)
    coverage_note=(f'PaddleOCR retains {processed}/140 processed physical pages, including all 18 labeled pages. '
                   'The run prioritizes the unchanged 54-label accuracy evaluation. '
                   'Full-document coverage, native-text diagnostics and end-to-end timing are incomplete.'
                   if processed<140 else 'PaddleOCR processed all 140 physical pages.')
    labels=b.read_jsonl(ROOT/'labels.jsonl')
    checks=b.read_jsonl(ROOT/'results/preliminary_checks.jsonl')
    docs=b.read_json(ROOT/'documents.json')
    out=ROOT/'review'
    out.mkdir(exist_ok=True)
    shutil.copytree(REFERENCE/'2026-10-05_pilot_benchmark/review/assets',out/'assets',dirs_exist_ok=True)
    nav='<nav>'+''.join(f'<a href="{key}.html">{name}</a>' for key,name in [('index','Overview'),('tables','Tables'),('numbers','Numbers'),('text','Text & order'),('comparison','Same pages'),('outputs','Saved outputs'),('labels','References')])+'</nav>'

    def start(title):
        return ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                f'<title>{e(title)}</title><style>{definitions.CSS}.parsed img{{max-width:100%}}.parsed{{max-height:700px;overflow:auto}}'
                '.predictions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.prediction{min-width:0}'
                '@media(max-width:850px){.predictions{display:block}}</style><body>'+nav+f'<h1>{e(title)}</h1>'
                '<p class="banner">Same six PDFs and 54 unchanged assistant-authored draft references. '
                '18 of 140 pages have selected labels; 0 labels are human verified. Results are preliminary. '
                'Missing or ambiguous cells fail; number presence does not establish row/year association.</p>'
                f'<p class="banner">{e(coverage_note)}</p>')

    def finish():
        return '<p><a href="../README.md">Method and commands</a> · <a href="../results/preliminary.json">Scores and provenance</a> · <a href="../results/preliminary_checks.jsonl">Every check</a></p></body></html>'

    main_metrics=['associated_value_accuracy','selected_value_presence','negative_value_accuracy','text_span_retention','footnote_text_retention','reading_order_accuracy']
    index=start('PaddleOCR replication of Sam’s pipeline')
    index+='<p>Sam’s original four exports are frozen in the reference snapshot. PaddleOCR supplies OCR, layout and native HTML tables for the selected evaluation pages, retaining every previously completed page. Source PDFs match Sam’s SHA-256 hashes. Predictions receive no numeric corrections or label-based repair.</p>'
    index+='<p>The CPU configuration uses PP-OCRv5 mobile text detection/recognition with PP-StructureV3’s standard layout/table models. Rendering and recognition crops use 300 DPI; the detector has a 1,280-pixel internal limit to avoid a macOS native-runtime crash. This configuration is fixed across all inputs.</p>'
    index+=definitions.metric_table(result['aggregate'],main_metrics)
    index+='<h2>Coverage and recorded processing time</h2><table><tr><th>Parser</th><th>Documents with output</th><th>Text pages</th><th>Seconds</th></tr>'
    for parser in b.PARSERS:
        runs=[r for r in result['runs'] if r['parser']==parser]
        index+=f'<tr><th>{NAMES[parser]}</th><td>{sum(r["status"] in {"success","partial","empty"} for r in runs)}/6</td><td>{sum(r["nonempty_pages"] for r in runs)}/140</td><td>{sum(r["elapsed_seconds"] or 0 for r in runs):.1f}</td></tr>'
    index+='</table><p>Historical Sam runs used Apple Silicon; this run uses an Intel Mac CPU. The selected-page run combines preserved page timings with new page timings; its whole-document runtime is unavailable. These figures are not a speed comparison.</p>'
    index+='<p><a href="comparison.html">Review the same six example pages</a> · <a href="outputs.html">Open saved document outputs</a></p>'
    (out/'index.html').write_text(index+finish())
    from metric_glossary import glossary_html
    for key,group in definitions.GROUPS.items():
        names=group['primary']+group['extra']
        page=start(group['title'])+f'<p>{e(group["question"])}</p><p>{e(group["scope"])}</p>'
        page+=definitions.metric_table(result['aggregate'],names)
        page+=glossary_html(labels,definitions.METRICS,definitions.UNSCORED,names)
        for doc in docs:
            perdoc={p:next(d['metrics'] for d in result['documents'] if d['document']==doc['id'] and d['parser']==p) for p in b.PARSERS}
            page+=f'<h2>{e(doc["title"])}</h2>'+definitions.metric_table(perdoc,group['primary'])
        failures=[r for r in checks if r['parser']==PARSER and r['metric'] in names and r.get('passed') is False]
        page+=f'<h2>PaddleOCR failed checks ({len(failures)})</h2>'
        for r in failures:
            page+=f'<details><summary>{e(r["metric"])} · {e(r["label_id"])}</summary><pre>{e(json.dumps(r.get("detail"),ensure_ascii=False,indent=2))}</pre></details>'
        (out/(key+'.html')).write_text(page+finish())
    comparison=start('Same source page across all five pipelines')
    for docid,pno,title in renderer.EXAMPLES:
        comparison+=f'<h2 id="{docid}-p{pno}">{e(title)} · {e(docid)} · PDF page {pno}</h2><img style="max-width:650px;width:100%" src="assets/{docid}_{pno}.png" alt="Original PDF page">'
        comparison+='<div class="predictions">'
        for parser in b.PARSERS:
            work=prediction_dir(docid,parser)
            pages=b.read_json(work/'pages.json')['pages']
            text=next(p['markdown'] for p in pages if p['page']==pno)
            comparison+=f'<article class="prediction"><h3>{NAMES[parser]}</h3><a href="{href(work/"document.md")}">Saved Markdown</a><div class="parsed">{render_prediction(text,work,renderer)}</div><details><summary>Exact page Markdown</summary><pre>{e(text)}</pre></details></article>'
        comparison+='</div>'
    (out/'comparison.html').write_text(comparison+finish())
    outputs=start('Saved parsed outputs')
    for doc in docs:
        outputs+=f'<h2>{e(doc["title"])} · {doc["pages"]} pages</h2><table><tr><th>Parser</th><th>Files</th></tr>'
        for parser in b.PARSERS:
            work=prediction_dir(doc['id'],parser)
            links=' · '.join(f'<a href="{href(work/file)}">{name}</a>' for file,name in [('document.md','Markdown'),('pages.json','Pages'),('raw.md','Raw'),('metadata.json','Metadata'),('run.json','Run')])
            count=len(b.read_json(work/'pages.json')['pages'])
            outputs+=f'<tr><th>{NAMES[parser]} · {count}/{doc["pages"]} source pages</th><td>{links}</td></tr>'
        outputs+='</table>'
    (out/'outputs.html').write_text(outputs+finish())
    source=start('Unchanged Sam reference labels')
    for doc in docs:
        for pno in sorted({l['page'] for l in labels if l['document']==doc['id']}):
            source+=f'<h2>{e(doc["id"])} · PDF page {pno}</h2><img style="max-width:650px;width:100%" src="assets/{doc["id"]}_{pno}.png" alt="Original source page">'
            source+=''.join(definitions.label_card(l) for l in labels if l['document']==doc['id'] and l['page']==pno)
    (out/'labels.html').write_text(source+finish())
    lines=['# Measured PaddleOCR comparison','','Same 54 preliminary references, unchanged scoring logic. Six hash-identical PDFs / 140 source pages; selected labels on 18 pages.','',coverage_note,'','| Metric | '+' | '.join(NAMES[p] for p in b.PARSERS)+' |','|---|'+'---|'*len(b.PARSERS)]
    for name in main_metrics:
        values=[result['aggregate'][p][name] for p in b.PARSERS]
        lines.append('| '+definitions.METRICS[name][0]+' | '+' | '.join(f'{v["passed"]}/{v["total"]} ({v["value"]:.1%})' for v in values)+' |')
    lines+=['','[Visual comparison](review/comparison.html) · [Saved outputs](review/outputs.html) · [Detailed JSON](results/preliminary.json) · [CSV](results/metrics.csv).','','Paddle configuration: PP-StructureV3 with PP-OCRv5 mobile detection/recognition and standard layout/table models; CPU, four Paddle math threads, 300 DPI renders, 1,280-pixel detector limit for macOS compatibility. Notes, headers and footers are retained. This is a measurement of this specific configuration, not the server-OCR preset.','','Historical runtimes are from different hardware. Selected-page processing is not a full-document speed comparison. Reference labels are assistant-authored drafts, and no overall parser ranking is claimed.']
    (ROOT/'REPORT.md').write_text('\n'.join(lines)+'\n')
    print(out/'index.html')


if __name__=='__main__':
    main()
