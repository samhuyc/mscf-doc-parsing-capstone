"""Validate common sponsor exports and isolate permitted semantic input."""
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re

from config import PARSERS, REPO, ROOT

FILES = ('pages.json', 'metadata.json', 'document.md', 'run.json')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf8')


def redact_destinations(text):
    """Mask non-content syntax with spaces, preserving character offsets/newlines.

    Keep visible link text and HTML tag names/structure, but hide paths, URLs,
    image syntax and HTML attributes (which can contain answer-like filenames).
    This representation is identical for rules and LLMs.
    """
    def mask(m):
        return ''.join('\n' if c == '\n' else ' ' for c in m.group())
    text = re.sub(r'<!--.*?-->|!\[[^\]]*\]\([^)]*\)', mask, text, flags=re.S)
    text = re.sub(r'(?<=\])\([^)]*\)', mask, text)
    text = re.sub(r'(?m)^\s*\[[^\]]+\]:\s*\S+.*$', mask, text)
    text = re.sub(r'(?<=<)(?:https?://|file:)[^>]+', mask, text)
    def tag(m):
        return re.sub(r'\s+[\w:-]+\s*=\s*(?:"[^"]*"|\x27[^\x27]*\x27|[^\s>]+)', mask, m.group())
    return re.sub(r'<[^>]+>', tag, text)


@dataclass(frozen=True)
class ParsedPage:
    page: int
    markdown: str
    original: str = field(repr=False)


@dataclass(frozen=True)
class ParsedDocument:
    source_sha256: str
    parser: str
    pages: tuple[ParsedPage, ...]
    embedded_title: str = ''
    original_title: str = field(default='', repr=False)

    def semantic_payload(self):
        # Intentionally excludes parser identity, hash, ID, path, and native data.
        return dict(pages=[dict(page=p.page, markdown=p.markdown) for p in self.pages],
                    embedded_title=self.embedded_title)

    @property
    def semantic_sha256(self):
        return digest(json_bytes(self.semantic_payload()))

    def source_text(self, source, page):
        if source == 'embedded_title' and page is None:
            return self.embedded_title, self.original_title, '/source/metadata/title'
        if source != 'page' or type(page) is not int or not 1 <= page <= len(self.pages):
            raise ValueError('Invalid physical page or evidence source')
        p = self.pages[page - 1]
        return p.markdown, p.original, f'/pages/{page - 1}/markdown'


def make_document(texts, title='', parser='pymupdf4llm', source_sha256='a' * 64):
    if not texts or any(not isinstance(s, str) for s in texts):
        raise ValueError('No physical pages or non-string Markdown')
    return ParsedDocument(source_sha256, parser,
                          tuple(ParsedPage(i + 1, redact_destinations(s), s) for i, s in enumerate(texts)),
                          redact_destinations(title), title)


def locate_evidence(doc, item):
    """Validate exact quotation; enrich model evidence with reproducible offsets."""
    raw, original, pointer = doc.source_text(item['source'], item['page'])
    quote = item['quote']
    if not isinstance(quote, str) or not quote.strip():
        raise ValueError('Empty quotation')
    start = item.get('start', raw.find(quote))
    end = item.get('end', start + len(quote))
    if type(start) is not int or type(end) is not int or start < 0 or end <= start or raw[start:end] != quote:
        raise ValueError('Quotation/span not found on declared source page')
    result = dict(source=item['source'], page=item['page'], quote=quote, start=start, end=end,
                  original_quote=original[start:end], json_pointer=pointer)
    if any(k in item and item[k] != result[k] for k in ('original_quote', 'json_pointer')):
        raise ValueError('Original source quotation/pointer mismatch')
    return result


def validate_evidence(doc, fields):
    errors, count = [], 0
    for name, d in fields.items():
        for i, item in enumerate(d['evidence']):
            count += 1
            try:
                locate_evidence(doc, item)
            except (ValueError, KeyError, TypeError) as e:
                errors.append(dict(field=name, evidence=i, error=str(e)))
    return dict(count=count, errors=errors)


