"""Extract frozen predictions. Evaluation is deliberately a separate process."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import time

from adapters import digest, json_bytes, load_inputs, validate_evidence
from baseline_bridge import PINNED
from config import MODEL, PARSERS, ROOT, VERSION
import hybrid
import llm_extractor
from providers import OpenAIProvider, ProviderError
import rule_extractor
from schema import validate_fields


def code_hashes():
    files = [*ROOT.glob('*.py'), *ROOT.glob('*.schema.json'), ROOT / 'prompts/metadata_extraction.txt',
             ROOT / 'input_manifest.json']
    return {p.relative_to(ROOT).as_posix(): digest(p.read_bytes().replace(b'\r\n', b'\n')) for p in files}


def write_new(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8', newline='\n') as file:
        file.write(content)


def read_records(path):
    return [json.loads(s) for s in Path(path).read_text(encoding='utf8').splitlines() if s.strip()]


def run(output=ROOT / 'results', parsers=PARSERS, methods=('rule',), provider=None, offline=False,
        cache=None, manifest=ROOT / 'input_manifest.json'):
    output = Path(output).resolve()
    # This CLI must never write outside the new experiment, including old archives.
    if not output.is_relative_to(ROOT) or output == ROOT:
        raise ValueError('Output must be a new results directory inside this experiment')
    loaded = load_inputs(manifest, parsers)  # Validate entire requested matrix before writes/calls.
    targets = [output / 'predictions' / p / (m + '.jsonl') for p in parsers for m in methods]
    if any(p.exists() for p in targets):
        raise FileExistsError('Prediction output exists; use a fresh output directory or unrun methods/parsers')
    provider = provider or OpenAIProvider()
    cache = Path(cache or output / 'cache')
    run_hashes = code_hashes()
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        revision = None
    identity = dict(experiment_version=VERSION, created_at_utc=datetime.now(timezone.utc).isoformat(),
                    base_revision=revision, python=platform.python_version(), platform=platform.platform(),
                    code_hashes=run_hashes, o6_hashes=PINNED)
    summary = dict(**identity, configurations=[], provider_failures=[])
    for parser in parsers:
        inputs = [(doc, prov) for doc, prov in loaded if doc.parser == parser]
        current = {}
        for method in methods:
            rows = []
            if method == 'hybrid':
                for dependency in ('rule', 'llm'):
                    if dependency not in current:
                        path = output / 'predictions' / parser / (dependency + '.jsonl')
                        current[dependency] = {r['source_sha256']: r for r in read_records(path)}
            for doc, provenance in inputs:
                started = time.perf_counter()
                record = dict(schema_version=1, method=method, **provenance, run=identity, status='success')
                try:
                    if method == 'rule':
                        fields, audit = rule_extractor.extract(doc)
                        resources = dict(model_calls_this_run=0, model_calls=0, usage=None, estimated_cost_usd=0)
                    elif method == 'llm':
                        fields, audit, resources = llm_extractor.extract(doc, provider, cache, offline=offline)
                    else:
                        r, l = (current[m].get(doc.source_sha256) for m in ('rule', 'llm'))
                        if not r or not l or any(x['status'] != 'success' for x in (r, l)):
                            record.update(status='unavailable', error='missing_successful_rule_or_llm_prediction')
                            rows.append(record)
                            continue
                        if any(x['semantic_sha256'] != doc.semantic_sha256 or x['parser'] != parser for x in (r, l)):
                            raise ValueError('Hybrid input identity mismatch')
                        fields, audit = hybrid.resolve(doc, r['fields'], l['fields'])
                        resources = dict(model_calls_this_run=0, model_calls=0, usage=None, estimated_cost_usd=0,
                                         dependency_cost_note='Resolver only; add rule and independent LLM costs',
                                         llm_cache_key=l['resources']['cache_key'])
                    errors = validate_fields(fields)
                    evidence = validate_evidence(doc, fields)
                    if errors or evidence['errors']:
                        raise ValueError(f'Invalid extraction: {errors} {evidence["errors"]}')
                    record.update(fields=fields, audit=audit, resources=resources,
                                  latency_seconds=time.perf_counter() - started)
                except ProviderError as error:
                    record.update(status='failed', error=error.metadata['error'], resources=error.metadata,
                                  latency_seconds=time.perf_counter() - started)
                    summary['provider_failures'].append(dict(parser=parser, document_id=provenance['document_id'],
                                                             **error.metadata))
                rows.append(record)
                print(parser, method, provenance['document_id'], record['status'], flush=True)
                # A global auth/quota failure must not trigger 17 identical billed attempts.
                if record.get('error') in ('HTTP_401', 'HTTP_403', 'HTTP_429', 'missing_OPENAI_API_KEY'):
                    break
            current[method] = {r['source_sha256']: r for r in rows}
            write_new(output / 'predictions' / parser / (method + '.jsonl'),
                      ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))
            summary['configurations'].append(dict(parser=parser, method=method, expected=len(inputs),
                                                   successful=sum(r['status'] == 'success' for r in rows),
                                                   recorded=len(rows)))
        if summary['provider_failures'] and summary['provider_failures'][-1]['error'] in (
                'HTTP_401', 'HTTP_403', 'HTTP_429', 'missing_OPENAI_API_KEY'):
            break
    name = digest(json_bytes(summary))[:16]
    write_new(output / 'runs' / (name + '.json'), json.dumps(summary, indent=2) + '\n')
    return summary


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--output', type=Path, default=ROOT / 'results')
    cli.add_argument('--parsers', nargs='+', choices=PARSERS, default=list(PARSERS))
    cli.add_argument('--methods', nargs='+', choices=['rule', 'llm', 'hybrid'], default=['rule'])
    cli.add_argument('--model', default=MODEL)
    cli.add_argument('--offline', action='store_true', help='Only use matching cached LLM responses')
    cli.add_argument('--cache', type=Path)
    args = cli.parse_args()
    if len(set(args.methods)) != len(args.methods) or len(set(args.parsers)) != len(args.parsers):
        cli.error('Duplicate method/parser')
    ordered = [m for m in ('rule', 'llm', 'hybrid') if m in args.methods]
    result = run(args.output, args.parsers, ordered, OpenAIProvider(args.model), args.offline, args.cache)
    if result['provider_failures']:
        raise SystemExit(2)
