"""Separate correctness models with grouped diagnostics and explicit calibration.

Default: exploratory leave-one-document-family-out diagnostics on the current
draft labels. Public probabilities remain null. An explicit verified-data split
can fit a base model, calibrate on separate families and evaluate on a third set.
No claim of deployment calibration follows automatically from successful fitting.
"""
import argparse
import csv
import hashlib
import html
import json
import math
import re
from decimal import Decimal
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parent
NUMERIC_FEATURES = (
    'well_formed_number', 'comparison_available', 'numeric_value_agreement',
    'comparison_text_similarity', 'numeric_token_count', 'decimal_point_count',
    'digit_count', 'has_explicit_sign', 'has_currency', 'has_percent',
)
ASSOCIATION_FEATURES = (
    'row_label_unmerged', 'value_cell_unmerged', 'unique_comparison_row',
    'column_header_bound', 'column_header_agreement', 'header_comparison_available',
    'header_text_similarity',
)
FEATURES = {'numeric': NUMERIC_FEATURES, 'association': ASSOCIATION_FEATURES}
TARGETS = {
    'numeric': 'Numeric content of this returned value is transcribed correctly, including sign/decimal. This is not row/year correctness.',
    'association': 'The exported cell has the correct unambiguous row and column association. Numeric content and unit correctness are separate.',
}


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def family(row):
    """Explicit family overrides support future documents; existing RR pair stays together."""
    doc = row['document']
    if doc.startswith('rolls_royce_2026h1_'):
        if row.get('document_family') not in (None,'','rolls_royce_2026h1'):
            raise ValueError('related_document_family_mismatch')
        return 'rolls_royce_2026h1'
    if row.get('document_family'):
        return row['document_family']
    return doc


def compact(value):
    return re.sub(r'\s+', '', str(value)).replace('−', '-').casefold()


