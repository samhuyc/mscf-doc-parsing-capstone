"""Build a portable visual review of source pages and all parser outputs."""
import html
import json
import os
import sys
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / '2026-09-20_evaluation'))
from formats import MARKDOWN, plain_text
from bs4 import BeautifulSoup

LABELS = {'mineru_ocr': 'MinerU OCR', 'mineru_vlm': 'MinerU local VLM',
          'pymupdf4llm': 'PyMuPDF4LLM — no OCR'}


def main():
    out = ROOT / 'evaluation'
    images = out / 'source_pages'
    images.mkdir(parents=True, exist_ok=True)
    checks = json.loads((ROOT / 'checks.json').read_text())['checks']
    selections = sorted({(c['document'],c['page']) for c in checks})
    # Load every export before publishing: missing runs must not silently become
    # blank panes in an apparently finished comparison.
    exports = {}
    runs = {}
    for name in sorted({name for name, _ in selections}):
        for parser in LABELS:
            work = ROOT / 'results' / name / parser
            exports[name, parser] = json.loads((work / 'pages.json').read_text())['pages']
            runs[name, parser] = json.loads((work / 'run.json').read_text())
            run = runs[name, parser]
            if run['status'] not in ('success', 'partial', 'empty') or len(exports[name, parser]) != run['expected_pages']:
                raise ValueError(f'Incomplete export: {name}/{parser}')
    parts = ['''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Sponsor PDF parser comparison</title><style>
body{font:15px/1.5 system-ui;margin:24px;color:#172a3a;background:#f3f5f7}h1{font-size:30px}section{margin:30px 0} .grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.pane{background:white;padding:14px;border:1px solid #ccd3dc;overflow:auto;max-height:850px;min-width:0}.pane:target{outline:3px solid #2764ad}img{max-width:100%}table{border-collapse:collapse;font-size:11px}td,th{border:1px solid #abb6c3;padding:4px;min-width:35px}h3{font-size:17px}.checks{background:#e8edf4;padding:12px}.summary{font-size:14px}a{color:#17528c} @media(max-width:1100px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}} @media(max-width:650px){.grid{grid-template-columns:1fr}}
</style><h1>Sponsor PDF parser comparison</h1><p>Review format v2 · Six source pages · Original parser predictions · Physical PDF page numbers. Values are not repaired. See <a href="../REPORT.md">REPORT.md</a> for pipeline setups, runtime and metric definitions.</p>''']
    parts.append(f'<p class="checks"><strong>{len(exports)}/{len(selections) * len(LABELS)} document/parser exports loaded, including all six MinerU VLM results.</strong> Text and tables are embedded in this HTML; only images use adjacent files. This review shows one checked page per document. Links below each parser heading open its full output.</p>')
    parts.append('<table class="summary"><thead><tr><th>Pipeline</th><th>Completed exports</th><th>Pages with extracted text</th></tr></thead><tbody>')
    for parser, label in LABELS.items():
        group = [pages for (name, p), pages in exports.items() if p == parser]
        pages = [page for document in group for page in document]
        nonempty = sum(bool(plain_text(page['markdown']).strip()) for page in pages)
        parts.append(f'<tr><td>{label}</td><td>{len(group)}</td><td>{nonempty}/{len(pages)}</td></tr>')
    parts.append('</tbody></table><p>Order: Source → MinerU OCR → MinerU VLM → PyMuPDF4LLM. On narrower windows, panels wrap onto more rows; each long panel scrolls independently. An image-only PyMuPDF result has no OCR transcription.</p>')
    for name, page in selections:
        image = images / f'{name}_{page:03d}.png'
        with pymupdf.open(ROOT / 'inputs' / (name+'.pdf')) as doc:
            doc[page-1].get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(image)
        relevant = [c for c in checks if c['document']==name and c['page']==page]
        text = '; '.join(c['label']+': '+', '.join(c['values']) for c in relevant)
        parts.append(f'<section><h2>{html.escape(name)} · page {page}</h2><p><a href="#{name}-mineru_vlm">Jump to this page’s VLM result</a></p><p class="checks">Source checks: {html.escape(text)}</p><div class="grid"><div class="pane"><h3>Source</h3><a href="source_pages/{image.name}"><img src="source_pages/{image.name}" alt="Source page {page}"></a></div>')
        for parser, label in LABELS.items():
            work = ROOT / 'results' / name / parser
            md = exports[name, parser][page-1]['markdown']
            soup = BeautifulSoup(MARKDOWN.render(md), 'html.parser')
            for tag in soup(['script','style','iframe']):
                tag.decompose()
            for tag in soup.find_all('img'):
                src = tag.get('src','')
                if not src.startswith(('http:', 'https:', 'data:')):
                    tag['src'] = os.path.relpath(work / src, out)
            chars = len(plain_text(md))
            tables = len(soup.find_all('table'))
            status = f'{chars:,} transcribed characters; {tables} HTML tables.' if chars else 'No transcribed text. Any image below is a source crop, not OCR output.'
            links = ' · '.join(f'<a href="{os.path.relpath(work / filename, out)}">{title}</a>' for filename, title in [('document.md', 'Full Markdown'), ('pages.json', 'Page JSON'), ('run.json', 'Run settings')])
            parts.append(f'<div class="pane" id="{name}-{parser}"><h3>{label}</h3><p>{links}</p><p class="checks">{status}</p>{soup if md.strip() else "<p>Export exists but this page has no extracted content.</p>"}</div>')
        parts.append('</div></section>')
    parts.append('</html>')
    (out / 'REVIEW.html').write_text(''.join(parts))

if __name__ == '__main__':
    main()
