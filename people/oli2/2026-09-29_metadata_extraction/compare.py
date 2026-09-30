"""Compare semantic decisions only; leave both experiment runs untouched."""
import argparse
import json
from pathlib import Path

from inputs import ROOT, read_json, sha256
from rules import FIELDS, RULESET_VERSION


def load_rows(path):
    rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if len({r['document_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate document IDs')
    return {r['document_id']: r for r in rows}


def compare(before_path, after_path):
    before, after = load_rows(before_path), load_rows(after_path)
    if set(before) != set(after):
        raise ValueError('Runs must contain the same documents')
    changes = []
    for doc in before:
        for field in FIELDS:
            old = {key: before[doc][field][key] for key in ('value', 'status', 'role')}
            new = {key: after[doc][field][key] for key in ('value', 'status', 'role')}
            if old != new:
                changes.append(dict(document_id=doc, field=field, before=old, after=new))
    return dict(before_rulesets=sorted({r['ruleset_version'] for r in before.values()}),
                after_rulesets=sorted({r['ruleset_version'] for r in after.values()}),
                before_sha256=sha256(before_path.read_bytes()), after_sha256=sha256(after_path.read_bytes()),
                comparison_scope='Field value, status and role only. Rule IDs, candidate rankings, evidence IDs, runtime and derived document status are not semantic field decisions.',
                documents_compared=len(before), changed_decisions=changes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', type=Path, default=ROOT / 'baseline' / '1.0.0' / 'results' / 'metadata.jsonl')
    parser.add_argument('--after', type=Path, default=ROOT / 'results' / RULESET_VERSION / 'metadata.jsonl')
    parser.add_argument('--output', type=Path, default=ROOT / 'results' / RULESET_VERSION / 'comparison.json')
    args = parser.parse_args()
    if (not args.output.resolve().is_relative_to(ROOT) or
            args.output.resolve().is_relative_to(ROOT / 'baseline') or args.output.exists()):
        parser.error('Choose a new comparison file inside the experiment, outside baseline archives')
    archive = ROOT / 'baseline' / '1.0.0'
    for name, digest in read_json(archive / 'integrity.json')['sha256'].items():
        if sha256((archive / name).read_bytes()) != digest:
            raise ValueError(f'Baseline archive changed: {name}')
        if name.startswith('results/') and sha256((ROOT / name).read_bytes()) != digest:
            raise ValueError(f'Original baseline results changed: {name}')
    report = compare(args.before, args.after)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
