"""Read and validate existing exports. No PDF, OCR, network, or model dependencies."""
from dataclasses import dataclass
import hashlib
import html
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
FILES = ('pages.json', 'metadata.json', 'document.md', 'run.json')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def lf_bytes(data):
    """Only normalize Git's Windows checkout line endings; retain other bytes."""
    return data.replace(b'\r\n', b'\n')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


@dataclass(frozen=True)
class TextView:
    """Searchable text with a character map back to exact original evidence."""
    raw: str
    text: str
    spans: tuple
    file: str
    pointer: str
    page: int | None

    def evidence(self, start, end):
        left, right = self.spans[start][0], self.spans[end - 1][1]
        return dict(file=self.file, json_pointer=self.pointer, page=self.page,
                    start=left, end=right, quote=self.raw[left:right])


def text_view(raw, file, pointer, page):
    # Remove syntax and image destinations, retaining picture *text* when present.
    syntax = re.compile(r'<!--.*?-->|!\[[^\]]*\]\([^)]*\)|<[^>]*>|&(?:#\d+|#x[0-9a-fA-F]+|\w+);|[*_`#]+', re.S)
    chars, spans = [], []

    def append(value, start, end):
        for char in value:
            char = ' ' if char.isspace() else char
            if char == ' ' and chars and chars[-1] == ' ':
                spans[-1] = (spans[-1][0], end)
            else:
                chars.append(char)
                spans.append((start, end))

    cursor = 0
    for match in syntax.finditer(raw):
        for i in range(cursor, match.start()):
            append(raw[i], i, i + 1)
        token = match.group()
        replacement = html.unescape(token) if token.startswith('&') else ' '
        append(replacement, match.start(), match.end())
        cursor = match.end()
    for i in range(cursor, len(raw)):
        append(raw[i], i, i + 1)
    return TextView(raw, ''.join(chars), tuple(spans), file, pointer, page)


def load_document(entry, repo=REPO):
    repo = Path(repo).resolve()
    folder = (repo / entry['path']).resolve()
    if not folder.is_relative_to(repo):
        raise ValueError('Input path escapes repository')
    data, hashes, converted = {}, {}, []
    for name in FILES:
        raw = (folder / name).read_bytes()
        portable = lf_bytes(raw)
        if sha256(portable) != entry['sha256_utf8_lf'][name]:
            raise ValueError(f'Pinned input hash mismatch: {name}')
        hashes[name] = dict(checkout_sha256=sha256(raw), utf8_lf_sha256=sha256(portable))
        if raw != portable:
            converted.append(name)
        data[name] = portable.decode('utf-8')
    pages, metadata, run = (json.loads(data[n]) for n in ('pages.json', 'metadata.json', 'run.json'))
    source = metadata['source']
    if pages['schema_version'] != 1 or pages['page_numbering'] != '1-based physical PDF pages':
        raise ValueError('Unsupported page contract')
    if not (entry['parser'] == pages['parser'] == metadata['parser'] == run['parser']):
        raise ValueError('Parser identity mismatch')
    if not (entry['document_id'] == source['id'] == run['document']):
        raise ValueError('Document identity mismatch')
    if not (entry['source_sha256'] == source['sha256'] == pages['source_sha256'] == run['input_sha256']):
        raise ValueError('Source hash mismatch')
    records = pages['pages']
    if not (len(records) == source['pages'] == run['expected_pages'] == run['parsed_pages']):
        raise ValueError('Page count mismatch')
    if [p['page'] for p in records] != list(range(1, len(records) + 1)):
        raise ValueError('Invalid physical page sequence')
    if run['status'] != 'success' or run['nonempty_pages'] != sum(p['text_chars'] > 0 for p in records):
        raise ValueError('Incomplete or inconsistent parser run')
    if sha256(data['document.md'].encode('utf-8')) != run['document_sha256']:
        raise ValueError('Parser document hash mismatch after declared LF normalization')
    reconstructed = '\n\n'.join(f"<!-- source page {p['page']} -->\n\n{p['markdown']}" for p in records)
    if reconstructed != data['document.md']:
        raise ValueError('Page text differs from document.md')
    prefix = Path(entry['path']).as_posix()
    views = [text_view(p['markdown'], prefix + '/pages.json', f'/pages/{i}/markdown', p['page'])
             for i, p in enumerate(records)]
    # The semantic rule interface receives ONLY page text and the embedded PDF title.
    # Manifest titles, IDs, paths, timestamps and labels never become search text.
    title = text_view(source['metadata'].get('title', ''), prefix + '/metadata.json',
                      '/source/metadata/title', None)
    provenance = dict(input_path=prefix, parser=entry['parser'], parser_versions=run['versions'],
                      source_sha256=source['sha256'], input_hashes=hashes,
                      line_endings_normalized=converted,
                      source_kind='scanned' if not any(source['native_text_chars']) else 'digital',
                      page_count=len(records))
    return views, title, provenance
