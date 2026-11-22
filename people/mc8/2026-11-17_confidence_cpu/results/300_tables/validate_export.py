"""Verify the published snapshot without models, raw images or third-party packages."""
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent


def read(name):
    return json.loads((HERE / name).read_text())


def close(actual, expected):
    if expected is None:
        assert actual is None
    else:
        assert math.isclose(actual, expected, abs_tol=1e-12), (actual, expected)


def validate():
    provenance = read('export-provenance.json')
    for name, record in provenance['byte_preserved_exports'].items():
        assert hashlib.sha256((HERE / name).read_bytes()).hexdigest() == record['sha256'], name
    summary = read('summary.json')
    details = read('summary-metrics.json')
    rows = read('development/pairs.json')['pairs']
    tables = read('data_snapshot/tables.json')['tables']
    ledger = read('batch-progress.json')
    assert summary['completed_tables'] == 300
    assert summary['scored_outputs'] == len(rows) == 2100
    assert ledger['completed_batches'] == summary['completed_batches'] == 3
    ids = {row['table_id'] for row in rows}
    prefix = {table_id for batch in ledger['batches'][:3] for table_id in batch['table_ids']}
    assert ids == prefix and len(ids) == 300
    cohort = [table for table in tables if table['table_id'] in ids]
    assert len(tables) == 2000 and len(cohort) == 300
    assert {table['split'] for table in cohort} == {'development'}
    assert len({table['issuer'] for table in cohort}) == 9
    assert len({table['document'] for table in cohort}) == 55
    assert len({row['table_id'] for row in rows if row['financial_reference_eligible']}) == 283
    assert len({(row['table_id'], row['engine']) for row in rows}) == 2100
    assert set(Counter(row['engine'] for row in rows).values()) == {300}
    assert {row['inference_status'] for row in rows} == {'success'}
    assert {row['split'] for row in rows} == {'development'}
    for engine, saved in summary['engines'].items():
        group = [row for row in rows if row['engine'] == engine]
        facts = [row['fact_f1'] for row in group if row['fact_f1'] is not None]
        recall = [row['financial_value_recall'] for row in group
                  if row['financial_value_recall'] is not None]
        native = [row['native_numeric'] for row in group if row['native_numeric'] is not None]
        close(mean(facts) if facts else None, saved['fact_f1'])
        close(mean(recall), saved['financial_value_recall'])
        close(mean(native), details['engines'][engine]['mean_native_numeric'])
    with (HERE / 'scores.csv').open(newline='') as stream:
        csv_rows = list(csv.DictReader(stream))
    assert len(csv_rows) == 2100
    for exported, original in zip(csv_rows, rows):
        assert (exported['table_id'], exported['engine']) == (original['table_id'], original['engine'])
        for key in ('fact_f1', 'financial_value_recall', 'native_numeric'):
            close(float(exported[key]) if exported[key] else None, original[key])
    forecasts = read('presentation/exploratory_development_forecasts.json')
    for engine, saved in forecasts['engines'].items():
        group = [row for row in rows if row['engine'] == engine and row['fact_f1'] is not None]
        source = {row['table_id']: row for row in group}
        predictions = saved['predictions']
        assert len(predictions) == len(source) == 283
        assert {prediction['table_id'] for prediction in predictions} == set(source)
        for prediction in predictions:
            row = source[prediction['table_id']]
            assert prediction['truth'] == row['fact_f1']
            assert prediction['issuer'] == row['issuer']
            training = [other for other in group if other['issuer'] != row['issuer']]
            fold = saved['folds'][row['issuer']]
            assert set(fold['training_issuers']) == {other['issuer'] for other in training}
            assert row['issuer'] not in fold['training_issuers']
            assert fold['training_rows'] == prediction['training_rows'] == len(training)
            assert fold['selected_feature'] == prediction['selected_feature']
            close(prediction['baseline'], mean(other['fact_f1'] for other in training))
            assert 0 <= prediction['prediction'] <= 1
            if prediction['missing_selected_confidence']:
                close(prediction['prediction'], prediction['baseline'])
        metrics = saved['ours_development_cv']
        for column, prefix in (('prediction', ''), ('baseline', 'baseline_')):
            close(mean(abs(p[column] - p['truth']) for p in predictions), metrics[prefix + 'mae'])
            close(mean((p[column] - p['truth']) ** 2 for p in predictions), metrics[prefix + 'mse'])
        close(metrics['baseline_mse'] - metrics['mse'], metrics['mse_gain'])
    result = dict(status='passed', tables=300, scored_outputs=2100, financial_tables=283,
                  issuers=9, source_reports=55, byte_preserved_exports=len(provenance['byte_preserved_exports']),
                  aggregate_metrics_recomputed=True, csv_matches_pairs=True,
                  forecast_losses_and_baselines_recomputed=True, saved_fold_issuer_separation_verified=True,
                  final_test_evaluated=False, inference_run_by_validation=False)
    print(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    validate()
