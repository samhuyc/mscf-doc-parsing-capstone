"""Small offline BM25 retrieval diagnostic. References never enter chunk generation."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import statistics

from chunker import digest, span
from run import ROOT, REPO, portable_hash, write_json

STOP = set('a an the of in on at for to and or is are was were what how which with by from its it'.split())


def tokens(text):
    return [t for t in re.findall(r'[^\W_]+', text.casefold()) if t not in STOP]


def rank(chunks, question):
    """BM25, k1=1.5 and b=0.75; no expected answers or evidence are accepted here."""
    counts = [Counter(tokens(c['retrieval_text'])) for c in chunks]
    lengths = [sum(c.values()) for c in counts]
    average = sum(lengths) / len(lengths) if lengths else 1
    df = Counter(t for c in counts for t in c)
    query = set(tokens(question))
    scored = []
    for chunk, counts_i, length in zip(chunks, counts, lengths):
        score = 0
        for term in query:
            tf = counts_i[term]
            if tf:
                idf = math.log(1 + (len(chunks) - df[term] + .5) / (df[term] + .5))
                score += idf * tf * 2.5 / (tf + 1.5 * (.25 + .75 * length / max(average, 1)))
        if score > 0:
            scored.append((score, chunk))
    return sorted(scored, key=lambda row: (-row[0], row[1]['chunk_id']))


def supports(chunks, expected):
    locations = [s for c in chunks for s in c['source_spans'] + c['context_spans']]
    return all(any(s['page'] == e['page'] and s['start'] <= e['start'] and s['end'] >= e['end']
                   for s in locations) for e in expected)


def evaluate(folder, probes_path, output):
    folder, output = Path(folder), Path(output)
    if output.exists():
        raise FileExistsError('Use a fresh retrieval result path')
    probes = json.loads(Path(probes_path).read_text(encoding='utf8'))
    docs = {d['document_id']: d for d in json.loads((folder / 'documents.json').read_text(encoding='utf8'))}
    chunks = {strategy: [json.loads(line) for line in (folder / f'{strategy}_chunks.jsonl').read_text(encoding='utf8').splitlines()]
              for strategy in ('page', 'section')}
    records = []
    for q in probes['queries']:
        doc = docs[q['document_id']]
        source_path = REPO / doc['source_artifact']
        if portable_hash(source_path) != doc['pages_sha256']:
            raise ValueError('Probe source differs from chunked source')
        pages = json.loads(source_path.read_text(encoding='utf8'))['pages']
        expected = []
        for e in q['evidence']:
            text = pages[e['page'] - 1]['markdown']
            if text.count(e['quote']) != 1:
                raise ValueError(f'Probe {q["id"]}: evidence must match exactly once on its page')
            start = text.index(e['quote'])
            expected.append(span(e['page'], start, start + len(e['quote'])))
        for strategy, rows in chunks.items():
            candidates = [c for c in rows if c['document_id'] == q['document_id']]
            ordered = rank(candidates, q['question'])[:3]
            retrieved = [c for _, c in ordered]
            records.append(dict(query_id=q['id'], document_id=q['document_id'], question=q['question'],
                                strategy=strategy, evidence=expected,
                                hit_at_1=supports(retrieved[:1], expected), hit_at_3=supports(retrieved, expected),
                                top3_retrieval_chars=sum(len(c['retrieval_text']) for c in retrieved),
                                top3=[dict(chunk_id=c['chunk_id'], score=round(score, 5),
                                           source_spans=c['source_spans'], context_spans=c['context_spans'])
                                      for score, c in ordered]))
    aggregate = {}
    for strategy in chunks:
        rows = [r for r in records if r['strategy'] == strategy]
        aggregate[strategy] = dict(queries=len(rows), hit_at_1=sum(r['hit_at_1'] for r in rows),
                                   hit_at_3=sum(r['hit_at_3'] for r in rows),
                                   mean_top3_retrieval_chars=round(statistics.mean(r['top3_retrieval_chars'] for r in rows), 1))
    result = dict(annotation_origin=probes['annotation_origin'], scope=probes['scope'],
                  retrieval='BM25 within the specified document, k1=1.5, b=0.75, top_k=3; English lexical tokens',
                  scope_note='No embeddings or LLM calls; no cross-document, Chinese, or final-answer evaluation.',
                  evidence_note='Exact saved-parser-text spans, including explicitly linked context; not verified PDF facts. Alternative valid evidence is not labeled.',
                  probe_sha256=digest(Path(probes_path).read_bytes()),
                  chunk_hashes={s: portable_hash(folder / f'{s}_chunks.jsonl') for s in chunks},
                  aggregate=aggregate, queries=records)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, result)
    return aggregate


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--results', type=Path, required=True)
    cli.add_argument('--probes', type=Path, default=ROOT / 'probes.json')
    cli.add_argument('--output', type=Path, required=True)
    args = cli.parse_args()
    print(json.dumps(evaluate(args.results, args.probes, args.output), indent=2))
