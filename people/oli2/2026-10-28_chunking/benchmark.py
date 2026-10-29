"""Fixed-query retrieval comparison: page versus section, with and without a document filter."""
from collections import defaultdict
import json
from pathlib import Path
import statistics

from chunker import digest, span
from retrieval import Retriever, build_context
from run import ROOT, REPO, portable_hash, write_json
from structure import ENCODING


def load_probes(documents):
    docs = {d['document_id']: d for d in documents}
    records, hashes = [], {}
    for filename, cohort in [('probes.json', 'original_8'), ('expanded_probes.json', 'expanded_24')]:
        path = ROOT / filename
        data = json.loads(path.read_text(encoding='utf8'))
        hashes[filename] = portable_hash(path)
        for q in data['queries']:
            doc = docs[q['document_id']]
            source = REPO / doc['source_artifact']
            if portable_hash(source) != doc['pages_sha256']:
                raise ValueError('Probe source hash mismatch')
            pages = json.loads(source.read_text(encoding='utf8'))['pages']
            evidence = []
            for e in q['evidence']:
                text = pages[e['page'] - 1]['markdown']
                if text.count(e['quote']) != 1:
                    raise ValueError(f'{q["id"]}: quote must occur exactly once on the specified page: {e["quote"]}')
                start = text.index(e['quote'])
                evidence.append(dict(document_id=q['document_id'], quote=e['quote'],
                                     **span(e['page'], start, start + len(e['quote']))))
            records.append(dict(id=q['id'], document_id=q['document_id'], question=q['question'],
                                cohort=cohort, kind='table' if any('<td>' in e['quote'] or '<th>' in e['quote'] for e in q['evidence']) else 'prose',
                                evidence=evidence))
    if len({q['id'] for q in records}) != len(records):
        raise ValueError('Duplicate query IDs')
    return records, hashes


def supports(chunks, evidence):
    """Source identity and merged intervals prevent wrong-page and split-span false results."""
    for e in evidence:
        intervals = sorted((s['start'], s['end']) for c in chunks if c['document_id'] == e['document_id']
                           for s in c['source_spans'] + c['context_spans'] if s['page'] == e['page'])
        cursor = e['start']
        for start, end in intervals:
            if start <= cursor:
                cursor = max(cursor, end)
        if cursor < e['end']:
            return False
    return True


def compare(documents, strategies, budget=3072):
    probes, hashes = load_probes(documents)
    records = []
    for strategy, chunks in strategies.items():
        retriever = Retriever(chunks)
        for scope in ('within_document', 'all_documents'):
            for q in probes:
                ranked = retriever.search(q['question'], q['document_id'] if scope == 'within_document' else None, 3)
                top = [c for _, c in ranked]
                packed = build_context(q['question'], ranked, budget, 3, ENCODING)
                chosen = [item['chunk'] for item in packed['selected']]
                records.append(dict(query_id=q['id'], cohort=q['cohort'], kind=q['kind'], question=q['question'],
                                    document_id=q['document_id'], strategy=strategy, scope=scope,
                                    hit_at_1=supports(top[:1], q['evidence']), hit_at_3=supports(top, q['evidence']),
                                    hit_within_budget=supports(chosen, q['evidence']),
                                    prompt_tokens=packed['prompt_tokens'], selected_chunks=len(chosen),
                                    budget_skips=len(packed['skipped']),
                                    top3=[dict(chunk_id=c['chunk_id'], document_id=c['document_id'],
                                               score=round(score, 8), source_spans=c['source_spans'], context_spans=c['context_spans'])
                                          for score, c in ranked],
                                    selected_ids=[c['chunk_id'] for c in chosen]))
    aggregates = []
    for scope in ('within_document', 'all_documents'):
        for strategy in strategies:
            for cohort in ('all_32', 'original_8', 'expanded_24'):
                rows = [r for r in records if r['scope'] == scope and r['strategy'] == strategy
                        and (cohort == 'all_32' or r['cohort'] == cohort)]
                aggregates.append(dict(scope=scope, strategy=strategy, cohort=cohort, queries=len(rows),
                                       hit_at_1=sum(r['hit_at_1'] for r in rows), hit_at_3=sum(r['hit_at_3'] for r in rows),
                                       hit_within_budget=sum(r['hit_within_budget'] for r in rows),
                                       mean_prompt_tokens=round(statistics.mean(r['prompt_tokens'] for r in rows), 1),
                                       mean_selected_chunks=round(statistics.mean(r['selected_chunks'] for r in rows), 2)))
    return dict(annotation_origin='Assistant-authored development references from saved parser text; no independent PDF gold or held-out corpus.',
                limitations=['Designated source-span coverage is not final-answer accuracy.',
                             'Other valid evidence can exist at unlabeled locations.',
                             'BM25 is lexical retrieval; no embedding model or LLM is evaluated.',
                             'Six previously inspected documents are not independent generalization evidence.'],
                settings=dict(retrieval='BM25', k1=1.5, b=.75, top_k=3, context_budget=budget, tokenizer=ENCODING,
                              packing='Whole passages from the fixed top-three pool; no truncation or replacement from lower ranks.'),
                probe_hashes=hashes, probes=probes, aggregates=aggregates, records=records)
