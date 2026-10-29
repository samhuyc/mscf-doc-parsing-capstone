"""Apply the frozen local schema adapter, then the official benchmark metrics."""
import argparse
import csv
import importlib.metadata
import time
from collections import Counter
from pathlib import Path

import jsonschema

from extract_rules import VERSION, extract
from prepare import ROOT, decoded, read_json, sha256, write_json


def official_extractbench(reference, prediction, schema):
    from extract_bench.evaluation.metrics.extract import compute_unified_evidence_metrics
    from extract_bench.test_cases.schema import ExtractFieldTestRule
    rules = [ExtractFieldTestRule.model_validate(dict(body, type='extract_field', field_path=path))
             for path, body in decoded(reference['field_rules']).items()]
    metrics = compute_unified_evidence_metrics(decoded(reference['expected_output']),
                                               prediction, rules, data_schema=schema)
    return {m.metric_name: m.value for m in metrics}


def official_longextract(reference_path, prediction, schema):
    from longextract_bench.grading import _load_gt, grade
    return grade(prediction, _load_gt(reference_path), schema)


def evaluate(run_name):
    run_root = ROOT / 'runs' / run_name
    results = []
    code_hash = sha256(ROOT / 'extract_rules.py')
    lock_path = ROOT / 'adapter.lock.json'
    if not lock_path.exists() or read_json(lock_path)['sha256'] != code_hash:
        raise ValueError('Adapter is not frozen or has changed; freeze it under a new version before scoring')
    for record in read_json(ROOT / 'manifest.json'):
        folder = run_root / record['local_id']
        result = {'local_id': record['local_id'], 'dataset': record['dataset'],
                  'id': record['id'], 'pages': record['pages'], 'parser_status': 'not_run',
                  'extraction_status': 'not_run', 'metrics': None,
                  'parser_seconds': None, 'extraction_seconds': None, 'schema_valid': None}
        results.append(result)
        status_path = folder / 'run.json'
        if not status_path.exists():
            continue
        parser_run = read_json(status_path)
        result['parser_status'] = parser_run['status']
        result['parser_seconds'] = parser_run.get('runtime_seconds')
        if parser_run['status'] != 'success':
            result['extraction_status'] = 'not_run_parser_' + parser_run['status']
            if parser_run['status'] in ('failed', 'timeout', 'partial', 'empty') and record['dataset'] == 'extractbench':
                result['metrics'] = {f'extract_unified_value_{name}': 0.0 for name in ('precision', 'recall', 'f1')}
            continue
        if parser_run['source_sha256'] != record['files']['pdf']['sha256']:
            raise ValueError('Parser source identity differs from manifest')
        for key in ('schema', 'reference'):
            item = record['files'][key]
            if sha256(ROOT / item['path']) != item['sha256']:
                raise ValueError(f'Changed {key}')
        markdown_path = ROOT / parser_run['markdown']
        saved_hash = next(x['sha256'] for x in parser_run['outputs'] if x['path'] == parser_run['markdown'])
        if sha256(markdown_path) != saved_hash:
            raise ValueError('Parser Markdown changed')
        schema = read_json(ROOT / record['files']['schema']['path'])
        # This stage receives only parsed Markdown and schema, never the reference.
        audit_path = folder / 'extraction.json'
        if audit_path.exists():
            audit = read_json(audit_path)
            if (audit['adapter_sha256'] != code_hash or audit['source_markdown_sha256'] != saved_hash
                    or audit['schema_sha256'] != record['files']['schema']['sha256']
                    or audit['prediction_sha256'] != sha256(folder / 'prediction.json')):
                raise ValueError('Existing extraction provenance changed; use a new run')
            prediction = read_json(folder / 'prediction.json')
            elapsed = audit['runtime_seconds']
        else:
            started = time.monotonic()
            prediction, audit = extract(markdown_path.read_text(), schema)
            elapsed = time.monotonic() - started
            write_json(folder / 'prediction.json', prediction)
            write_json(audit_path, {
                **audit, 'adapter_sha256': code_hash, 'source_markdown_sha256': saved_hash,
                'schema_sha256': record['files']['schema']['sha256'],
                'runtime_seconds': elapsed, 'prediction_sha256': sha256(folder / 'prediction.json')})
        result['extraction_seconds'] = round(elapsed, 4)
        result['extraction_status'] = 'completed' if prediction else 'empty'
        validation_errors = list(jsonschema.Draft202012Validator(schema).iter_errors(prediction))
        result['schema_valid'] = not validation_errors
        result['schema_errors'] = [e.message for e in validation_errors[:20]]
        reference_path = ROOT / record['files']['reference']['path']
        if record['dataset'] == 'extractbench':
            result['metrics'] = official_extractbench(read_json(reference_path), prediction, schema)
            if not prediction:
                # An empty extraction is a failed attempt, even if a schema has defaults.
                result['metrics'] = {key: 0.0 for key in result['metrics']}
            if parser_run['runtime_seconds'] + elapsed > 1800:
                result['extraction_status'] = 'pipeline_timeout'
                result['metrics'] = {key: 0.0 for key in result['metrics']}
        elif prediction:
            result['metrics'] = official_longextract(reference_path, prediction, schema)
        print(record['local_id'], result['parser_status'], result['extraction_status'], flush=True)
    report = {'run': run_name, 'adapter': VERSION, 'adapter_sha256': code_hash,
              'manifest_sha256': sha256(ROOT / 'manifest.json'),
              'scope': 'MinerU 2.1.11 CPU plus deterministic schema adapter; nine-document subset',
              'official_metric_functions_with_custom_subset_reporting': True,
              'packages': {d.metadata['Name']: d.version for d in importlib.metadata.distributions()},
              'documents': results, 'summary': {}}
    for dataset in ('extractbench', 'longextract'):
        rows = [r for r in results if r['dataset'] == dataset]
        metrics = [r['metrics'] for r in rows if r['metrics'] is not None]
        keys = set().union(*(m.keys() for m in metrics)) if metrics else set()
        averages = {k: sum(m[k] for m in metrics if k in m) / sum(k in m for m in metrics)
                    for k in keys if not k.endswith(('_rows', '_total', '_match')) and k != 'matched'}
        report['summary'][dataset] = {
            'selected': len(rows), 'parser_status_counts': dict(Counter(r['parser_status'] for r in rows)),
            'extraction_status_counts': dict(Counter(r['extraction_status'] for r in rows)),
            'schema_valid': sum(r['schema_valid'] is True for r in rows),
            'scored': len(metrics), 'equal_document_mean': averages,
            'averaging_rule': ('Attempted terminal failures score zero; unfinished jobs excluded and disclosed'
                               if dataset == 'extractbench' else 'Completed nonempty extractions only; failures excluded and disclosed')}
    destination = ROOT / 'results' / run_name
    write_json(destination / 'results.json', report)
    with (destination / 'summary.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=['local_id', 'dataset', 'id', 'pages', 'parser_status',
                                                   'extraction_status', 'schema_valid', 'parser_seconds',
                                                   'extraction_seconds', 'value_f1', 'precision', 'recall', 'leaf_accuracy'])
        writer.writeheader()
        for row in results:
            metrics = row['metrics'] or {}
            writer.writerow({**{k: v for k, v in row.items() if k in writer.fieldnames},
                             'value_f1': metrics.get('extract_unified_value_f1'),
                             'precision': metrics.get('precision'), 'recall': metrics.get('recall'),
                             'leaf_accuracy': metrics.get('leaf_accuracy')})
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', default='mineru_cpu_v1')
    args = parser.parse_args()
    if Path(args.run).name != args.run:
        parser.error('Use a simple run name')
    evaluate(args.run)
