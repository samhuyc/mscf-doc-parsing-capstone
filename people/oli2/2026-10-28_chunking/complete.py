"""Reproduce the complete chunking deliverable from frozen parser outputs."""
import argparse
from importlib.metadata import version
import json
from pathlib import Path
import statistics
import time

from benchmark import compare, load_probes
from chunker import validate_chunks
from retrieval import Retriever, build_context
from review import build_review
from run import DEFAULT_DOCS, METADATA, ROOT, SOURCES, load_document, portable_hash, write_json, write_jsonl
from structure import ENCODING, VERSION, chunk_document, count_tokens, token_summary


def metrics(chunks, validation, budget):
    return dict(**validation, **token_summary(chunks, budget),
                median_chars=statistics.median(c['char_count'] for c in chunks),
                max_chars=max(c['char_count'] for c in chunks),
                median_context_tokens=statistics.median(c['context_tokens'] for c in chunks),
                cross_page_chunks=sum(len({s['page'] for s in c['source_spans']}) > 1 for c in chunks),
                chunks_with_adjacent_context=sum(bool(c['context_spans']) for c in chunks))


def boundary_audit(chunks):
    old = [json.loads(line) for line in (ROOT / 'results/v1/section_chunks.jsonl').read_text(encoding='utf8').splitlines()]
    review = []
    for c in old:
        if c['char_count'] >= 100:
            continue
        covering = [n for n in chunks if n['document_id'] == c['document_id'] and any(
            a['page'] == b['page'] and a['start'] < b['end'] and b['start'] < a['end']
            for a in n['source_spans'] for b in c['source_spans'])]
        review.append(dict(original_chunk_id=c['chunk_id'], source_spans=c['source_spans'], excerpt=c['content'],
                           final_chunk_ids=[n['chunk_id'] for n in covering],
                           outcome='retained_low_information' if all(not n['indexable'] for n in covering) else
                                   'joined_with_adjacent_content' if any(n['char_count'] >= 100 for n in covering) else 'retained_small_passage'))
    small = [dict(chunk_id=c['chunk_id'], source_spans=c['source_spans'], content=c['content'],
                  indexable=c['indexable'], flags=c['flags']) for c in chunks if c['char_count'] < 100]
    return dict(review_type='Source-text structural audit, not independent human semantic annotation',
                original_small_chunks=len(review), original_small_chunk_dispositions=review,
                final_small_chunks=small)


def build(output, max_tokens=1024, context_budget=3072, with_metadata=True):
    output = Path(output)
    if output.exists():
        raise FileExistsError('Use a fresh output directory')
    started = time.perf_counter()
    docs = [load_document(SOURCES / name / 'pymupdf4llm', METADATA if with_metadata else None) for name in DEFAULT_DOCS]
    # Validate all references before any scoring. They are never passed to chunk_document.
    load_probes(docs)
    pages, sections, decisions, per_doc = [], [], {}, []
    for doc in docs:
        p, s, h = chunk_document(doc, max_tokens)
        pages.extend(p)
        sections.extend(s)
        decisions[doc['document_id']] = h
        per_doc.append(dict(document_id=doc['document_id'], pages=len(doc['pages']),
                            page=metrics(p, validate_chunks(doc, p), max_tokens),
                            section=metrics(s, validate_chunks(doc, s), max_tokens)))
    summary = dict(version=VERSION, parser='pymupdf4llm', max_tokens=max_tokens, tokenizer=ENCODING,
                   documents=per_doc, total_pages=len(pages), total_section_chunks=len(sections),
                   source_characters=sum(d['page']['source_characters'] for d in per_doc),
                   table_blocks=sum(d['page']['table_blocks_preserved'] for d in per_doc),
                   section_totals=token_summary(sections, max_tokens),
                   processing_seconds=round(time.perf_counter() - started, 4),
                   limitations=['Exact preservation is measured against saved parser text, not original PDF fidelity.',
                                'Heading normalization and adjacent notes remain heuristic.',
                                'Complete tables can exceed the per-chunk token target and are explicitly flagged.',
                                'Cross-page table fragments are not stitched; image content is not reprocessed.'])
    retrieval = compare(docs, dict(page=pages, section=sections), context_budget)
    question = 'Which accounting standard was used to prepare EDF financial statements?'
    example = build_context(question, Retriever(sections).search(question, 'edf_2024', 3), context_budget)
    output.mkdir(parents=True)
    write_jsonl(output / 'page_chunks.jsonl', pages)
    write_jsonl(output / 'section_chunks.jsonl', sections)
    write_json(output / 'summary.json', summary)
    write_json(output / 'documents.json', [{k: v for k, v in d.items() if k != 'pages'} for d in docs])
    write_json(output / 'heading_decisions.json', decisions)
    write_json(output / 'boundary_audit.json', boundary_audit(sections))
    write_json(output / 'retrieval.json', retrieval)
    write_json(output / 'rag_example.json', example)
    (output / 'rag_example.txt').write_text(example['prompt'], encoding='utf8')
    write_json(output / 'manifest.json', dict(version=VERSION, parameters=dict(max_tokens=max_tokens, context_budget=context_budget,
               tokenizer=ENCODING, with_metadata=with_metadata),
               dependencies={name: version(name) for name in ('markdown-it-py', 'tiktoken')},
               code_hashes={p.name: portable_hash(p) for p in sorted(ROOT.glob('*.py'))},
               test_hashes={p.name: portable_hash(p) for p in sorted((ROOT / 'tests').glob('*.py'))},
               requirements_sha256=portable_hash(ROOT / 'requirements.txt'),
               probe_hashes=retrieval['probe_hashes'],
               sources=[dict(document_id=d['document_id'], source_artifact=d['source_artifact'],
                             source_sha256=d['source_sha256'], input_hashes=d['input_hashes'],
                             metadata_sha256=d['metadata_sha256']) for d in docs]))
    build_review(output / 'preview.html', docs, pages, sections, summary, decisions)
    write_json(output / 'index.json', dict(schema_version=1, default_strategy='section', tokenizer=ENCODING,
               chunk_files={name: dict(path=f'{name}_chunks.jsonl', sha256_utf8_lf=portable_hash(output / f'{name}_chunks.jsonl'))
                            for name in ('page', 'section')}))
    return summary, retrieval['aggregates']


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output', type=Path, required=True)
    cli.add_argument('--max-tokens', type=int, default=1024)
    cli.add_argument('--context-budget', type=int, default=3072)
    cli.add_argument('--without-metadata', action='store_true')
    args = cli.parse_args()
    summary, metrics = build(args.output, args.max_tokens, args.context_budget, not args.without_metadata)
    print(json.dumps(dict(summary=summary, retrieval=[m for m in metrics if m['cohort'] == 'all_32']), indent=2))
