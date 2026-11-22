"""Exploratory issuer-held-out forecasts; preserve the production run and freeze."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

OUT = Path(__file__).resolve().parent
CPU = OUT.parents[2]
ROOT = CPU.parents[2]
SAM = ROOT/'people/samhu/2026-11-15_table_confidence/results/native_prototype'
RUN = OUT.parent
sys.path.insert(0, str(CPU))
from common import read, sam_paths, sha, write
sam_paths()
from calibration_round2 import outer_predictions, metrics, FEATURES
from evaluate_table_accuracy import spearman, error_auc

ENGINES = ('paddle_vl', 'mineru_table', 'glm', 'monkey')
files = [RUN/'development/pairs.json', RUN/'batch-results/batch-03.json',
         RUN/'batch-results/batch-03-metrics.json', RUN/'data_snapshot/tables.json',
         SAM/'round2/development_validation.json', SAM/'round2/test_pairs.json', SAM/'findings.json',
         SAM.parent.parent/'prototype/calibration_round2.py']
# The code is at the project root's prototype, beside results/.
files[-1] = SAM.parent.parent/'prototype/calibration_round2.py'
before = {str(path.relative_to(ROOT)): sha(path) for path in files}
freeze_before = sha(RUN/'calibrators-frozen.json') if (RUN/'calibrators-frozen.json').exists() else None
tables = [r for r in read(RUN/'data_snapshot/tables.json')['tables'] if r['split'] == 'development'][:300]
ids = {t['table_id'] for t in tables}
all_rows = [r for r in read(RUN/'development/pairs.json')['pairs'] if r['table_id'] in ids]
assert len(all_rows) == 2100 and len(ids) == 300
sam_test_rows = read(SAM/'round2/test_pairs.json')['pairs']
sam_cv = {r['engine']: r for r in read(SAM/'round2/development_validation.json')['summaries']
          if r['method'] == 'header_selected'}
sam_findings = {r['engine']: r for r in read(SAM/'findings.json')['final_comparison']}
summary = read(RUN/'batch-results/batch-03.json')


def pearson(rows):
    rows = [r for r in rows if r.get('native_numeric') is not None and r.get('fact_f1') is not None]
    xs = [r['native_numeric'] for r in rows]
    ys = [r['fact_f1'] for r in rows]
    if len(xs) < 3:
        return None
    xm, ym = statistics.mean(xs), statistics.mean(ys)
    numerator = sum((x-xm)*(y-ym) for x, y in zip(xs, ys))
    denom = math.sqrt(sum((x-xm)**2 for x in xs)*sum((y-ym)**2 for y in ys))
    return numerator/denom if denom else None


results = {}
for engine in ENGINES:
    rows = [r for r in all_rows if r['engine'] == engine and r['fact_f1'] is not None]
    assert len(rows) == 283 and len({r['issuer'] for r in rows}) == 9
    assert abs(statistics.mean(r['fact_f1'] for r in rows)-summary['engines'][engine]['fact_f1']) < 1e-12
    print('Computing nested issuer-held-out forecasts:', engine, flush=True)
    predictions = outer_predictions(rows, target='fact_f1', select=True)
    assert len(predictions) == len(rows)
    assert Counter(p['table_id'] for p in predictions) == Counter(r['table_id'] for r in rows)
    truth = {r['table_id']: r for r in rows}
    folds = {}
    for p in predictions:
        source = truth[p['table_id']]
        assert p['truth'] == source['fact_f1']
        assert source['issuer'] not in p['training_issuers']
        assert p['issuer'] == source['issuer']
        training = [r for r in rows if r['issuer'] != p['issuer']]
        assert p['training_rows'] == len(training)
        assert set(p['training_issuers']) == {r['issuer'] for r in training}
        assert abs(p['baseline']-statistics.mean(r['fact_f1'] for r in training)) < 1e-12
        assert 0 <= p['prediction'] <= 1
        if p['missing_selected_confidence']:
            assert p['prediction'] == p['baseline']
        folds[p['issuer']] = {k:p[k] for k in ('selected_feature', 'training_rows', 'training_issuers', 'inner_mse')}
    score = metrics(predictions)
    # Independently recompute both losses and baseline losses.
    for key, value in dict(
        mae=sum(abs(p['prediction']-p['truth']) for p in predictions)/len(predictions),
        mse=sum((p['prediction']-p['truth'])**2 for p in predictions)/len(predictions),
        baseline_mae=sum(abs(p['baseline']-p['truth']) for p in predictions)/len(predictions),
        baseline_mse=sum((p['baseline']-p['truth'])**2 for p in predictions)/len(predictions)).items():
        assert abs(score[key]-value) < 1e-12
    native = [r for r in rows if r.get('native_numeric') is not None]
    sam_native = [r for r in sam_test_rows if r['engine'] == engine and r.get('native_numeric') is not None and r.get('fact_f1') is not None]
    assert len(sam_native) == 11
    correlation = dict(
        ours_pearson=pearson(native), sam_test_pearson=pearson(sam_native),
        ours_spearman=spearman([r['native_numeric'] for r in native], [r['fact_f1'] for r in native]),
        sam_test_spearman=spearman([r['native_numeric'] for r in sam_native], [r['fact_f1'] for r in sam_native]),
        ours_error_auc=error_auc([r['native_numeric'] for r in native], [r['fact_f1'] >= .95 for r in native]),
        sam_test_error_auc=error_auc([r['native_numeric'] for r in sam_native], [r['fact_f1'] >= .95 for r in sam_native]),
        ours_rows=len(native), sam_test_rows=len(sam_native))
    assert abs(correlation['sam_test_spearman']-sam_findings[engine]['prediction']['ranking']['spearman']) < 1e-12
    assert abs(correlation['sam_test_error_auc']-sam_findings[engine]['prediction']['ranking']['error_auc_below_95']) < 1e-12
    results[engine] = dict(ours_development_cv=score, sam_development_cv=sam_cv[engine],
        sam_final_test=sam_findings[engine]['prediction'], correlations=correlation,
        folds=folds, predictions=[{k:v for k,v in p.items() if k not in ('inner_mse', 'training_issuers')}
                                 for p in predictions])
    print(engine, 'MAE', score['mae'], 'MSE', score['mse'], 'gain', score['mse_gain'],
          'gain CI', score['mse_gain_issuer_bootstrap_95'], flush=True)

assert before == {str(path.relative_to(ROOT)): sha(path) for path in files}
freeze_after = sha(RUN/'calibrators-frozen.json') if (RUN/'calibrators-frozen.json').exists() else None
assert freeze_before == freeze_after
output = dict(scope='Exploratory development cross-validation on the saved 300-table prefix; not final held-out test results',
    method='Nested leave-one-issuer-out validation; select among 12 native features inside each training fold, then isotonic regression',
    baseline='Mean financial F1 of the outer training issuers; no held-out labels used',
    missing_confidence_policy='Use outer training mean and retain the row',
    candidate_features=list(FEATURES), table_count=300, eligible_financial_tables_per_engine=283,
    outer_issuer_folds=9, sam_development_cv=dict(rows_per_engine=94, issuers=42),
    sam_final_test=dict(rows_per_engine=11, issuers=11), sources_sha256=before,
    scientific_code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    native_correlation_feature='native_numeric', error_definition='financial fact F1 < 0.95; lower confidence predicts errors',
    pearson_note='Computed from saved pairs for this report; not a metric in Sam\'s original headline summary',
    canonical_calibration_unchanged=True, no_ocr_or_model_weight_training=True, validation='Passed issuer separation, count, range, baseline and independent-loss checks',
    engines=results)
write(OUT/'exploratory_development_forecasts.json', output)
print('Saved', OUT/'exploratory_development_forecasts.json', flush=True)
