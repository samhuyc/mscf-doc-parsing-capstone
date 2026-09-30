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


def main():
    out = ROOT / 'evaluation'
    images = out / 'source_pages'
    images.mkdir(parents=True, exist_ok=True)
    checks = json.loads((ROOT / 'checks.json').read_text())['checks']
    selections = sorted({(c['document'],c['page']) for c in checks})
    parts = ['''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Sponsor PDF parser comparison</title><style>
body{font:15px/1.5 system-ui;margin:24px;color:#172a3a;background:#f3f5f7}h1{font-size:30px}section{margin:30px 0} .grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.pane{background:white;padding:14px;border:1px solid #ccd3dc;overflow:auto;max-height:850px}img{max-width:100%}table{border-collapse:collapse;font-size:11px}td,th{border:1px solid #abb6c3;padding:4px;min-width:35px}h3{font-size:17px}.checks{background:#e8edf4;padding:12px} @media(max-width:1100px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
</style><h1>Sponsor PDF parser comparison</h1><p>Six source pages · Original parser predictions · Physical PDF page numbers. Values are not repaired. See REPORT.md for runtime and metric definitions.</p>''']
    for name, page in selections:
        image = images / f'{name}_{page:03d}.png'
        with pymupdf.open(ROOT / 'inputs' / (name+'.pdf')) as doc:
            doc[page-1].get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(image)
        relevant = [c for c in checks if c['document']==name and c['page']==page]
        text = '; '.join(c['label']+': '+', '.join(c['values']) for c in relevant)
        parts.append(f'<section><h2>{html.escape(name)} · page {page}</h2><p class="checks">Source checks: {html.escape(text)}</p><div class="grid"><div class="pane"><h3>Source</h3><a href="source_pages/{image.name}"><img src="source_pages/{image.name}" alt="Source page {page}"></a></div>')
        for parser in ('mineru_ocr','mineru_vlm','pymupdf4llm'):
            work = ROOT / 'results' / name / parser
            file = work / 'pages.json'
            md = ''
            if file.exists():
                md = json.loads(file.read_text())['pages'][page-1]['markdown']
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
            parts.append(f'<div class="pane"><h3>{parser}</h3><p class="checks">{status}</p>{soup if md.strip() else "<p>No output available.</p>"}</div>')
        parts.append('</div></section>')
    parts.append('</html>')
    (out / 'REVIEW.html').write_text(''.join(parts))

if __name__ == '__main__':
    main()
