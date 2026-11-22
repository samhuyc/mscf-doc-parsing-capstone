"""Explicit development-only monotone calibration; never overwrite a freeze."""
import argparse
from datetime import datetime,timezone
import math
from pathlib import Path
import statistics
from common import HERE, DATA, config, read, write, sha, environment, sam_paths, implementation_hashes


def check_freeze(run):
    frozen=read(run/'calibrators-frozen.json')
    expected=dict(config_sha256=sha(HERE/'config.json'),tables_sha256=sha(DATA/'tables.json'),
                  references_sha256=sha(DATA/'references.json'),
                  development_pairs_sha256=sha(run/'development/pairs.json'),sam_code_lock_sha256=sha(HERE/'sam-code-lock.json'),
                  adapter_sha256=sha(HERE/'sam_bridge.py'),evaluator_sha256=sha(HERE/'evaluate.py'),calibration_code_sha256=sha(HERE/'calibrate.py'),implementation=implementation_hashes())
    if frozen['provenance']!=expected:raise RuntimeError('Calibration/code/data freeze mismatch')
    if set(frozen['engines'])!={'paddle_vl','glm','monkey','mineru_table'}:raise RuntimeError('Incomplete structured-model calibration')
    return frozen


def forecast(frozen,row):
    from calibration_round2 import predict
    x=row.get(frozen['selected_feature'])
    missing=x is None
    estimate=predict(frozen['isotonic'],x) if not missing and frozen['isotonic'] else frozen['baseline']
    return dict(expected_f1=estimate,baseline=frozen['baseline'],selected_feature=frozen['selected_feature'],
                missing_selected_confidence=missing,review=missing or frozen['review_cutoff'] is None or x<=frozen['review_cutoff'],
                estimate_semantics='Expected associated-financial-fact F1; not probability the table is correct')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--run-dir',type=Path,default=HERE/'runs/cpu_v1');args=p.parse_args()
    if not args.execute:p.error('Calibration requires explicit --execute')
    run=args.run_dir.resolve();target=run/'calibrators-frozen.json'
    if target.exists():raise RuntimeError('Calibration already frozen; create a new run version')
    if (run/'test').exists():raise RuntimeError('Test inference already started; choose a new independent test/version')
    environment()
    from sam_bridge import check_frozen_code
    check_frozen_code()
    from calibration_round2 import choose_feature,fit_isotonic
    payload=read(run/'development/pairs.json')
    expected=dict(tables_sha256=sha(DATA/'tables.json'),references_sha256=sha(DATA/'references.json'),
                  config_sha256=sha(HERE/'config.json'),sam_code_lock_sha256=sha(HERE/'sam-code-lock.json'),
                  adapter_sha256=sha(HERE/'sam_bridge.py'),evaluator_sha256=sha(HERE/'evaluate.py'),implementation=implementation_hashes())
    if payload['provenance']!=expected:raise RuntimeError('Development scoring provenance changed; rescore a compatible new experiment')
    tables=[t for t in read(DATA/'tables.json')['tables'] if t['split']=='development']
    pairs=payload['pairs'];frozen={}
    for engine in ('paddle_vl','glm','monkey','mineru_table'):
        planned=[r for r in pairs if r['engine']==engine]
        if len(planned)!=len(tables) or any(r['inference_status']=='missing' for r in planned):raise RuntimeError('Finish all development inference before calibration: '+engine)
        rows=[r for r in planned if r['fact_f1'] is not None]
        if len({r['issuer'] for r in rows})<3:raise RuntimeError('Need at least three development issuers')
        feature,losses=choose_feature(rows,'fact_f1')
        available=[r for r in rows if r.get(feature) is not None]
        model=fit_isotonic([r[feature] for r in available],[r['fact_f1'] for r in available]) if available else []
        xs=sorted(r[feature] for r in available)
        frozen[engine]=dict(selected_feature=feature,issuer_held_out_selection_mse=losses,isotonic=model,
             baseline=statistics.mean(r['fact_f1'] for r in rows),review_cutoff=xs[max(0,math.ceil(.2*len(xs))-1)] if xs else None,
             development_rows=len(rows),training_issuers=sorted({r['issuer'] for r in rows}),
             measurement_flagged_rows=sum(bool(r['measurement_flags']) for r in rows),
             failed_inference_rows=sum(r['inference_status']!='success' for r in rows))
    write(target,dict(frozen_utc=datetime.now(timezone.utc).isoformat(),engines=frozen,
          provenance=dict(config_sha256=sha(HERE/'config.json'),tables_sha256=sha(DATA/'tables.json'),
            references_sha256=sha(DATA/'references.json'),
            development_pairs_sha256=sha(run/'development/pairs.json'),sam_code_lock_sha256=sha(HERE/'sam-code-lock.json'),
            adapter_sha256=sha(HERE/'sam_bridge.py'),evaluator_sha256=sha(HERE/'evaluate.py'),calibration_code_sha256=sha(HERE/'calibrate.py'),implementation=implementation_hashes()),
          test_inference_started=False,semantics='Expected F1, not calibrated probability of correctness'))
    print('Frozen development-only maps:',target)


if __name__=='__main__':main()
