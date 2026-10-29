"""Offline four-pipeline page examples, full-output index and concise summary."""
from html import escape as e
import os
from pathlib import Path
from urllib.parse import quote, urlsplit
from bs4 import BeautifulSoup
from benchmark import ROOT, PARSERS, MD, read_json, read_jsonl, prediction_dir

# Source examples selected for document/layout diversity, not scores.
EXAMPLES = [('peterborough_2025',2,'Scanned balance sheet'),
            ('hippodrome_2025',21,'Scanned table exported as a picture'),
            ('cvs_2025q2',6,'Digital financial slide'),
            ('edf_2024',3,'Nested table headers'),
            ('rolls_royce_2026h1_presentation',9,'Financial presentation'),
            ('rolls_royce_2026h1_release',13,'Financial release')]


def href(path, base=None):
    return quote(os.path.relpath(path, base or ROOT/'review'), safe='/')


def rendered(markdown, directory):
    """Allowlist saved model output before embedding; preserve table spans only."""
    soup=BeautifulSoup(MD.render(markdown),'html.parser')
    allowed={'p','br','hr','h1','h2','h3','h4','h5','h6','strong','b','em','i','ul','ol','li',
             'span','table','thead','tbody','tfoot','tr','th','td','blockquote','pre','code','img','a','sup','sub'}
    for tag in list(soup.find_all(True)):
        if tag.parent is None:
            continue
        if tag.name not in allowed:
            tag.decompose()
            continue
        attrs={}
        if tag.name in {'td','th'}:
            for key in ('rowspan','colspan'):
                value=str(tag.get(key,''))
                if value.isdigit() and 0<int(value)<=1000:
                    attrs[key]=value
        if tag.name=='img':
            source=tag.get('src','')
            target=(directory/source).resolve()
            if urlsplit(source).scheme or not target.is_relative_to(directory.resolve()) or not target.is_file():
                tag.decompose();continue
            attrs={'src':href(target),'alt':str(tag.get('alt','Extracted image')),'loading':'lazy'}
        if tag.name=='a':
            # Untrusted model-created links are displayed as text, not active links.
            tag.unwrap();continue
        tag.attrs=attrs
    return str(soup)


