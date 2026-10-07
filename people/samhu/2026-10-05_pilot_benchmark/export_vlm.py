"""Rebuild portable canonical exports from raw chunks; never rerun recognition."""
import hashlib
import json
from pathlib import Path
import re
import sys
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT.parent/'2026-09-29_sponsor_samples'
sys.path.insert(0,str(SOURCE))
from parse import dump, export_pages


def portable_markdown(text, work):
    # PyMuPDF may emit absolute paths or paths relative to its process cwd.
    # Only rewrite image destinations belonging to this document's image folder.
    def replace(match):
        target=match[2].strip('<>')
        image_prefix=str(work.relative_to(ROOT))+'/images/'
        if target.startswith(str(work)+'/images/') or target.startswith(image_prefix):
            destination='images/'+target.rsplit('/images/',1)[1]
            if not (work/destination).is_file():
                raise ValueError('Missing exported image: '+destination)
            return match[1]+destination+')'
        return match[0]
    return re.sub(r'(!\[[^\]]*\]\()([^)]+)\)',replace,text)


def main():
    sources={s['id']:s for s in json.loads((SOURCE/'source_manifest.json').read_text())}
    for path in sorted((ROOT/'results/parsed').glob('*/pymupdf4llm_vlm/run.json')):
        run=json.loads(path.read_text())
        if run['status']!='success':
            raise ValueError('Incomplete run: '+str(path))
        work=path.parent;raw=json.loads((work/'raw_chunks.json').read_text())
        chunks=[dict(text=portable_markdown(c['text'],work),native={k:v for k,v in c.items() if k!='text'}) for c in raw]
        pages=export_pages(work,chunks,sources[run['document']],run['parser'])
        run.update(document_sha256=hashlib.sha256((work/'document.md').read_bytes()).hexdigest(),
                   nonempty_pages=sum(p['text_chars']>0 for p in pages),
                   export_adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                   export_note='Canonical conversion plus portable image destinations only; raw OCR and raw chunks unchanged.',
                   exported_at_utc=datetime.now(timezone.utc).isoformat())
        dump(path,run)
        print(run['document'],'portable export')

if __name__=='__main__':
    main()