def number(value):
    """Conservative parsing: preserve sign, currency and suffix; reject malformed grouping."""
    if value is None:
        return None
    s = compact(value)
    suffix = next((x for x in ('pts', '%', 'p') if s.endswith(x)), '')
    if suffix:
        s = s[:-len(suffix)]
    currency = s[0] if s and s[0] in '$£€' else ''
    if currency:
        s = s[1:]
    parenthesized = s.startswith('(') and s.endswith(')')
    if parenthesized:
        s = s[1:-1]
        if s.startswith(('+', '-')):
            return None
    elif '(' in s or ')' in s:
        return None
    if not re.fullmatch(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', s):
        return None
    val = Decimal(s.replace(',', ''))
    return (-val if parenthesized else val, currency, suffix)


def feature_values(row):
    """Read only extracted evidence, never labels, references, IDs or review status."""
    text = row['extracted_value']
    comparison = row.get('comparison_value')
    other_header = row.get('comparison_header')
    parsed, other = number(text), number(comparison)
    features = row['features']
    values = {
        'well_formed_number': float(parsed is not None),
        'comparison_available': float(comparison is not None),
        'numeric_value_agreement': float(parsed is not None and other is not None and parsed == other),
        'comparison_text_similarity': SequenceMatcher(None, compact(text), compact(comparison)).ratio() if comparison is not None else 0.,
        'numeric_token_count': float(len(re.findall(r'\d[\d,]*(?:\.\d+)?', text))),
        'decimal_point_count': float(text.count('.')),
        'digit_count': float(sum(c.isdigit() for c in text)),
        'has_explicit_sign': float(any(c in text for c in '()-−+')),
        'has_currency': float(any(c in text for c in '$£€')),
        'has_percent': float('%' in text),
        'header_comparison_available': float(other_header is not None),
        'header_text_similarity': SequenceMatcher(None, compact(row['column_header']), compact(other_header)).ratio() if other_header is not None else 0.,
    }
    for key in ASSOCIATION_FEATURES[:5]:
        values[key] = float(features[key])
    return values


def matrix(rows, target):
    return np.array([[feature_values(r)[k] for k in FEATURES[target]] for r in rows], dtype=float)


def labels(rows, target):
    values = []
    for row in rows:
        keys = ['numeric_correct'] if target == 'numeric' else ['row_correct', 'column_correct']
        if not all(isinstance(row.get(k), bool) for k in keys):
            raise ValueError(f'Missing/uncertain {target} label: {row.get("sample_id")}')
        values.append(int(all(row[k] for k in keys)))
    return np.array(values, dtype=int)


def train(rows, target):
    y = labels(rows, target)
    if len(set(y)) < 2:
        raise ValueError('training_partition_has_only_one_class')
    # Fixed settings, no search against this pilot; no class balancing or oversampling.
    estimator = make_pipeline(StandardScaler(), LogisticRegression(C=1., solver='lbfgs', max_iter=2000, random_state=0))
    estimator.fit(matrix(rows, target), y)
    if estimator[-1].n_iter_.max() >= 2000:
        raise ValueError('optimizer_did_not_converge')
    return estimator


def serialize(estimator, target):
    return dict(feature_names=list(FEATURES[target]), mean=estimator[0].mean_.tolist(),
                scale=estimator[0].scale_.tolist(), coefficients=estimator[1].coef_[0].tolist(),
                intercept=float(estimator[1].intercept_[0]), penalty_C=1.)


def predict_saved(model, rows, target):
    if model['feature_names'] != list(FEATURES[target]):
        raise ValueError('feature_schema_mismatch')
    x = (matrix(rows, target) - np.array(model['mean'])) / np.array(model['scale'])
    logits = x @ np.array(model['coefficients']) + model['intercept']
    return 1/(1+np.exp(-np.clip(logits, -700, 700)))


def reliability(y, p):
    bins = []
    for i in range(5):
        selected = (p >= i/5) & ((p < (i+1)/5) if i < 4 else (p <= 1))
        if selected.any():
            bins.append(dict(lower=i/5, upper=(i+1)/5, n=int(selected.sum()),
                             predicted=float(p[selected].mean()), observed=float(y[selected].mean())))
    return bins


def metrics(y, p):
    if not len(y):
        return None
    return dict(n=len(y), correct=int(y.sum()), errors=int((1-y).sum()),
                brier=float(brier_score_loss(y, p)),
                log_loss=float(log_loss(y, np.column_stack([1-p, p]), labels=[0, 1])),
                roc_auc=float(roc_auc_score(y, p)) if len(set(y)) == 2 else None,
                reliability=reliability(y, p))


def diagnostics(rows, target):
    """Out-of-family predictions. Failed folds remain explicit, never filled in-sample."""
    predictions, folds = [], []
    for held in sorted({family(r) for r in rows}):
        fitting = [r for r in rows if family(r) != held]
        testing = [r for r in rows if family(r) == held]
        fold = dict(held_family=held, train_families=sorted({family(r) for r in fitting}),
                    train_n=len(fitting), test_n=len(testing),
                    test_errors=int((1-labels(testing, target)).sum()))
        try:
            model = train(fitting, target)
        except ValueError as exc:
            fold.update(status='not_scored', reason=str(exc))
            predictions.extend(dict(sample_id=r['sample_id'], family=held, target=target,
                                    actual=int(y), diagnostic_probability=None, status='not_scored')
                               for r,y in zip(testing, labels(testing, target)))
        else:
            p = model.predict_proba(matrix(testing, target))[:,1]
            baseline = float(labels(fitting, target).mean())
            fold.update(status='scored_exploratory', metrics=metrics(labels(testing, target), p),
                        constant_train_rate_baseline=metrics(labels(testing, target), np.full(len(testing), baseline)))
            predictions.extend(dict(sample_id=r['sample_id'], family=held, target=target, actual=int(y),
                                    diagnostic_probability=float(v), status='uncalibrated_out_of_family')
                               for r,y,v in zip(testing, labels(testing, target), p))
        folds.append(fold)
    scored = [p for p in predictions if p['diagnostic_probability'] is not None]
    return dict(folds=folds, predictions=predictions, coverage=len(scored)/len(rows),
                scored_errors=sum(p['actual']==0 for p in scored),
                total_errors=int((1-labels(rows, target)).sum()),
                metrics_on_scored_only=metrics(np.array([p['actual'] for p in scored]),
                                               np.array([p['diagnostic_probability'] for p in scored])),
                interpretation='Draft-label, uncalibrated retrospective diagnostics. Coverage and error coverage must accompany metrics.')


def split_rows(rows, assignments):
    if set(assignments) != {'train', 'calibration', 'test'}:
        raise ValueError('split_must_have_train_calibration_test')
    groups = {part:set(assignments[part]) for part in assignments}
    if any(not g for g in groups.values()):
        raise ValueError('empty_partition')
    if any(groups[a] & groups[b] for a,b in [('train','calibration'),('train','test'),('calibration','test')]):
        raise ValueError('document_family_leakage')
    if set.union(*groups.values()) != {family(r) for r in rows}:
        raise ValueError('split_must_assign_every_family_exactly_once')
    ids=[r['sample_id'] for r in rows]
    if len(ids)!=len(set(ids)):
        raise ValueError('duplicate_sample_id')
    return {part:[r for r in rows if family(r) in selected] for part,selected in groups.items()}


def fit_calibrated(rows, target, assignments):
    """A real training/calibration/test path; never use test labels to fit either stage."""
    parts = split_rows(rows, assignments)
    for part, subset in parts.items():
        if not all(r.get('human_verified') is True and r.get('reviewer') not in (None,'','assistant') for r in subset):
            raise ValueError(f'{part}: independently_reviewed_labels_required')
        if len(set(labels(subset, target))) != 2:
            raise ValueError(f'{part}: both_correct_and_incorrect_examples_required')
    estimator = train(parts['train'], target)
    calibration_logits = estimator.decision_function(matrix(parts['calibration'], target)).reshape(-1,1)
    calibrator = LogisticRegression(C=1., solver='lbfgs', max_iter=2000, random_state=0)
    calibrator.fit(calibration_logits, labels(parts['calibration'], target))
    # A fixed regularized sigmoid calibration model; performance is assessed, not assumed.
    raw = estimator.predict_proba(matrix(parts['test'], target))[:,1]
    test_logits = estimator.decision_function(matrix(parts['test'], target)).reshape(-1,1)
    calibrated = calibrator.predict_proba(test_logits)[:,1]
    y = labels(parts['test'], target)
    baseline = np.full(len(y), labels(parts['train'], target).mean())
    result = dict(status='experimental_calibrated_model_evaluated_not_deployment_approved',
                  target=TARGETS[target], split=assignments, base=serialize(estimator,target),
                  sigmoid=dict(slope=float(calibrator.coef_[0,0]), intercept=float(calibrator.intercept_[0]), penalty_C=1.),
                  test_raw=metrics(y,raw), test_calibrated=metrics(y,calibrated), test_baseline=metrics(y,baseline),
                  calibrated_brier_improves_baseline=bool(brier_score_loss(y,calibrated)<brier_score_loss(y,baseline)),
                  predictions=[dict(sample_id=r['sample_id'], raw=float(p), calibrated=float(q), actual=int(t))
                               for r,p,q,t in zip(parts['test'],raw,calibrated,y)],
                  note='Minimum checks prevent leakage/one-class fitting; passing them does not prove calibration or adequate sample size.')
    return result


def infer(models, rows):
    """Apply already-fitted models to label-free records; never refit at inference."""
    output=[dict(sample_id=r['sample_id'], numeric=None, association=None) for r in rows]
    for target in TARGETS:
        model=models.get(target,{})
        if model.get('status')!='experimental_calibrated_model_evaluated_not_deployment_approved':
            for r in output:
                r[target]=dict(estimated_probability=None,status='calibrated_model_unavailable')
            continue
        base=model['base']
        if base['feature_names']!=list(FEATURES[target]):
            raise ValueError('feature_schema_mismatch')
        x=(matrix(rows,target)-np.array(base['mean']))/np.array(base['scale'])
        logits=x @ np.array(base['coefficients'])+base['intercept']
        transformed=model['sigmoid']['slope']*logits+model['sigmoid']['intercept']
        probabilities=1/(1+np.exp(-np.clip(transformed,-700,700)))
        for r,p in zip(output,probabilities):
            r[target]=dict(estimated_probability=float(p),status='experimental_calibrated_estimate',
                           target=TARGETS[target], deployment_approved=False)
    return output


def audit(rows, target):
    y = labels(rows,target)
    failure_families=sorted({family(r) for r,v in zip(rows,y) if not v})
    verified=sum(r.get('human_verified') is True for r in rows)
    reasons=[]
    if verified < len(rows):
        reasons.append('independent_review_incomplete')
    if len(failure_families)<3:
        reasons.append('errors_cannot_be_distributed_across_three_disjoint_family_partitions')
    return dict(target=TARGETS[target], samples=len(rows), correct=int(y.sum()), errors=int((1-y).sum()),
                families=sorted({family(r) for r in rows}), error_families=failure_families,
                independently_reviewed=verified, calibrated_probability_available=False,
                blockers=reasons or ['explicit_train_calibration_test_run_required'])


def write_review_queue(rows, path):
    fields=['sample_id','document','page','extracted_value','column_header','reference_value','row_label',
            'proposed_numeric_correct','proposed_row_correct','proposed_column_correct',
            'human_numeric_correct','human_row_correct','human_column_correct','reviewer','reviewed_at','notes']
    with path.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in rows:
            row={k:r.get(k,'') for k in fields[:7]}
            for key in ['numeric_correct','row_correct','column_correct']:
                row['proposed_'+key]=str(r[key]).lower()
            writer.writerow(row)


def import_reviews(rows, review_path):
    """Review happens outside this script. Blank/uncertain decisions stay unverified."""
    with Path(review_path).open(newline='') as f:
        decisions=list(csv.DictReader(f))
    known={r['sample_id']:r for r in rows}; seen=set(); output={k:dict(v) for k,v in known.items()}
    for d in decisions:
        sid=d['sample_id']
        if sid not in known or sid in seen:
            raise ValueError('unknown_or_duplicate_review_id')
        seen.add(sid)
        if (d['extracted_value'] != known[sid]['extracted_value'] or d['document']!=known[sid]['document']
                or str(d['page'])!=str(known[sid]['page']) or d['column_header']!=known[sid]['column_header']
                or d['row_label']!=known[sid]['row_label']):
            raise ValueError('stale_review_identity_or_value')
        keys=['numeric_correct','row_correct','column_correct']
        values=[d['human_'+k].strip().lower() for k in keys]
        if not any(values):
            continue
        if any(v not in ('true','false') for v in values):
            raise ValueError('complete_explicit_boolean_review_required')
        if not d['reviewer'].strip() or d['reviewer'].strip().lower() in ('assistant','codex') or not d['reviewed_at'].strip():
            raise ValueError('reviewer_and_review_date_required')
        output[sid].update({k:v=='true' for k,v in zip(keys,values)})
        output[sid].update(human_verified=True, reviewer=d['reviewer'].strip(), reviewed_at=d['reviewed_at'],
                           review_notes=d.get('notes',''), reviewed_targets=['numeric','association'],
                           unit_human_verified=False)
        output[sid]['correct']=all(output[sid][k] for k in ['numeric_correct','row_correct','column_correct','unit_correct'])
    return list(output.values())


def report(out, audits, runs):
    lines=['# Separate correctness models', '',
           'Individual-feature logistic models are implemented and fitted for exploratory diagnostics. Numeric transcription and row/column association are separate targets. No validated per-cell probability is available yet.', '',
           '| Target | Correct / total | Error families | Independent reviews | Out-of-family coverage | Errors in scored folds |',
           '|---|---:|---:|---:|---:|---:|']
    for target,a in audits.items():
        d=runs[target]
        lines.append(f"| {target} | {a['correct']}/{a['samples']} | {len(a['error_families'])} | {a['independently_reviewed']} | {d['coverage']:.0%} | {d['scored_errors']}/{d['total_errors']} |")
    lines += ['', '## Actual out-of-family diagnostic results', '',
              '| Target | Held family | Status | Brier loss | Training-rate baseline loss |',
              '|---|---|---|---:|---:|']
    for target,d in runs.items():
        for fold in d['folds']:
            if fold['status']=='not_scored':
                lines.append(f"| {target} | {fold['held_family']} | {fold['reason']} | — | — |")
            else:
                lines.append(f"| {target} | {fold['held_family']} | experimental only | {fold['metrics']['brier']:.4f} | {fold['constant_train_rate_baseline']['brier']:.4f} |")
    lines += ['', 'Lower loss is better, but partial coverage and draft labels prevent calibration claims. The association model struggles on the Rolls-Royce family: merged period headers are absent from its training documents. Numeric scored folds contain zero errors, so their small losses do not establish numeric-error detection.']
    lines += ['', '## Why a probability is still withheld', '',
              'The numeric errors in the current sample all come from EDF. Holding EDF out leaves training with no numeric errors, so that fold cannot fit a binary correctness model. The other numeric folds test only correct examples. A low loss on those folds would not validate error detection.', '',
              'Association labels describe correct row and column bindings, independently of numeric content. Only EDF and the Rolls-Royce family contain association failures, so errors cannot appear in three disjoint training/calibration/test family partitions. Units remain a separate review target; no unit probability is inferred.', '',
              'All existing labels are assistant-reviewed drafts. No synthetic errors, duplicated rows, other-parser labels or benchmark F1 scores are used as extra training truth.', '',
              '## Implementation', '',
              '- Numeric model: syntax, numeric/text agreement, comparison availability, token/decimal/digit counts, sign, currency and percentage markers.',
              '- Association model: distinct row/value cells, unique comparison row, bound header, header availability/agreement/similarity.',
              '- Fixed regularized logistic regression with fold-local scaling. No class balancing, oversampling or hyperparameter search against this sample.',
              '- Four document-family folds; the two Rolls-Royce documents always stay together. Failed folds remain missing rather than receiving in-sample substitutes.',
              '- Explicit verified-data workflow fits a base model on training families, a regularized sigmoid on calibration families, then reports raw/calibrated/baseline losses and reliability bins on test families. Successful execution does not automatically approve deployment.', '',
              '## Files', '',
              '- `data_audit.json`: exact data limitations per target.',
              '- `diagnostics.json`: folds, coverage, losses and reliability bins. Diagnostic probabilities are uncalibrated experimental model outputs, not confidence scores.',
              '- `exploratory_models.json`: fitted coefficients; deliberately not a deployed predictor.',
              '- `feature_rows.json`: label-free numeric and association feature vectors.',
              '- `review_queue.csv`: proposed labels plus blank human decision fields. Fill decisions only after reviewing the source.',
              '- `split_template.json`: illustrates explicit family assignments; the current draft data will fail eligibility checks.', '',
              'Source/render and annotation limitations remain in the parent README. More numerical variety does not establish that a probability is meaningful.']
    (out/'MODEL_REPORT.md').write_text('\n'.join(lines)+'\n')


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=ROOT/'reviewed_cells.json')
    p.add_argument('--output',type=Path,default=ROOT/'model_results')
    p.add_argument('--split',type=Path,help='Explicit JSON family assignments for verified training/calibration/testing.')
    p.add_argument('--review-csv',type=Path,help='Import explicit human decisions to a new file; never overwrite source labels.')
    p.add_argument('--model',type=Path,help='Apply an existing calibration_run.json to --input without reading any labels.')
    args=p.parse_args(); rows=read(args.input); out=args.output;out.mkdir(parents=True,exist_ok=True)
    if not isinstance(rows,list) or not rows:
        p.error('--input must contain a nonempty JSON array of cell records')
    if args.model:
        if args.review_csv or args.split:
            p.error('--model is inference-only and cannot be combined with review or fitting')
        write(out/'predictions.json',infer(read(args.model),rows))
        write(out/'provenance.json',dict(input_sha256=digest(args.input),model_sha256=digest(args.model),script_sha256=digest(__file__)))
        return
    if args.review_csv:
        rows=import_reviews(rows,args.review_csv)
        write(out/'reviewed_input.json',rows)
    if args.split:
        assignments=read(args.split)
        results={}
        for target in TARGETS:
            try:
                results[target]=fit_calibrated(rows,target,assignments)
            except ValueError as exc:
                results[target]=dict(status='not_fitted',reason=str(exc),confidence=None)
        write(out/'calibration_run.json',results)
        write(out/'provenance.json',dict(input_sha256=digest(args.input),split_sha256=digest(args.split),
                                        review_csv_sha256=digest(args.review_csv) if args.review_csv else None,
                                        script_sha256=digest(__file__),sklearn_version=sklearn.__version__))
        print(json.dumps({k:v['status'] for k,v in results.items()}))
        if any(v['status']=='not_fitted' for v in results.values()):
            raise SystemExit(2)
        return
    audits={t:audit(rows,t) for t in TARGETS}
    runs={t:diagnostics(rows,t) for t in TARGETS}
    models={}
    for target in TARGETS:
        try:
            models[target]=dict(status='exploratory_draft_labels_not_for_confidence',model=serialize(train(rows,target),target))
        except ValueError as exc:
            models[target]=dict(status='not_fitted',reason=str(exc))
    write(out/'data_audit.json',audits);write(out/'diagnostics.json',runs);write(out/'exploratory_models.json',models)
    write(out/'feature_rows.json',[dict(sample_id=r['sample_id'],document_family=family(r),features=feature_values(r)) for r in rows])
    queue=out/'review_queue.csv'
    if not queue.exists():
        write_review_queue(rows,queue)
    write(out/'split_template.json',{'train':['cvs_2025q2','edf_2024'],'calibration':['hippodrome_2025'],'test':['rolls_royce_2026h1']})
    write(out/'provenance.json',dict(input_path=str(args.input),input_sha256=digest(args.input),script_sha256=digest(__file__),
                                   numpy_version=np.__version__,sklearn_version=sklearn.__version__,
                                   source_review_csv_sha256=digest(args.review_csv) if args.review_csv else None))
    report(out,audits,runs)
    print(json.dumps(audits,indent=2))


if __name__=='__main__':
    main()
