"""Download Sam's exact PDFs, rejecting changed bytes before any parsing."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import time
import urllib.request

ROOT = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fetch(url, path, expected_hash=None):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if expected_hash and sha(path) != expected_hash:
            raise ValueError(f'Existing file hash mismatch: {path}')
        return path
    temporary = path.with_suffix(path.suffix + '.part')
    try:
        for attempt in range(3):
            try:
                request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(request, timeout=90) as response, temporary.open('wb') as out:
                    total = 0
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > 200 * 1024 * 1024:
                            raise ValueError('Download exceeds 200 MiB')
                        out.write(chunk)
                if expected_hash and sha(temporary) != expected_hash:
                    raise ValueError(f'Upstream bytes changed: {url}')
                temporary.replace(path)
                return path
            except (OSError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
    finally:
        temporary.unlink(missing_ok=True)


def sponsors(local_inputs=None):
    import pymupdf
    sources = json.loads((ROOT / 'source_manifest.json').read_text())
    audit = []
    for source in sources:
        record = dict(document=source['id'], expected_sha256=source['sha256'])
        try:
            path = ROOT / 'inputs' / (source['id'] + '.pdf')
            local = Path(local_inputs) / path.name if local_inputs else None
            if not path.exists() and local and local.is_file():
                if sha(local) != source['sha256']:
                    raise ValueError(f'Local input differs from Sam: {local}')
                path.parent.mkdir(exist_ok=True)
                shutil.copy2(local, path)
            fetch(source['url'], path, source['sha256'])
            if not path.read_bytes().startswith(b'%PDF-'):
                raise ValueError('Not a PDF')
            with pymupdf.open(path) as pdf:
                if len(pdf) != source['pages']:
                    raise ValueError('Physical PDF page count mismatch')
                record.update(status='success', pages=len(pdf), actual_sha256=sha(path))
        except Exception as exc:
            record.update(status='failed', error=repr(exc))
        audit.append(record)
        (ROOT / 'input_verification.json').write_text(json.dumps(audit, indent=2) + '\n')
        print(source['id'], record['status'], record.get('pages', record.get('error')), flush=True)
    return all(r['status'] == 'success' for r in audit)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--local-inputs', type=Path)
    args = cli.parse_args()
    if not sponsors(args.local_inputs):
        raise SystemExit(1)
