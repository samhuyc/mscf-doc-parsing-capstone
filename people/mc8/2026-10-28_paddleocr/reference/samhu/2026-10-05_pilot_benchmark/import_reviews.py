"""Validate a browser review export; optionally apply and regenerate reports offline."""
import argparse
import copy
from datetime import datetime
import json

from benchmark import ROOT, read_json, read_jsonl, sha, validate, write_jsonl, refresh_annotations, score


def apply_decisions(labels, bundle, expected_hash):
    if bundle.get('schema_version') != 1 or bundle.get('label_sha256') != expected_hash:
        raise ValueError('Export does not match this label version; no changes applied.')
    decisions = bundle.get('decisions')
    if not isinstance(decisions, list):
        raise ValueError('Missing decisions list')
    updated = copy.deepcopy(labels)
    by_id = {x['id']: x for x in updated}
    seen = set()
    for decision in decisions:
        ident = decision.get('id')
        if ident not in by_id or ident in seen:
            raise ValueError('Unknown or duplicate label ID')
        seen.add(ident)
        label = by_id[ident]
        if decision.get('source_sha256') != label['source_sha256']:
            raise ValueError('Source hash mismatch')
        state = decision.get('status')
        reviewer, notes, when = decision.get('reviewer'), decision.get('notes'), decision.get('reviewed_at')
        if state not in {'pending','approved','needs_correction','excluded'}:
            raise ValueError('Invalid review state')
        if not isinstance(notes,str) or not isinstance(reviewer,str):
            raise ValueError('Reviewer and notes must be strings')
        if state != 'pending':
            if not reviewer.strip() or not isinstance(when,str):
                raise ValueError('A decision requires reviewer name and timestamp')
            parsed = datetime.fromisoformat(when.replace('Z','+00:00'))
            if parsed.tzinfo is None:
                raise ValueError('Review timestamp requires a timezone')
        if state in {'needs_correction','excluded'} and not notes.strip():
            raise ValueError('Correction or exclusion requires a note')
        label['review_decision'] = {k:decision.get(k) for k in ('status','notes','reviewer','reviewed_at','source_sha256')}
        label['review_status'] = {'approved':'human_verified','excluded':'excluded'}.get(state,'draft')
        label['reviewer'] = reviewer.strip() if state != 'pending' else None
        label['reviewed_at'] = when if state != 'pending' else None
        label['review_notes'] = notes
        if state == 'excluded':
            label['exclusion_reason'] = notes
        else:
            label.pop('exclusion_reason',None)
    return updated, len(seen)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('export_file')
    cli.add_argument('--apply',action='store_true',help='Apply validated decisions and regenerate coverage, scores and reports')
    args = cli.parse_args()
    label_path = ROOT/'labels.jsonl'
    before_hash = sha(label_path)
    updated, count = apply_decisions(read_jsonl(label_path),read_json(args.export_file),before_hash)
    validate(updated,read_json(ROOT/'documents.json'))
    if args.apply and count:
        backup = ROOT/'review_history'/f'labels-{before_hash}.jsonl'
        backup.parent.mkdir(exist_ok=True)
        if not backup.exists():
            backup.write_bytes(label_path.read_bytes())
        temporary = label_path.with_suffix('.jsonl.tmp')
        write_jsonl(temporary,updated)
        temporary.replace(label_path)
        refresh_annotations()
        score()
        score(include_drafts=True)
        from report import main as build_report
        build_report()
    print(json.dumps(dict(decisions=count,applied=bool(args.apply and count),
                          human_verified=sum(x['review_status'] in {'human_verified','adjudicated'} for x in updated))))


if __name__ == '__main__':
    main()
