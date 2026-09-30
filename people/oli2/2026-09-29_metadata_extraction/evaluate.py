"""Evaluation-only labels and evidence checks; never called by extraction."""
import argparse
import json
from pathlib import Path
import statistics

from jsonschema import Draft202012Validator, FormatChecker

from inputs import ROOT, REPO, read_json, load_document
from rules import FIELDS, RULESET_VERSION


def ratio(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator,
                rate=numerator / denominator if denominator else None)


def validate_evidence(row, repo=REPO):
    """Validate exact source spans and physical pages, not semantic truth."""
    errors, valid, cache = [], 0, {}
    ids = [e['id'] for e in row['evidence']]
    if len(ids) != len(set(ids)):
        errors.append('duplicate_evidence_ids')
    prefix = row['provenance']['input_path']
    for e in row['evidence']:
        try:
            if e['file'] not in (prefix + '/pages.json', prefix + '/metadata.json'):
                raise ValueError('Evidence must cite a canonical input')
            path = (Path(repo) / e['file']).resolve()
            if not path.is_relative_to(Path(repo).resolve()):
                raise ValueError('Evidence path escapes repository')
            if e['file'] not in cache:
                cache[e['file']] = read_json(path)
            source = cache[e['file']]
            if e['file'].endswith('/pages.json'):
                parts = e['json_pointer'].split('/')
                if len(parts) != 4 or parts[1] != 'pages' or parts[3] != 'markdown':
                    raise ValueError('Unsupported page evidence pointer')
                index = int(parts[2])
                if index < 0:
                    raise ValueError('Negative page index')
                page = source['pages'][index]
                if e['page'] != page['page']:
                    raise ValueError('Physical page mismatch')
                text = page['markdown']
            else:
                if e['json_pointer'] != '/source/metadata/title' or e['page'] is not None:
                    raise ValueError('Only embedded PDF title metadata may support predictions')
                text = source['source']['metadata']['title']
            if not (0 <= e['start'] < e['end'] <= len(text)) or text[e['start']:e['end']] != e['quote']:
                raise ValueError('Exact source quote or offsets mismatch')
            valid += 1
        except (ValueError, KeyError, IndexError, OSError) as error:
            errors.append(f'{e["id"]}: {error}')
    for field in FIELDS:
        decision = row[field]
        if decision['status'] == 'resolved' and not decision['evidence_ids']:
            errors.append(f'{field}: resolved without evidence')
        if decision['status'] != 'resolved' and decision['value'] is not None:
            errors.append(f'{field}: abstention must have null value')
        for item in [decision, *decision['candidates']]:
            if not set(item['evidence_ids']).issubset(ids):
                errors.append(f'{field}: dangling evidence reference')
    return dict(valid=valid, total=len(ids), errors=errors)


def evaluate(rows, labels, repo=REPO):
    expected = {r['document_id']: r for r in labels['documents']}
    if len(expected) != len(labels['documents']):
        raise ValueError('Duplicate label document IDs')
    predictions = {r['document_id']: r for r in rows}
    if len(predictions) != len(rows) or set(predictions) - set(expected):
        raise ValueError('Duplicate or unexpected prediction document IDs')
    validator = Draft202012Validator(read_json(ROOT / 'metadata.schema.json'), format_checker=FormatChecker())
    metrics, mistakes, abstentions, diagnostics = {}, [], [], []
    for field in FIELDS:
        matches = statuses = resolved = nonnull_correct = nonnull_total = 0
        for doc, label in expected.items():
            gold = label['expected'][field]
            actual = predictions.get(doc, {}).get(field)
            is_resolved = bool(actual and actual['status'] == 'resolved' and actual['value'] is not None)
            matches += bool(actual is not None and actual['value'] == gold['value'])
            statuses += bool(actual is not None and actual['status'] == gold['status'])
            resolved += is_resolved
            nonnull_total += gold['value'] is not None
            nonnull_correct += bool(gold['value'] is not None and is_resolved and actual['value'] == gold['value'])
            if actual is None or actual['value'] != gold['value'] or actual['status'] != gold['status']:
                mistakes.append(dict(document_id=doc, field=field, expected=gold,
                                     actual={k: actual[k] for k in ('value', 'status')} if actual else None))
            if not is_resolved:
                abstentions.append(dict(document_id=doc, field=field,
                                        status=actual['status'] if actual else 'missing_prediction',
                                        expected_abstention=gold['value'] is None))
        metrics[field] = dict(exact_match=ratio(matches, len(expected)),
                              status_accuracy=ratio(statuses, len(expected)),
                              supported_value_exact_match=ratio(nonnull_correct, nonnull_total),
                              coverage=ratio(resolved, len(expected)),
                              abstention_rate=ratio(len(expected)-resolved, len(expected)))
    evidence_valid = evidence_total = 0
    for row in rows:
        errors = [f'{list(e.path)}: {e.message}' for e in validator.iter_errors(row)]
        evidence = validate_evidence(row, repo)
        evidence_valid += evidence['valid']
        evidence_total += evidence['total']
        diagnostics.append(dict(document_id=row['document_id'], schema_errors=errors,
                                evidence_errors=evidence['errors'], warnings=row['warnings']))
    resolved_count = sum(m['coverage']['numerator'] for m in metrics.values())
    runtime = {r['document_id']: r['runtime']['total_seconds'] for r in rows}
    return dict(schema_version=1,expected_documents=len(expected),evaluated_documents=len(rows),
                missing_documents=sorted(set(expected)-set(predictions)),
                label_origin=labels['annotation_origin'], label_review_status=labels['review_status'],
                metrics=metrics, overall_coverage=ratio(resolved_count, len(expected)*len(FIELDS)),
                overall_abstention_rate=ratio(len(expected)*len(FIELDS)-resolved_count, len(expected)*len(FIELDS)),
                evidence_validity=ratio(evidence_valid, evidence_total),
                evidence_validity_note='Exact quotation, offsets, allowed input and physical page only; this does not establish semantic correctness or OCR accuracy.',
                mistakes=mistakes, abstentions=abstentions, diagnostics=diagnostics,
                runtime=dict(per_document_seconds=runtime, total_seconds=sum(runtime.values()),
                             mean_seconds=statistics.mean(runtime.values()) if runtime else None,
                             scope='One local sequential run: file reads, validation, text adaptation and rules; excludes OCR, models, output serialization and evaluation. Not a controlled benchmark.'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--predictions', type=Path, default=ROOT / 'results' / RULESET_VERSION / 'metadata.jsonl')
    parser.add_argument('--labels', type=Path, default=ROOT / 'reference_labels.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'results' / RULESET_VERSION / 'evaluation.json')
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT):
        parser.error('Evaluation outputs must stay inside this O6 experiment folder')
    if args.output.resolve().is_relative_to(ROOT / 'baseline') or args.output.exists():
        parser.error('Refusing to overwrite an evaluation or write into a baseline archive')
    rows = [json.loads(line) for line in args.predictions.read_text(encoding='utf-8').splitlines() if line.strip()]
    manifest = read_json(ROOT / 'input_manifest.json')
    for row in rows:
        matches = [x for x in manifest['documents'] if x['document_id'] == row['document_id']]
        if len(matches) != 1:
            raise ValueError('Prediction identity not found in fixed manifest')
        _, _, provenance = load_document(matches[0])
        for key, value in provenance.items():
            if row['provenance'][key] != value:
                raise ValueError(f'Prediction provenance mismatch: {key}')
    report = evaluate(rows, read_json(args.labels))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2))
    if report['missing_documents'] or any(d['schema_errors'] or d['evidence_errors'] for d in report['diagnostics']):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
