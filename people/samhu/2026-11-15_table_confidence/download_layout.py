"""Fetch the team's already-pinned detector, checking every file hash."""
import hashlib
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent
NAME = 'PP-DocLayout_plus-L'


def main():
    manifest = ROOT.parents[1] / 'mc8/2026-10-28_paddleocr/model_sources.json'
    record = next(r for r in json.loads(manifest.read_text()) if r['model'] == NAME)
    folder = ROOT / 'work/models' / NAME
    folder.mkdir(parents=True, exist_ok=True)
    for name, info in record['files'].items():
        path = folder / name
        if not path.exists():
            url = f"https://huggingface.co/{record['repository']}/resolve/{record['revision']}/{name}"
            tmp = path.with_suffix(path.suffix + '.part')
            with urllib.request.urlopen(url, timeout=120) as response, tmp.open('wb') as out:
                while block := response.read(1024 * 1024):
                    out.write(block)
            if hashlib.sha256(tmp.read_bytes()).hexdigest() != info['sha256']:
                raise ValueError(f'Hash mismatch: {name}')
            tmp.replace(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != info['sha256']:
            raise ValueError(f'Cached model changed: {name}')
        print('Verified', name, flush=True)
    (folder / 'provenance.json').write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    main()
