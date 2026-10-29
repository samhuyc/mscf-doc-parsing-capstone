"""Run Sam's unchanged 54-label scorer and 18-row sponsor diagnostics."""
import csv
import json
from common import ROOT, PARSER, REFERENCE, dump, load, scorer
from comparison import baseline_parity


def main():
    b = scorer()
    b.validate(b.read_jsonl(ROOT/'labels.jsonl'), b.read_json(ROOT/'documents.json'))
    b.refresh_annotations()
    reviewed = b.score()
    preliminary = b.score(include_drafts=True)
    baseline = b.read_json(REFERENCE/'2026-10-05_pilot_benchmark/results/preliminary.json')
    baseline_parity(preliminary,baseline,b.PARSERS[:-1])
    with (ROOT/'results/metrics.csv').open('w', newline='') as out:
        writer = csv.DictWriter(out, fieldnames=['parser','metric','value','passed','total','numerator','denominator','equal_document_mean'])
        writer.writeheader()
        for parser, metrics in preliminary['aggregate'].items():
            for name, metric in metrics.items():
                writer.writerow(dict(parser=parser, metric=name, **{k: metric.get(k) for k in writer.fieldnames[2:]}))
    # Sam's earlier source-row/native-text diagnostics, with only paths and parser list changed.
    earlier = load('sam_sponsor_evaluate', REFERENCE/'2026-09-29_sponsor_samples/evaluate.py')
    earlier.ROOT = ROOT
    earlier.PARSERS = (PARSER,)
    # His earlier diagnostic uses results/<doc>/<parser>, whereas the October
    # scorer uses results/parsed/<doc>/<parser>. Point both at the same exports.
    for source in b.read_json(ROOT/'source_manifest.json'):
        alias=ROOT/'results'/source['id']
        destination=ROOT/'results/parsed'/source['id']
        if alias.is_symlink():
            assert alias.resolve()==destination.resolve()
        elif alias.exists():
            raise FileExistsError(f'Unexpected earlier-evaluation path: {alias}')
        else:
            alias.symlink_to(destination.relative_to(alias.parent),target_is_directory=True)
    earlier.main()
    processed=sum(r['exported_pages'] for r in preliminary['runs'] if r['parser']==PARSER)
    dump(ROOT/'evaluation/scope.json',dict(source_pages=140,processed_pages=processed,
         full_document_diagnostics_comparable=processed==140,
         note='The 18-row/50-value spot-check pages are present. Native text diagnostics include unprocessed source pages as missing and are not a full-run accuracy comparison when coverage is partial.'))
    dump(ROOT/'results/evaluation_verification.json', dict(baseline_metrics_unchanged=True,
         selected_labels=preliminary['selected_labels'], reviewed_labels=reviewed['selected_labels'],
         label_sha256=preliminary['label_sha256'], scorer_sha256=preliminary['scorer_sha256'],
         per_document_baselines_exact=True,equal_document_mean_roundoff_tolerance=1e-14))
    print(json.dumps(preliminary['aggregate'][PARSER], indent=2))


if __name__ == '__main__':
    main()
