"""Additional descriptive metrics from saved scores; never run or fit a model."""
from collections import Counter
from functools import lru_cache
from pathlib import Path
import statistics

from common import DATA, read, sha, sam_paths

STRUCTURED = ('paddle_vl', 'glm', 'monkey', 'mineru_table')


def mean(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


@lru_cache(maxsize=32)
def saved_pairs(path, modified, size):
    return read(path)


@lru_cache(maxsize=20000)
def recognition_seconds(path, modified, size):
    return read(path).get('seconds')


@lru_cache(maxsize=256)
def native_ranking(values):
    # Reuse Sam's exact ranking definitions and deterministic issuer bootstrap.
    sam_paths()
    from analyze import ranking
    rows = [dict(issuer=issuer, native_numeric=native, fact_f1=truth)
            for issuer, native, truth in values]
    return ranking(rows, 'native_numeric', 'fact_f1')


def prediction_details(rows):
    rows = [r for r in rows if r.get('split') == 'test'
            and r.get('fact_f1') is not None and 'expected_f1' in r]
    if not rows:
        return None
    sam_paths()
    from calibration_round2 import metrics
    predictions = [dict(table_id=r['table_id'], issuer=r['issuer'], truth=r['fact_f1'],
                        prediction=r['expected_f1'], baseline=r['baseline'],
                        selected_feature=r['selected_feature'], review=r['review']) for r in rows]
    result = metrics(predictions)
    bad = [p for p in predictions if p['truth'] < .95]
    caught = sum(p['review'] for p in bad)
    result['triage'] = dict(reviewed=sum(p['review'] for p in predictions),
                            total=len(predictions), errors=len(bad), caught=caught,
                            error_capture=caught/len(bad) if bad else None)
    return result


def collect_details(run, summary):
    """Select the historical prefix, even if newer pairs/inference already exist.

    Original summary JSON, score caches, references and inference stay untouched.
    Refuse stale scores instead of presenting changed rows as an old milestone.
    """
    run = Path(run)
    ledger_path = run/'batch-progress.json'
    ledger = read(ledger_path) if ledger_path.exists() else None
    manifest_path = DATA/'tables.json'
    manifest = read(manifest_path)['tables'] if manifest_path.exists() else []
    by_id = {t['table_id']: t for t in manifest}
    specs = summary.get('splits', {summary.get('split', 'development'): summary})
    pairs = []
    sources = {}
    for split, spec in specs.items():
        count = spec['scored_tables']
        if ledger:
            batches = ledger['batches']
            if 'completed_batches' in summary:
                batches = batches[:summary['completed_batches']]
            ordered = [tid for b in batches if b['split'] == split for tid in b['table_ids']]
        else:
            ordered = [t['table_id'] for t in manifest if t['split'] == split]
        if len(ordered) < count:
            raise ValueError('Cannot identify the saved table prefix for '+split)
        ids = set(ordered[:count])
        path = run/split/'pairs.json'
        if not path.exists():
            return None
        stat = path.stat()
        payload = saved_pairs(str(path), stat.st_mtime_ns, stat.st_size)
        rows = [dict(r, split=split) for r in payload['pairs']
                if r['table_id'] in ids and r['engine'] in summary['engines']]
        expected = {(tid, engine) for tid in ids for engine in summary['engines']}
        actual = [(r['table_id'], r['engine']) for r in rows]
        if len(actual) != len(expected) or set(actual) != expected:
            raise ValueError('Incomplete saved scores for '+split)
        pairs.extend(rows)
        sources[split] = dict(path=str(path), sha256=sha(path), selected_tables=count,
                              scoring_provenance=payload.get('provenance'))

    engines = {}
    for engine, original in summary['engines'].items():
        rows = [r for r in pairs if r['engine'] == engine]
        valid = [r for r in rows if r.get('fact_f1') is not None]
        for key in ('fact_f1', 'financial_value_recall'):
            value = mean(r.get(key) for r in rows)
            old = original[key]
            if (value is None) != (old is None) or (value is not None and abs(value-old) > 1e-12):
                raise ValueError('Saved scores changed since this summary: '+engine+' '+key)
        if len(rows) != original['planned'] or dict(Counter(r['inference_status'] for r in rows)) != original['statuses']:
            raise ValueError('Saved coverage changed since this summary: '+engine)
        native = [r['native_numeric'] for r in rows if r.get('native_numeric') is not None]
        grits = [r['grits_content_f1'] for r in rows if r.get('grits_content_f1') is not None]
        times = []
        for r in rows:
            path = run/r['split']/engine/(r['table_id']+'.json')
            if path.exists():
                stat = path.stat()
                seconds = recognition_seconds(str(path), stat.st_mtime_ns, stat.st_size)
                if seconds is not None:
                    times.append(seconds)
        split_rankings = {}
        for split in specs:
            values = tuple((r['issuer'], r['native_numeric'], r['fact_f1']) for r in valid
                           if r['split'] == split and r.get('native_numeric') is not None)
            if engine in STRUCTURED:
                split_rankings[split] = native_ranking(values)
        engines[engine] = dict(n=len(rows), eligible_f1_tables=len(valid),
            mean_fact_f1=mean(r['fact_f1'] for r in valid), mean_grits=mean(grits),
            grits_tables=len(grits), mean_number_recall=mean(r.get('financial_value_recall') for r in rows),
            number_recall_tables=sum(r.get('financial_value_recall') is not None for r in rows),
            numeric_coverage=len(native), mean_native_numeric=mean(native),
            native_range=[min(native), max(native)] if native else None,
            median_recognition_seconds=statistics.median(times) if times else None,
            timed_outputs=len(times), truncated=sum(bool(r.get('truncated')) for r in rows),
            errors_below_95=sum(r['fact_f1'] < .95 for r in valid),
            exact_tables=sum(r['fact_f1'] >= 1-1e-9 for r in valid),
            ranking_by_split=split_rankings, prediction=prediction_details(rows))

    identities = {(r['split'], r['table_id']) for r in pairs}
    financial = {(r['split'], r['table_id']) for r in pairs if r.get('financial_reference_eligible')}
    test = [r for r in pairs if r['split'] == 'test']
    flags = {}
    for r in pairs:
        if r.get('measurement_flags'):
            flags[r['table_id']] = r['measurement_flags']
    known_sources = [by_id[tid].get('document') for _, tid in identities if tid in by_id]
    return dict(counts=dict(unique_crops=len(identities), outputs=len(pairs),
        financial_crops=len(financial), no_financial_facts=len(identities-financial),
        source_reports=len(set(known_sources)) if len(known_sources) == len(identities) else None,
        financial_issuers=len({r.get('issuer') for r in pairs if r.get('financial_reference_eligible')}),
        issuers=len({r['issuer'] for r in pairs if r.get('issuer') is not None}),
        final_test_crops=len({r['table_id'] for r in test}),
        final_test_issuers=len({r.get('issuer') for r in test}), configurations=len(engines),
        models=len({'mineru' if e == 'mineru_table' else e for e in engines})),
        engines=engines, measurement_flags=flags, source_pairs=sources,
        scope='Descriptive development metrics; test metrics use test rows only',
        runtime_scope='Median saved per-output seconds within this report prefix, including first-output setup; excludes separate scoring/calibration',
        reference_status='Public labels; independent human audit pending')