def build():
    from report import NAMES, METRICS, page_start, page_end, metric_table
    result=read_json(ROOT/'results/preliminary.json')
    checks=read_jsonl(ROOT/'results/preliminary_checks.jsonl')
    docs=read_json(ROOT/'documents.json')
    labels=read_jsonl(ROOT/'labels.jsonl')
    byid={d['id']:d for d in docs}
    verified=sum(x['review_status'] in {'human_verified','adjudicated'} for x in labels)
    page=page_start('Same page, four pipelines','comparison',verified,len(labels))
    page+='''<style>.comparison-source{max-width:650px;margin:20px auto}.comparison-source img{width:100%}.predictions{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.prediction{min-width:0}.prediction .parsed{max-height:620px;overflow:auto;border:1px solid #ccd8d3;padding:14px;font-size:13px;background:#fff}.parsed img{max-width:100%}.parsed h1{font-size:22px}.parsed h2{font-size:19px}.parsed table{font-size:11px}.example{border-top:3px solid #234e49;margin-top:40px;padding-top:15px}@media(max-width:850px){.predictions{display:block}}</style>
    <p>Original page, selected-reference checks, then the four canonical page exports without value corrections. Examples span all six sources; they are illustrative, not a random sample. Table structure is rendered; raw Markdown remains available. Scroll inside each output to see its complete page.</p>'''
    page+='<p>'+ ' · '.join(f'<a href="#{d}-p{n}">{e(title)}</a>' for d,n,title in EXAMPLES)+'</p>'
    for docid,pno,title in EXAMPLES:
        page+=f'<section class="example" id="{docid}-p{pno}"><h2>{e(title)}</h2><p>{e(byid[docid]["title"])} · physical PDF page {pno}</p>'
        page+=f'<div class="comparison-source"><a href="assets/{docid}_{pno}.png"><img loading="lazy" src="assets/{docid}_{pno}.png" alt="Original PDF page {pno}"></a></div>'
        from benchmark import summarize
        aggregates={p:summarize([r for r in checks if r['document']==docid and r['page']==pno and r['parser']==p]) for p in PARSERS}
        page+=metric_table(aggregates,['associated_value_accuracy','selected_value_presence'])
        if docid == 'cvs_2025q2':
            page+='<div class="card"><b>What to inspect</b><p>All four outputs retain the ten labeled amounts. MinerU VLM places the year headings in prose above its table, so the strict association check cannot connect the values to those years. The new PyMuPDF VLM backend reads two graphic regions on this page; the main financial text already exists in the PDF. Compare the small graphics and headings as well as the table.</p></div>'
        if docid == 'hippodrome_2025':
            page+='<div class="card"><b>What to inspect</b><p>This page explains all six additional cell-association failures versus Tesseract. The VLM recognizes the labeled amounts, but the subsequent PyMuPDF layout/export represents the financial-position table as an image plus flat picture text. The scorer finds no explicit table, so 0/6 cell associations pass while all six amounts remain present. The displayed image is a retained source crop, not a structured extracted table.</p></div>'
        if docid == 'edf_2024':
            page+='<div class="card"><b>What to inspect</b><p>Look at the Electricity/Gas and Domestic/Non Domestic header hierarchy. MinerU OCR merges several row labels and values. Both PyMuPDF variants retain the selected financial cells here using the native text layer; small logo/graphic regions still invoke OCR. Passing selected cells does not mean every row is exported separately.</p></div>'
        if docid == 'peterborough_2025':
            page+='<div class="card"><b>What to inspect</b><p>The source places some detail amounts to the left of each year’s total column. MinerU VLM exports these into one column per year. Both PyMuPDF exports keep separate detail/total columns, so the strict scorer misses some year associations despite retaining the amounts. The VLM OCR output also reads note number 7 as a mathematical symbol; that error is preserved, not corrected.</p></div>'
        page+='<p>These counts cover selected labels on this page. A missing/ambiguous row or header fails association even when the number survives. The source image is the visual authority.</p><div class="predictions">'
        for parser in PARSERS:
            directory=prediction_dir(docid,parser)
            pages=read_json(directory/'pages.json')['pages']
            prediction=next(x['markdown'] for x in pages if x['page']==pno)
            run=read_json(directory/'run.json')
            if parser=='pymupdf4llm_vlm':
                mode='VLM OCR used' if pno in run.get('vlm_pages',[]) else 'Native text retained; no VLM recognition on this page'
            elif parser=='pymupdf4llm':
                mode='Tesseract callback invoked' if pno in run.get('ocr_pages',[]) else 'Native text retained; no Tesseract callback'
            else:
                mode='Full MinerU OCR pipeline' if parser=='mineru_ocr' else 'Full MinerU VLM pipeline'
            page+=f'<article class="prediction"><h3>{e(NAMES[parser])}</h3><p><small>{e(mode)}</small> · <a href="{href(directory/"document.md")}">Full document</a></p><div class="parsed">{rendered(prediction,directory)}</div><details><summary>Exact page Markdown</summary><pre>{e(prediction)}</pre></details></article>'
        page+='</div></section>'
    (ROOT/'review/comparison.html').write_text(page+page_end())
    output=page_start('Full parsed results','outputs',verified,len(labels))
    output+='<p>All six complete PDFs, all four pipelines. <b>Document</b> is the full readable Markdown; <b>Pages</b> is the page-level JSON; <b>Run</b> records settings, hashes and timing. Keep the linked image folders beside each document.</p><p>The three September outputs remain in their original folders. The new PyMuPDF4LLM + VLM output is under <code>results/parsed/</code> in this October 5 evaluation folder.</p>'
    lines=['# Four-pipeline results — October 6 addition','','Start with [page comparisons](../review/comparison.html) or [all full parsed results](../review/outputs.html).','','The original three parser exports and all 54 October 5 labels are unchanged. These are preliminary assistant-authored references, not independently verified gold. Six PDFs / 140 pages per pipeline; 18 pages have selected labels. No overall ranking.','','| Metric | '+' | '.join(NAMES[p] for p in PARSERS)+' |','|---|'+'---|'*len(PARSERS)]
    metrics=['associated_value_accuracy','selected_value_presence','negative_value_accuracy','text_span_retention','footnote_text_retention','reading_order_accuracy']
    for metric in metrics:
        cells=[]
        for parser in PARSERS:
            m=result['aggregate'][parser][metric]
            cells.append(f"{m['passed']}/{m['total']} ({m['value']:.1%})" if m['value'] is not None else 'N/A')
        lines.append('| '+METRICS[metric][0]+' | '+' | '.join(cells)+' |')
    new_assoc=result['aggregate']['pymupdf4llm_vlm']['associated_value_accuracy']
    old_assoc=result['aggregate']['pymupdf4llm']['associated_value_accuracy']
    new_presence=result['aggregate']['pymupdf4llm_vlm']['selected_value_presence']
    old_presence=result['aggregate']['pymupdf4llm']['selected_value_presence']
    lines+=['',f"The VLM-backed PyMuPDF pipeline resolves **{new_assoc['passed']}/{new_assoc['total']}** selected cells correctly, versus **{old_assoc['passed']}/{old_assoc['total']}** with Tesseract. Selected-number retention is **{new_presence['passed']}/{new_presence['total']}**, versus **{old_presence['passed']}/{old_presence['total']}**. These compare the saved configurations, not an isolated recognition-model ablation.",
            '', 'The six-cell association gap comes entirely from Hippodrome PDF page 21: the new pipeline exports the table as a picture with flat text, while Tesseract produces an explicit table. The amounts survive, but their table structure does not. The 4/5 footnote result is triggered by a missing final period in the Peterborough page 3 note; its words are retained.',
            '', 'Concrete example: on Peterborough PDF page 2, both PyMuPDF variants retain 12/12 labeled amounts but associate only 8/12 with the expected year. Separate detail/total columns remain a layout issue. The new VLM also misreads note 7 as a mathematical symbol; see the unedited comparison.']
    lines+=['','Counts are selected checks, not whole-document accuracy. Exact row/header matching and explicit table structure are required for cell association. Presence can pass even when association fails.','','## What changed','','The new pipeline calls PyMuPDF4LLM 1.28.2 with `ocr_function`. Its standard OCR helper removes good native text from the rendered image, calls PP-OCRv6 **detection only**, uses the local MinerU2.5-Pro-2605-1.2B VLM to recognize each detected crop, and inserts the result at the detected coordinates. PyMuPDF Layout then performs layout/table extraction and Markdown export. No Paddle text recognizer, Tesseract recognition, prior MinerU outputs or reference labels supply its recognized text.','','This is a custom crop-recognition configuration, not MinerU’s default page parsing pipeline. Its quality depends on detection boxes, crop recognition and PyMuPDF’s text placement/layout. Automatic OCR (`force_ocr=False`, 300 DPI) matches the existing Tesseract routing policy; native-text pages may bypass OCR.','','| Document | Pages | Tesseract callback pages | VLM recognition pages | VLM recognized regions |','|---|---:|---:|---:|---:|']
    for doc in docs:
        output+=f'<h2>{e(doc["title"])}</h2><p>{doc["pages"]} physical PDF pages</p><div class="scroll"><table><tr><th>Pipeline</th><th>Complete outputs</th><th>Coverage</th></tr>'
        for parser in PARSERS:
            directory=prediction_dir(doc['id'],parser)
            run=read_json(directory/'run.json')
            links=' · '.join(f'<a href="{href(directory/file)}">{name}</a>' for file,name in [('document.md','Document'),('pages.json','Pages'),('raw.md','Raw'),('run.json','Run')])
            if parser=='pymupdf4llm_vlm':
                links+=f' · <a href="{href(directory/"ocr_pages.json")}">OCR audit</a>'
            output+=f'<tr><th>{e(NAMES[parser])}</th><td>{links}</td><td>{run.get("parsed_pages",0)}/{doc["pages"]} pages · {e(run["status"])}</td></tr>'
        output+='</table></div>'
        new=read_json(prediction_dir(doc['id'],'pymupdf4llm_vlm')/'run.json')
        old=read_json(prediction_dir(doc['id'],'pymupdf4llm')/'run.json')
        lines.append(f'| {doc["title"]} | {doc["pages"]} | {len(old.get("ocr_pages",[]))} | {len(new.get("vlm_pages",[]))} | {new.get("recognized_regions",0)} |')
    (ROOT/'review/outputs.html').write_text(output+page_end())
    lines+=['','## Files and reproduction','','- [Full parsed document index](../review/outputs.html): all 24 complete document exports.','- [Same-page examples](../review/comparison.html): six source pages with all four predictions and selected checks.','- [Detailed scores](preliminary.json) and [individual checks](preliminary_checks.jsonl).','- [Original October 5 summary](baseline_2026-10-05.json) preserves the three-pipeline snapshot.','- New raw crop predictions: `parsed/<document>/pymupdf4llm_vlm/ocr/page_NNN.json`.','- [Method and commands](../VLM_ADDITION.md).','','Historical timings are not a controlled speed comparison. New runs include local model loading; scoring/report generation uses saved predictions only. No hosted inference is used.']
    (ROOT/'results/SUMMARY.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':
    build()
