"""Build reproducible chunks and a local review from frozen PyMuPDF4LLM exports."""
import argparse
from collections import Counter
from importlib.metadata import version
import json
from pathlib import Path
import statistics
import time

from chunker import VERSION, chunk_document, digest, validate_chunks
from review import build_review

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
SOURCES = REPO / 'people/samhu/2026-09-29_sponsor_samples/results'
METADATA = ROOT.parent / '2026-10-06_metadata_rule_llm/results/predictions/pymupdf4llm/hybrid.jsonl'
DEFAULT_DOCS = ['edf_2024', 'rolls_royce_2026h1_release', 'hippodrome_2025',
                'cvs_2025q2', 'peterborough_2025', 'rolls_royce_2026h1_presentation']


def portable_hash(path):
    return digest(Path(path).read_bytes().replace(b'\r\n', b'\n'))


def load_document(folder, metadata_path=None):
    folder = Path(folder)
    data = {name: json.loads((folder / name).read_text(encoding='utf8'))
            for name in ('pages.json', 'metadata.json', 'run.json')}
    pages, meta, run = (data[n] for n in ('pages.json', 'metadata.json', 'run.json'))
    source = meta['source']
    if pages.get('schema_version') != 1 or pages.get('page_numbering') != '1-based physical PDF pages':
        raise ValueError('Unsupported page contract')
    if not pages['parser'] == meta['parser'] == run['parser'] == 'pymupdf4llm':
        raise ValueError('v1 requires the frozen pymupdf4llm pipeline; no automatic parser mixing')
    if not pages['source_sha256'] == source['sha256'] == run['input_sha256']:
        raise ValueError('Source identity mismatch')
    if run['document'] != source['id'] or run['status'] != 'success':
        raise ValueError('Unsuccessful or mismatched parser run')
    records = pages['pages']
    if not records or [p['page'] for p in records] != list(range(1, len(records) + 1)):
        raise ValueError('Missing, duplicate, or unordered physical pages')
    if not len(records) == source['pages'] == run['expected_pages'] == run['parsed_pages']:
        raise ValueError('Page count mismatch')
    if any(not isinstance(p['markdown'], str) for p in records):
        raise ValueError('Non-text page Markdown')
    source_artifact = (folder / 'pages.json').resolve()
    if source_artifact.is_relative_to(REPO):
        source_artifact = source_artifact.relative_to(REPO).as_posix()
    else:
        source_artifact = source_artifact.as_posix()
    doc = dict(document_id=source['id'], parser=pages['parser'], source_sha256=pages['source_sha256'],
               pages_sha256=portable_hash(folder / 'pages.json'), source_artifact=source_artifact,
               pages=records, document_metadata={}, metadata_sha256=None, metadata_record=None,
               source_url=source.get('url'), outline=meta.get('source_outline', []),
               parser_versions=run.get('versions', {}),
               input_hashes={name: portable_hash(folder / name) for name in data})
    if metadata_path is not None:
        rows = [json.loads(line) for line in Path(metadata_path).read_text(encoding='utf8').splitlines() if line.strip()]
        matches = [r for r in rows if r['document_id'] == doc['document_id'] and r['parser'] == doc['parser']]
        if len(matches) != 1:
            raise ValueError('Expected exactly one matching Hybrid metadata record')
        record = matches[0]
        if record['source_sha256'] != doc['source_sha256'] or record['input_hashes']['pages.json'] != doc['pages_sha256']:
            raise ValueError('Metadata was extracted from different source pages')
        if record['status'] != 'success':
            raise ValueError('Metadata extraction was unsuccessful')
        doc['document_metadata'] = {k: {n: v[n] for n in ('value', 'status', 'method')}
                                    for k, v in record['fields'].items()}
        doc['metadata_record'] = record
        doc['metadata_sha256'] = digest(record)
    return doc


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def write_jsonl(path, rows):
    Path(path).write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf8')


