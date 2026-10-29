"""Rebuild common exports from retained raw predictions without rerunning models."""
import hashlib
import json
from datetime import datetime, timezone
from parse import ROOT, block_md, dump, export_pages


def main():
    sources = {s['id']:s for s in json.loads((ROOT/'source_manifest.json').read_text())}
    for path in sorted((ROOT/'results').glob('*/*/run.json')):
        run = json.loads(path.read_text())
        if run['status'] not in ('success','partial','empty'):
            continue
        work = path.parent
        source = sources[run['document']]
        if run['parser']=='pymupdf4llm':
            raw=json.loads((work/'raw_chunks.json').read_text())
            chunks=[dict(text=c['text'],native={k:v for k,v in c.items() if k!='text'}) for c in raw]
        else:
            raw=json.loads((work/'raw_content_list.json').read_text())
            chunks=[dict(text='\n\n'.join(block_md(x) for x in raw if x['page_idx']==i), native=dict(page_idx=i)) for i in range(run['parsed_pages'])]
        assert len(chunks)==source['pages']
        pages=export_pages(work,chunks,source,run['parser'])
        nonempty=sum(p['text_chars']>0 for p in pages)
        run.update(nonempty_pages=nonempty,status='success' if nonempty==len(pages) else ('empty' if not nonempty else 'partial'),
                   document_sha256=hashlib.sha256((work/'document.md').read_bytes()).hexdigest(),
                   exported_at_utc=datetime.now(timezone.utc).isoformat())
        dump(path,run)
        print(run['document'],run['parser'],run['status'])

if __name__=='__main__':
    main()
