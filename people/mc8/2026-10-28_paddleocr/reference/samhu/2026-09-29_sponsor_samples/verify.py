"""Validate completeness, hashes, page indices and portable image references."""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def main():
    sources = json.loads((ROOT / 'source_manifest.json').read_text())
    errors = []
    checked = 0
    for source in sources:
        for parser in ('mineru_ocr','mineru_vlm','pymupdf4llm'):
            work = ROOT / 'results' / source['id'] / parser
            try:
                run = json.loads((work/'run.json').read_text())
                pages = json.loads((work/'pages.json').read_text())['pages']
                md = (work/'document.md').read_text()
                assert run['status'] in ('success','partial','empty'), run['status']
                assert run['input_sha256'] == source['sha256']
                assert run['document_sha256'] == hashlib.sha256((work/'document.md').read_bytes()).hexdigest()
                assert [p['page'] for p in pages] == list(range(1,source['pages']+1))
                assert len(pages) == run['parsed_pages'] == source['pages']
                assert run['nonempty_pages'] == sum(p['text_chars']>0 for p in pages)
                if parser == 'pymupdf4llm':
                    assert run['settings']['ocr'] is True
                    assert run['settings']['layout'] is True
                    audit = json.loads((work/'ocr_pages.json').read_text())['pages']
                    assert run['ocr_pages'] == [p['page'] for p in audit]
                    assert len(set(run['ocr_pages'])) == len(audit)
                    assert all(1 <= p['page'] <= source['pages'] for p in audit)
                    if not any(source['native_text_chars']):
                        assert run['ocr_pages'] == list(range(1, source['pages']+1)), 'Scan pages skipped OCR'
                        assert all(p['text_chars_after'] > 0 for p in audit), 'OCR returned empty scan text'
                for path in re.findall(r'!\[[^\]]*\]\(([^)]+)\)', md):
                    path = path.strip('<>')
                    assert not Path(path).is_absolute(), f'Nonportable image: {path}'
                    assert (work/path).is_file(), f'Missing image: {path}'
                checked += 1
            except Exception as error:
                errors.append(f'{source["id"]}/{parser}: {error}')
    record = dict(checked_runs=checked, expected_runs=len(sources)*3, errors=errors)
    (ROOT/'evaluation/validation.json').write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))
    if errors:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
