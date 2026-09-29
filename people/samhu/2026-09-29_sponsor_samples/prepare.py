"""Download public sponsor PDFs; validate bytes and retain source provenance."""
import hashlib
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
import pymupdf

ROOT = Path(__file__).resolve().parent

def main():
    destination = ROOT / 'inputs'
    destination.mkdir(exist_ok=True)
    records = []
    for source in json.loads((ROOT / 'sources.json').read_text()):
        path = destination / (source['id'] + '.pdf')
        record = dict(source)
        try:
            if not path.exists():
                for attempt in range(3):
                    try:
                        request = urllib.request.Request(source['url'], headers={'User-Agent': 'Mozilla/5.0'})
                        with urllib.request.urlopen(request, timeout=90) as response:
                            content = response.read(100 * 1024 * 1024 + 1)
                        if len(content) > 100 * 1024 * 1024 or not content.startswith(b'%PDF-'):
                            raise ValueError('Not a PDF or larger than 100 MiB')
                        with pymupdf.open(stream=content, filetype='pdf') as doc:
                            if not len(doc):
                                raise ValueError('Empty PDF')
                        path.write_bytes(content)
                        break
                    except Exception:
                        if attempt == 2:
                            raise
                        time.sleep(2 ** attempt)
            with pymupdf.open(path) as doc:
                record.update(status='success', pages=len(doc), metadata=doc.metadata,
                              outline=doc.get_toc(), native_text_chars=[len(p.get_text().strip()) for p in doc])
            record.update(sha256=hashlib.sha256(path.read_bytes()).hexdigest(), bytes=path.stat().st_size)
        except Exception as error:
            record.update(status='failed', error=str(error))
        record['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
        records.append(record)
        (ROOT / 'source_manifest.json').write_text(json.dumps(records, indent=2) + '\n')
        print(source['id'], record['status'], record.get('pages', record.get('error')), flush=True)
    if any(r['status'] != 'success' for r in records):
        raise SystemExit(1)

if __name__ == '__main__':
    main()