def load_export(folder, expected=None):
    folder = Path(folder)
    data, hashes = {}, {}
    for name in FILES:
        raw = (folder / name).read_bytes()
        portable = raw.replace(b'\r\n', b'\n')
        hashes[name] = digest(portable)
        if expected and hashes[name] != expected['sha256_utf8_lf'][name]:
            raise ValueError(f'Pinned input hash mismatch: {name}')
        data[name] = portable.decode('utf8')
    pages, metadata, run = (json.loads(data[n]) for n in ('pages.json', 'metadata.json', 'run.json'))
    source, parser = metadata['source'], pages['parser']
    if parser not in PARSERS or not parser == metadata['parser'] == run['parser']:
        raise ValueError('Parser identity mismatch')
    if pages['schema_version'] != 1 or pages['page_numbering'] != '1-based physical PDF pages':
        raise ValueError('Unsupported page contract')
    if not source['sha256'] == pages['source_sha256'] == run['input_sha256']:
        raise ValueError('Source hash mismatch')
    if not re.fullmatch('[0-9a-f]{64}', source['sha256']):
        raise ValueError('Invalid source hash')
    if source['id'] != run['document']:
        raise ValueError('Document identity mismatch')
    records = pages['pages']
    if not records or not len(records) == source['pages'] == run['expected_pages'] == run['parsed_pages']:
        raise ValueError('Page count mismatch')
    if [p['page'] for p in records] != list(range(1, len(records) + 1)):
        raise ValueError('Missing, duplicate or unordered physical page')
    if run['status'] != 'success' or run['nonempty_pages'] != sum(p['text_chars'] > 0 for p in records):
        raise ValueError('Incomplete parser run')
    reconstructed = '\n\n'.join(f"<!-- source page {p['page']} -->\n\n{p['markdown']}" for p in records)
    if reconstructed != data['document.md'] or digest(reconstructed.encode('utf8')) != run['document_sha256']:
        raise ValueError('Page text/document.md/hash mismatch')
    if expected and (expected['parser'] != parser or expected['document_id'] != source['id'] or
                     expected['source_sha256'] != source['sha256']):
        raise ValueError('Pinned source identity mismatch')
    title = source.get('metadata', {}).get('title', '') or ''
    doc = make_document([p['markdown'] for p in records], title, parser, source['sha256'])
    provenance = dict(document_id=source['id'], parser=parser, source_sha256=doc.source_sha256,
                      input_hashes=hashes, parser_versions=run['versions'], page_count=len(records),
                      semantic_sha256=doc.semantic_sha256,
                      source_kind='scanned' if not any(source['native_text_chars']) else 'digital')
    return doc, provenance


def load_inputs(manifest=ROOT / 'input_manifest.json', parsers=PARSERS):
    entries = json.loads(Path(manifest).read_text(encoding='utf8'))['inputs']
    selected = [e for parser in parsers for e in entries if e['parser'] == parser]
    if not selected:
        raise ValueError('No inputs selected')
    loaded = []
    seen, identities = set(), {}
    for e in selected:
        key = (e['document_id'], e['parser'])
        if key in seen:
            raise ValueError('Duplicate input')
        seen.add(key)
        folder = (REPO / e['path']).resolve()
        if not folder.is_relative_to(REPO):
            raise ValueError('Input path escapes repository')
        doc, provenance = load_export(folder, e)
        identity = (doc.source_sha256, len(doc.pages))
        if identities.setdefault(e['document_id'], identity) != identity:
            raise ValueError('Cross-parser source identity mismatch')
        provenance['input_path'] = e['path']
        loaded.append((doc, provenance))
    for document in identities:
        if any((document, parser) not in seen for parser in parsers):
            raise ValueError('Missing parser/document combination; no fallback allowed')
    return loaded