def metrics(chunks, validation, max_chars):
    sizes = sorted(c['char_count'] for c in chunks)
    return dict(**validation, median_chars=statistics.median(sizes) if sizes else 0,
                max_chars=max(sizes, default=0),
                over_budget_chunks=sum(n > max_chars for n in sizes),
                cross_page_chunks=sum(len({s['page'] for s in c['source_spans']}) > 1 for c in chunks),
                chunks_with_adjacent_context=sum(bool(c['context_spans']) for c in chunks),
                flags=dict(Counter(flag for c in chunks for flag in c['flags'])))


def build(output, names=DEFAULT_DOCS, source_root=SOURCES, metadata_path=METADATA, max_chars=4000):
    output = Path(output)
    if output.exists():
        raise FileExistsError('Choose a fresh output directory; previous experiments are retained')
    if len(names) != len(set(names)) or not names:
        raise ValueError('Select unique, nonempty document IDs')
    docs, all_pages, all_sections, headings, results = [], [], [], {}, []
    started = time.perf_counter()
    for name in names:
        if Path(name).name != name or name in ('.', '..'):
            raise ValueError('Document IDs must be directory names')
        doc = load_document(Path(source_root) / name / 'pymupdf4llm', metadata_path)
        page, section, decisions = chunk_document(doc, max_chars)
        vp, vs = validate_chunks(doc, page), validate_chunks(doc, section)
        results.append(dict(document_id=name, pages=len(doc['pages']),
                            page=metrics(page, vp, max_chars), section=metrics(section, vs, max_chars)))
        docs.append(doc)
        all_pages.extend(page)
        all_sections.extend(section)
        headings[name] = decisions
    elapsed = time.perf_counter() - started
    summary = dict(version=VERSION, parser='pymupdf4llm', max_chars_soft_budget=max_chars,
                   size_unit='raw Markdown Unicode characters, not model tokens',
                   documents=results, total_pages=len(all_pages), total_section_chunks=len(all_sections),
                   processing_seconds=round(elapsed, 4),
                   limitations=['Coverage is relative to saved parser text, not original PDF accuracy.',
                                'Heading hierarchy and adjacent table context are heuristics, not semantic gold.',
                                'Large atomic blocks can exceed the soft character budget.',
                                'Cross-page table fragments are retained separately; no automatic table stitching.',
                                'Image references are preserved but image content is not newly recognized.',
                                'Document metadata inherits provisional extractor decisions; no silent correction.'])
    output.mkdir(parents=True)
    write_jsonl(output / 'page_chunks.jsonl', all_pages)
    write_jsonl(output / 'section_chunks.jsonl', all_sections)
    write_json(output / 'heading_decisions.json', headings)
    write_json(output / 'documents.json', [{k: v for k, v in d.items() if k != 'pages'} for d in docs])
    write_json(output / 'summary.json', summary)
    write_json(output / 'manifest.json', dict(version=VERSION, parameters=dict(max_chars=max_chars, overlap=0),
               dependencies=dict(markdown_it_py=version('markdown-it-py')),
               code_hashes={p.name: portable_hash(p) for p in sorted(ROOT.glob('*.py'))},
               sources=[dict(document_id=d['document_id'], source_artifact=d['source_artifact'],
                             source_sha256=d['source_sha256'], input_hashes=d['input_hashes'],
                             metadata_sha256=d['metadata_sha256']) for d in docs]))
    build_review(output / 'preview.html', docs, all_pages, all_sections, summary, headings)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--documents', nargs='+', default=DEFAULT_DOCS)
    parser.add_argument('--source-root', type=Path, default=SOURCES)
    parser.add_argument('--metadata', type=Path, default=METADATA)
    parser.add_argument('--without-metadata', action='store_true')
    parser.add_argument('--max-chars', type=int, default=4000)
    args = parser.parse_args()
    summary = build(args.output, args.documents, args.source_root,
                    None if args.without_metadata else args.metadata, args.max_chars)
    print(json.dumps(summary, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
