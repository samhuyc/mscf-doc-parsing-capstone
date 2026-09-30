"""Run O6 rules over six fixed parsed representations; never read labels."""
import argparse
import csv
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

from inputs import ROOT, REPO, load_document, read_json, sha256, lf_bytes
from rules import FIELDS, RULESET_VERSION, extract_fields


def run_experiment(manifest_path=ROOT / 'input_manifest.json', output=ROOT / 'results', repo=REPO):
    manifest_path, output = Path(manifest_path), Path(output).resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError('Outputs must stay within this O6 experiment folder')
    manifest = read_json(manifest_path)
    rows = []
    if len({x['document_id'] for x in manifest['documents']}) != len(manifest['documents']):
        raise ValueError('Duplicate manifest document IDs')
    code_hashes = {n: sha256(lf_bytes((ROOT / n).read_bytes())) for n in ('extract.py', 'inputs.py', 'rules.py')}
    for entry in manifest['documents']:
        started = perf_counter()
        pages, title, provenance = load_document(entry, repo)
        loaded = perf_counter()
        result = extract_fields(pages, title)
        finished = perf_counter()
        provenance.update(source_revision=manifest['source_revision'],
                          parser_selection='fixed_input_outside_O6_scope',
                          manifest_sha256_utf8_lf=sha256(lf_bytes(manifest_path.read_bytes())),
                          code_sha256_utf8_lf=code_hashes)
        row = dict(schema_version='1.0.0', ruleset_version=RULESET_VERSION,
                   document_id=entry['document_id'], provenance=provenance, **result,
                   runtime=dict(input_validation_seconds=loaded-started,
                                rules_seconds=finished-loaded, total_seconds=finished-started,
                                python=sys.version.split()[0], platform=platform.platform()))
        rows.append(row)
        print(entry['document_id'], row['document_type']['value'], row['reference_date']['value'], row['status'])
    # Validate all inputs before producing any output files. No silent skipped docs.
    output.mkdir(parents=True, exist_ok=True)
    (output / 'metadata.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8', newline='\n')
    with (output / 'summary.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['document_id', *FIELDS, 'status', 'warnings', 'runtime_seconds'])
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(document_id=row['document_id'],
                                 **{f: json.dumps(row[f]['value'], ensure_ascii=False) if isinstance(row[f]['value'], dict) else row[f]['value'] for f in FIELDS},
                                 status=row['status'], warnings='; '.join(row['warnings']),
                                 runtime_seconds=row['runtime']['total_seconds']))
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT / 'input_manifest.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'results')
    args = parser.parse_args()
    run_experiment(args.manifest, args.output)
