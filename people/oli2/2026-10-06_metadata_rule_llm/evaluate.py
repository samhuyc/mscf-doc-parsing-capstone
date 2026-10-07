"""Evaluation-only label access. Consumes frozen predictions; never extracts answers."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import subprocess

from adapters import digest, load_inputs, validate_evidence
from config import BASELINE, PARSERS, REPO, ROOT
from schema import FIELDS, equivalent, normalized_value, signature, validate_fields

PILOT_REVISION = '1d20388864e7015cbc2318478b82c73772143ae3'
PILOT_PATH = 'people/samhu/2026-10-05_pilot_benchmark/labels.jsonl'
O6_MAP = dict(document_type='document_type', reference_period='reporting_period',
              reference_date='reporting_period_end', document_date='document_date')


def ratio(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator,
                rate=numerator / denominator if denominator else None)


def read_jsonl(path):
    return [json.loads(s) for s in Path(path).read_text(encoding='utf8').splitlines() if s.strip()]


def pilot_reference(label):
    field, value = label['field'], label['value']
    if field == 'reporting_period':
        period = re.fullmatch(r'(\d{4})-([QH])([1-4])', value)
        if period:
            value = dict(year=int(period[1]), kind='quarter' if period[2] == 'Q' else 'half', number=int(period[3]))
            if value['kind'] == 'half' and value['number'] > 2:
                raise ValueError('Invalid pilot half')
        elif re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            # A date label is an end-date expectation, not a fiscal-kind annotation.
            field = 'reporting_period_end'
        else:
            raise ValueError(f'Unsupported pilot period: {value}')
    if field not in FIELDS:
        raise ValueError(f'Unknown pilot field: {field}')
    return dict(document_id=label['document'], source_sha256=label['source_sha256'],
                field=field, value=normalized_value(field, value), status='resolved',
                reference_id=label['id'], original_field=label['field'], original_value=label['value'],
                review_status=label['review_status'])


def load_references():
    # Read the exact teammate revision without merging or modifying their checkout.
    raw = subprocess.check_output(['git', 'show', f'{PILOT_REVISION}:{PILOT_PATH}'], cwd=REPO)
    pilot = [pilot_reference(x) for x in map(json.loads, raw.decode('utf8').splitlines())
             if x['kind'] == 'metadata' and x['review_status'] != 'excluded']
    old_raw = (BASELINE / 'reference_labels.json').read_bytes().replace(b'\r\n', b'\n')
    old = json.loads(old_raw)
    o6 = [dict(document_id=d['document_id'], field=O6_MAP[f], value=e['value'], status=e['status'],
               reference_id=f"o6:{d['document_id']}:{f}", review_status='provisional')
          for d in old['documents'] for f, e in d['expected'].items()]
    provenance = dict(pilot_revision=PILOT_REVISION, pilot_path=PILOT_PATH, pilot_sha256=digest(raw),
                      pilot_review_states=dict(Counter(x['review_status'] for x in pilot)),
                      o6_sha256=digest(old_raw), o6_origin=old['annotation_origin'],
                      warning='Development references; neither cohort is independent held-out gold')
    return dict(pilot_draft_inclusive=pilot,
                pilot_reviewed_only=[x for x in pilot if x['review_status'] in ('human_verified', 'adjudicated')],
                o6_provisional=o6), provenance


def index_records(records):
    indexed = {}
    for row in records:
        key = (row['document_id'], row['parser'], row['method'])
        if key in indexed:
            raise ValueError(f'Duplicate prediction: {key}')
        indexed[key] = row
    return indexed


def score_references(indexed, references, parser, method):
    metrics, mistakes = {}, []
    for field in FIELDS:
        labels = [r for r in references if r['field'] == field]
        correct = supported_correct = supported = resolved = ambiguous = not_found = missing = 0
        for label in labels:
            row = indexed.get((label['document_id'], parser, method))
            d = (row['fields'][field] if row and row['status'] == 'success'
                 and not validate_fields(row.get('fields')) else None)
            if row and label.get('source_sha256') and row['source_sha256'] != label['source_sha256']:
                raise ValueError('Reference/prediction source hash mismatch')
            ok = d is not None and equivalent(field, d['value'], label['value']) and d['status'] == label['status']
            correct += ok
            supported += label['value'] is not None
            supported_correct += ok and label['value'] is not None
            missing += d is None
            resolved += bool(d and d['status'] == 'resolved')
            ambiguous += bool(d and d['status'] == 'ambiguous')
            not_found += bool(d and d['status'] == 'not_found')
            if not ok:
                mistakes.append(dict(document_id=label['document_id'], field=field,
                                     reference_id=label['reference_id'], expected=label['value'],
                                     actual=d['value'] if d else None, status=d['status'] if d else 'missing'))
        metrics[field] = dict(exact_match=ratio(correct, len(labels)),
                              supported_value_accuracy=ratio(supported_correct, supported),
                              coverage=ratio(resolved, len(labels)), ambiguity_rate=ratio(ambiguous, len(labels)),
                              abstention_rate=ratio(ambiguous + not_found, len(labels)),
                              missing_or_failed_rate=ratio(missing, len(labels)))
    return dict(metrics=metrics, mistakes=mistakes, reference_fields=len(references))


def quality_metrics(rows, expected_inputs):
    indexed = {r['document_id']: r for r in rows}
    valid_schema = evidence_count = bad_evidence = unsupported = resolved = missing = 0
    diagnostics, coverage = [], {f: Counter() for f in FIELDS}
    for doc, provenance in expected_inputs:
        row = indexed.get(provenance['document_id'])
        if row is None or row['status'] != 'success':
            missing += 1
            for field in FIELDS:
                coverage[field]['missing'] += 1
            continue
        if (row['source_sha256'] != doc.source_sha256 or row['semantic_sha256'] != doc.semantic_sha256
                or row['input_hashes'] != provenance['input_hashes']):
            raise ValueError('Frozen prediction/input fingerprint mismatch')
        errors = validate_fields(row.get('fields'))
        valid_schema += not errors
        if errors:
            diagnostics.append(dict(document_id=row['document_id'], schema_errors=errors))
            continue
        check = validate_evidence(doc, row['fields'])
        evidence_count += check['count']
        bad_evidence += len(check['errors'])
        invalid_fields = {e['field'] for e in check['errors']}
        for f, d in row['fields'].items():
            coverage[f][d['status']] += 1
            if d['status'] == 'resolved':
                resolved += 1
                unsupported += f in invalid_fields or not d['evidence']
        if check['errors']:
            diagnostics.append(dict(document_id=row['document_id'], evidence_errors=check['errors']))
    proposed_evidence = sum(r.get('audit', {}).get('proposed_evidence_count', 0) for r in rows)
    invalid_proposals = sum(r.get('audit', {}).get('invalid_evidence_count', 0) for r in rows)
    raw_schema = [r['audit']['raw_schema_valid'] for r in rows if 'raw_schema_valid' in r.get('audit', {})]
    resources = [r.get('resources', {}) for r in rows]
    costs = [r.get('estimated_cost_usd') for r in resources]
    usage = [r['usage'] for r in resources if r.get('usage')]
    times = [r['latency_seconds'] for r in rows if 'latency_seconds' in r]
    return dict(schema_validity=ratio(valid_schema, len(expected_inputs)),
                evidence_validity=ratio(evidence_count - bad_evidence, evidence_count),
                unsupported_evidence_rate=ratio(unsupported, resolved),
                raw_llm_schema_validity=ratio(sum(raw_schema), len(raw_schema)),
                raw_llm_invalid_evidence_rate=ratio(invalid_proposals, proposed_evidence),
                rejected_llm_fields=sum(len(r.get('audit', {}).get('rejected_fields', [])) for r in rows),
                date_policy_rejected_fields=sum(len(r.get('audit', {}).get('policy_rejections', [])) for r in rows),
                semantic_hallucination_rate=None,
                evidence_note='Exact source membership only; does not establish semantic support, truth, or injection immunity',
                missing_or_failed_documents=missing,
                fields={f: dict(coverage=ratio(c['resolved'], len(expected_inputs)),
                                abstention_rate=ratio(c['ambiguous'] + c['not_found'], len(expected_inputs)),
                                ambiguity_rate=ratio(c['ambiguous'], len(expected_inputs)),
                                counts=dict(c)) for f, c in coverage.items()},
                resources=dict(latency_total_seconds=sum(times),
                               latency_mean_seconds=sum(times) / len(times) if times else None,
                               recorded_rows=len(rows), model_calls_this_run=sum(r.get('model_calls_this_run', r.get('model_calls', 0)) for r in resources),
                               original_response_model_calls=sum(r.get('model_calls', 0) for r in resources),
                               input_tokens=sum(u.get('input_tokens', 0) for u in usage),
                               output_tokens=sum(u.get('output_tokens', 0) for u in usage),
                               estimated_original_cost_usd=sum(costs) if costs and all(x is not None for x in costs) else None,
                               cache_hits=sum(bool(r.get('cache_hit')) for r in resources),
                               scope='Extraction only; excludes adapter loading, parsing/OCR, serialization and evaluation. Hybrid is resolver-only.'),
                diagnostics=diagnostics)


def compare(indexed, documents):
    stability, agreement = {}, {}
    for method in ('rule', 'llm', 'hybrid'):
        stability[method] = {}
        for f in FIELDS:
            eligible = equal = resolved_equal = 0
            differing = []
            for document in documents:
                rows = [indexed.get((document, p, method)) for p in PARSERS]
                if not all(r and r['status'] == 'success' and not validate_fields(r.get('fields')) for r in rows):
                    continue
                eligible += 1
                same = len({signature(r['fields'], f) for r in rows}) == 1
                equal += same
                resolved_equal += same and all(r['fields'][f]['status'] == 'resolved' for r in rows)
                if not same:
                    differing.append(dict(document_id=document, decisions={r['parser']: r['fields'][f]['value'] for r in rows}))
            stability[method][f] = dict(all_parser_decision_agreement=ratio(equal, eligible),
                                       all_parser_resolved_agreement=ratio(resolved_equal, eligible),
                                       missing_complete_triples=len(documents) - eligible, differences=differing)
    for parser in PARSERS:
        agreement[parser] = {}
        for f in FIELDS:
            available = both_resolved = agree = disagree = fallback = 0
            for document in documents:
                r, l = (indexed.get((document, parser, m)) for m in ('rule', 'llm'))
                if not r or not l or r['status'] != 'success' or l['status'] != 'success':
                    continue
                if validate_fields(r.get('fields')) or validate_fields(l.get('fields')):
                    continue
                r, l = r['fields'][f], l['fields'][f]
                available += 1
                if r['status'] == l['status'] == 'resolved':
                    both_resolved += 1
                    same = equivalent(f, r['value'], l['value'])
                    agree += same
                    disagree += not same
                fallback += r['status'] != 'resolved' and l['status'] == 'resolved'
            agreement[parser][f] = dict(available_pairs=available,
                                       resolved_agreement=ratio(agree, both_resolved),
                                       resolved_disagreement=ratio(disagree, both_resolved),
                                       llm_fallback_opportunities=fallback)
    return dict(parser_effect=stability, extractor_effect=agreement,
                note='Agreement is not accuracy; shared abstention counts only in decision agreement. Six-document descriptive study.')


def evaluate(predictions=ROOT / 'results/predictions', output=ROOT / 'results/evaluation', include_drafts=False):
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT) or output == ROOT:
        raise ValueError('Evaluation output must stay in new experiment')
    paths = [Path(predictions) / p / (m + '.jsonl') for p in PARSERS for m in ('rule', 'llm', 'hybrid')]
    existing = [p for p in paths if p.exists()]
    if not existing:
        raise ValueError('No predictions to evaluate')
    records = [r for p in existing for r in read_jsonl(p)]
    indexed = index_records(records)
    loaded = load_inputs()
    references, label_provenance = load_references()  # After predictions have been read/frozen.
    if not include_drafts:
        references.pop('pilot_draft_inclusive')
        references.pop('o6_provisional')
    artifacts = {}
    methods = sorted({r['method'] for r in records})
    for method in methods:
        result = dict(method=method, label_provenance=label_provenance,
                      predictions_sha256={str(p.relative_to(predictions)): digest(p.read_bytes().replace(b'\r\n', b'\n')) for p in existing},
                      parsers={})
        for parser in PARSERS:
            rows = [r for r in records if r['method'] == method and r['parser'] == parser]
            result['parsers'][parser] = dict(quality=quality_metrics(rows, [(d, p) for d, p in loaded if d.parser == parser]),
                                            cohorts={name: score_references(indexed, refs, parser, method) for name, refs in references.items()})
        artifacts[method] = result
    artifacts['comparison'] = compare(indexed, sorted({p['document_id'] for _, p in loaded}))
    targets = [output / (name + '.json') for name in artifacts]
    if any(p.exists() for p in targets):
        raise FileExistsError('Evaluation exists; use a fresh output directory')
    output.mkdir(parents=True, exist_ok=True)
    for name, value in artifacts.items():
        with (output / (name + '.json')).open('x', encoding='utf8', newline='\n') as file:
            json.dump(value, file, indent=2, ensure_ascii=False)
            file.write('\n')
    return artifacts


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--predictions', type=Path, default=ROOT / 'results/predictions')
    cli.add_argument('--output', type=Path, default=ROOT / 'results/evaluation')
    cli.add_argument('--include-drafts', action='store_true')
    args = cli.parse_args()
    evaluate(args.predictions, args.output, args.include_drafts)
    print('Wrote separate field metrics and comparison; no overall accuracy score.')
