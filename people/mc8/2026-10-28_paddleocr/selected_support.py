"""Resume page checkpoints and preserve physical IDs through Sam's exporter."""
import hashlib
import json
from pathlib import Path
import re

from common import PARSER, dump, export_pages


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_dump(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    dump(temporary, value)
    temporary.replace(path)


def portable_markdown(work, number, markdown):
    images = work / 'images' / f'page_{number:03}'
    # The original worker changes only crop paths. Reconstruct that exact change
    # from its untouched native Markdown and already saved per-page crops.
    names = re.findall(r'!\[[^\]]*\]\(([^)]+)\)|src=[\"\']([^\"\']+)', markdown)
    for pair in names:
        name = next(value for value in pair if value)
        target = images / Path(name).name
        if target.is_file():
            markdown = markdown.replace(name, str(target.relative_to(work)))
    return markdown


def checkpoints(work):
    """Read only committed complete pages; never run inference during recovery."""
    result = {}
    progress = work / 'progress.json'
    if progress.is_file():
        for audit in json.loads(progress.read_text())['pages']:
            number = audit['page']
            raw = work / audit['raw_prediction']
            if sha(raw) != audit['raw_sha256']:
                raise ValueError(f'Original checkpoint hash mismatch: {raw}')
            native = json.loads(raw.read_text())
            payload = native.get('res', native)
            markdown = (work/'raw'/f'page_{number:03}.md').read_text()
            result[number] = dict(audit=audit, chunk=dict(
                text=portable_markdown(work, number, markdown),
                native=dict(page_index=number-1, raw_prediction=audit['raw_prediction'],
                            parsing_res_list=payload.get('parsing_res_list', []))),
                provenance='original_full_document_checkpoint')
    for path in sorted((work/'page_checkpoints').glob('page_*.json')):
        entry = json.loads(path.read_text())
        number = entry['audit']['page']
        if number in result:
            raise ValueError(f'Duplicate completed checkpoint for physical page {number}')
        if sha(work/entry['audit']['raw_prediction']) != entry['audit']['raw_sha256']:
            raise ValueError(f'New checkpoint hash mismatch: {path}')
        if sha(work/'raw'/f'page_{number:03}.md') != entry['raw_markdown_sha256']:
            raise ValueError(f'Native Markdown hash mismatch: {path}')
        result[number] = entry
    return result


def export_sparse(work, completed, source):
    """Use Sam's exact canonicalization, retaining original physical numbering."""
    ids = sorted(completed)
    if not ids or not all(1 <= number <= source['pages'] for number in ids):
        raise ValueError('Invalid completed page IDs')
    # His exporter numbers chunks consecutively. Empty temporary slots maintain
    # physical IDs and heading metadata; remove all unprocessed slots afterward.
    chunks = [completed[i]['chunk'] if i in completed else dict(text='', native=None)
              for i in range(1, source['pages']+1)]
    pages = export_pages(work, chunks, source)
    pages = [p for p in pages if p['page'] in completed]
    data = json.loads((work/'pages.json').read_text())
    data.update(pages=pages, coverage=dict(source_pages=source['pages'], processed_pages=ids,
                unprocessed_pages=[i for i in range(1,source['pages']+1) if i not in completed],
                note='Only actual predictions are exported. Page IDs remain 1-based physical PDF pages.'))
    atomic_dump(work/'pages.json', data)
    (work/'document.md').write_text('\n\n'.join(f'<!-- source page {p["page"]} -->\n\n{p["markdown"]}' for p in pages))
    dump(work/'raw_chunks.json', [dict(**completed[i]['chunk'], physical_page=i) for i in ids])
    (work/'raw.md').write_text('\n\n'.join(completed[i]['chunk']['text'] for i in ids))
    dump(work/'ocr_pages.json', dict(engine='PaddleOCR PP-StructureV3',
         mode='selected evaluation pages, retaining every previously completed page',
         pages=[completed[i]['audit'] for i in ids]))
    return pages
