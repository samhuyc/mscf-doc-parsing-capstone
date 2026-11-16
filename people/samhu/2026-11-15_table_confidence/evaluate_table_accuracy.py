"""Track source-checked numeric transcription versus native table confidence.

No calibration is fitted. References are never used by inference or to repair
outputs. Correlations remain within engine and issuer-cluster uncertainty is
reported. This is not a benchmark of table structure or financial usability.
"""
import argparse
from collections import defaultdict
import csv
from datetime import datetime,timezone
from html import escape
import math
from pathlib import Path
import random
import statistics

from regions import table_summary
from core import read,write,sha,digest
from numeric_accuracy import numbers,numeric_score
from output_statistics import LABELS

ROOT=Path(__file__).resolve().parent


def ranks(values):
    ordered=sorted(range(len(values)),key=values.__getitem__)
    result=[0.]*len(values);start=0
    while start<len(values):
        end=start+1
        while end<len(values) and values[ordered[end]]==values[ordered[start]]:end+=1
        for i in ordered[start:end]:result[i]=(start+end-1)/2
        start=end
    return result


def spearman(x,y):
    if len(x)<3:return None
    a,b=ranks(x),ranks(y)
    ma,mb=statistics.mean(a),statistics.mean(b)
    denom=math.sqrt(sum((v-ma)**2 for v in a)*sum((v-mb)**2 for v in b))
    return sum((v-ma)*(w-mb) for v,w in zip(a,b))/denom if denom else None


def error_auc(confidences,exact):
    errors=[c for c,e in zip(confidences,exact) if not e]
    correct=[c for c,e in zip(confidences,exact) if e]
    if not errors or not correct:return None
    return sum((a<b)+.5*(a==b) for a in errors for b in correct)/(len(errors)*len(correct))


def summarize(pairs,feature='confidence',bootstrap=2000):
    rows=[r for r in pairs if r.get(feature) is not None and r['primary_eligible']]
    if not rows:return dict(n=0,status='No eligible completed outputs yet')
    c=[r[feature] for r in rows]; y=[r['numeric']['f1'] for r in rows]
    exact=[r['numeric']['exact'] for r in rows]
    groups=defaultdict(list)
    for r in rows:groups[r['issuer']].append(r)
    rng=random.Random(20261115); boots=[]
    for _ in range(bootstrap):
        sample=[r for key in rng.choices(list(groups),k=len(groups)) for r in groups[key]]
        v=spearman([r[feature] for r in sample],[r['numeric']['f1'] for r in sample])
        if v is not None:boots.append(v)
    boots.sort()
    ci=[boots[int(.025*(len(boots)-1))],boots[int(.975*(len(boots)-1))]] if len(boots)>=100 else None
    cutoff=sorted(c)[max(0,math.ceil(.2*len(c))-1)]
    retained=[r for r in rows if r[feature]>cutoff]
    all_risk=statistics.mean(1-v for v in y)
    retained_risk=statistics.mean(1-r['numeric']['f1'] for r in retained) if retained else None
    thresholds=[]
    for t in (.9,.95,.99):
        accepted=[r for r in rows if r[feature]>=t]
        thresholds.append(dict(threshold=t,accepted=len(accepted),numeric_mismatches=sum(not r['numeric']['exact'] for r in accepted)))
    return dict(n=len(rows),issuer_clusters=len(groups),status='Exploratory source-checked subset',
                mean_numeric_f1=statistics.mean(y),exact_numeric_tables=sum(exact),
                mean_financial_value_recall=statistics.mean(r['financial_values']['recall'] for r in rows),
                financial_value_omission_tables=sum(r['financial_values']['recall']<1 for r in rows),
                spearman=spearman(c,y),spearman_cluster_bootstrap_95=ci,valid_bootstrap_samples=len(boots),
                error_detection_auroc=error_auc(c,exact),
                auc_note='Low confidence predicts numeric mismatch; undefined if only one outcome class',
                baseline_mean_numeric_error=all_risk,
                rejection_20_percent=dict(threshold=cutoff,retained=len(retained),coverage=len(retained)/len(rows),
                    retained_mean_numeric_error=retained_risk,
                    error_reduction=all_risk-retained_risk if retained_risk is not None else None,
                    policy='Reject confidence at or below bottom-20% cutoff; retain ties together'),
                fixed_thresholds=thresholds)


def matched_cohort(pairs, expected_ids):
    """Require identical crop identities and scored successful outputs per engine."""
    expected=set(expected_ids)
    details={}
    for engine in LABELS:
        rows=[r for r in pairs if r['engine']==engine and r['primary_eligible']]
        observed=[r['table_id'] for r in rows]
        details[engine]=dict(missing=sorted(expected-set(observed)),
            unexpected=sorted(set(observed)-expected), duplicates=len(observed)-len(set(observed)),
            missing_confidence=sum(r['confidence'] is None for r in rows))
    return dict(complete=all(not any(v.values()) for v in details.values()),
                expected_crops=len(expected), table_ids=sorted(expected), engines=details)


def evaluate(root, require_complete=False):
    root=Path(root)
    data=read(root/'tables.json'); references=read(ROOT/'accuracy_references.json')
    selected={r['table_id']:r for r in references['references']}
    pairs=[]; pending=defaultdict(int); failed=[]
    bundle_hash=sha(root/'tables.json')
    for t in data['tables']:
        if t['table_id'] not in selected:continue
        ref=selected[t['table_id']]
        assert ref['review_status']=='assistant_visually_checked'
        assert ref['image_sha256']==t['image_sha256']==sha(root/t['image'])
        assert ref['source_sha256']==t['source_sha256']
        assert ref['numbers']==numbers(ref['reference_text'])
        for engine in LABELS:
            if engine in t['models']:
                result=t['models'][engine]['crop']; provenance=t['settings_sha256']
            else:
                folder=root/'mineru' if engine=='mineru' else root/'extra'/engine
                path=folder/(t['table_id']+'.json')
                if not path.exists():pending[engine]+=1;continue
                result=read(path);settings=read(folder/'settings.json')
                assert settings['source_bundle_sha256']==bundle_hash
                assert result['image_sha256']==t['image_sha256']
                assert result['settings_sha256']==digest(settings)
                provenance=result['settings_sha256']
            if result['status']!='success':
                failed.append(dict(engine=engine,table_id=t['table_id'],status=result['status']));continue
            assert table_summary(result['confidence_units'])==result['confidence']
            observed=numbers(result['text']); quality=numeric_score(ref['numbers'],observed)
            value_quality=numeric_score(ref['financial_values'],observed)
            pairs.append(dict(engine=engine,table_id=t['table_id'],document=t['document'],
                issuer='rolls_royce' if t['document'].startswith('rolls_royce') else t['document'],
                page=t['page'],image=t['image'],image_sha256=t['image_sha256'],settings_sha256=provenance,
                primary_eligible=ref['primary_eligible'],reference_number_count=len(ref['numbers']),
                confidence=result['confidence']['geometric_mean'],
                confidence_p10=result['confidence']['p10'],
                confidence_mean=result['confidence']['mean'],
                content_confidence=result.get('content_only',{}).get('confidence',{}).get('geometric_mean'),
                numeric=quality,financial_values=dict(recall=value_quality['recall'],
                    expected=value_quality['reference_numbers'],missing=value_quality['missing']),
                predicted_numbers=observed,truncated=result.get('truncated',False)))
    models={}
    for engine in LABELS:
        rows=[r for r in pairs if r['engine']==engine]
        models[engine]=dict(primary=summarize(rows),completed_reference_crops=len(rows),
            pending_reference_crops=pending[engine],
            secondary={feature:summarize(rows,feature,bootstrap=0) for feature in
                       ('confidence_p10','confidence_mean','content_confidence')})
    cohort=matched_cohort(pairs,[r['table_id'] for r in selected.values() if r['primary_eligible']])
    if require_complete and not cohort['complete']:
        raise ValueError(f'Incomplete matched cohort: {cohort}')
    report=dict(snapshot_utc=datetime.now(timezone.utc).isoformat(),matched_cohort=cohort,
        source_bundle_sha256=bundle_hash,reference_sha256=sha(ROOT/'accuracy_references.json'),
        metric_code_sha256=sha(ROOT/'numeric_accuracy.py'),evaluation_code_sha256=sha(Path(__file__)),
        selected_crops=len(selected),primary_eligible_crops=sum(r['primary_eligible'] for r in selected.values()),
        reference_numeric_tokens=sum(len(r['numbers']) for r in selected.values()),
        human_verified=False,models=models,pairs=pairs,failed=failed,
        limitations=[
            'Exploratory selected subset, not random or held-out; 19 eligible crops from six PDFs/five issuers.',
            'Assistant visually checked source references; independent human review remains outstanding.',
            'Numeric multiset F1 counts value occurrences, signs and percent/point suffixes; it cannot detect swapped cells, wrong row/column association, currency/scale loss, or tables omitted by layout.',
            'Headers, years and note numbers are included; nonnumeric text and dash/blank-cell accuracy are not scored.',
            'Secondary financial-value recall excludes annotated header/date/note numbers. It does not penalize extra numbers and cannot verify association; do not treat it as full accuracy.',
            'RR release page 17 is scored descriptively but excluded from primary associations because of clipped top-edge text.',
            'Raw scores differ across engines. No calibration is fitted; confidence is not a table correctness probability.',
            'Issuer-cluster bootstrap has only five independent clusters; intervals are descriptive and unstable.',
            'Pending runs are not treated as errors or substituted with pilot outputs.'])
    dest=root/'accuracy';dest.mkdir(exist_ok=True)
    write(dest/'tracking.json',report)
    fields=['engine','table_id','issuer','primary_eligible','confidence','confidence_p10','confidence_mean',
            'content_confidence','f1','precision','recall','exact','reference_numbers','predicted_numbers','matched_numbers']
    with (dest/'pairs.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for r in pairs:
            writer.writerow({k:r[k] if k in r and k!='predicted_numbers' else r['numeric'][k] for k in fields})
    render(dest,report)
    return report


def render(dest,data):
    def fmt(v):return 'No outcome variation' if v is None else f'{v:.3f}'
    cohort_note=('Matched comparison verified: every model has the same 19 crop IDs and native scores.'
                 if data['matched_cohort']['complete'] else 'Incomplete comparison: model cohorts are not yet matched.')
    lines=[]
    for engine,info in data['models'].items():
        s=info['primary']
        if not s['n']:
            lines.append(f'<tr><td>{LABELS[engine]}</td><td>0/{data["primary_eligible_crops"]}</td><td colspan="6">Awaiting this model’s full-corpus run</td></tr>');continue
        ci=s['spearman_cluster_bootstrap_95']
        ci_text='' if ci is None else f'[{ci[0]:.2f}, {ci[1]:.2f}]'
        triage=s['rejection_20_percent']
        lines.append(f'<tr><td>{LABELS[engine]}</td><td>{s["n"]}/{data["primary_eligible_crops"]}</td>'
          f'<td>{s["mean_numeric_f1"]:.1%}</td><td>{s["mean_financial_value_recall"]:.1%}</td><td>{fmt(s["spearman"])} {ci_text}</td>'
          f'<td>{fmt(s["error_detection_auroc"])}</td><td>{s["exact_numeric_tables"]}/{s["n"]}</td>'
          f'<td>{fmt(triage["error_reduction"])} · retain {triage["retained"]}/{s["n"]}</td></tr>')
    examples=sorted([r for r in data['pairs'] if r['primary_eligible'] and r['confidence'] is not None and not r['numeric']['exact']],key=lambda r:-(r['confidence']*(1-r['numeric']['f1'])))[:12]
    examples_html=[]
    for r in examples:
        examples_html.append(f'<details><summary>{LABELS[r["engine"]]} · {escape(r["table_id"])} · confidence {r["confidence"]:.2%} · numeric F1 {r["numeric"]["f1"]:.2%}</summary>'
          f'<p>Missing: {escape(str(r["numeric"]["missing"]))}<br>Extra: {escape(str(r["numeric"]["extra"]))}</p>'
          f'<img loading="lazy" src="../{escape(r["image"])}" alt="Source crop"></details>')
    page=f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Does confidence predict numeric accuracy?</title>
<style>body{{font:15px/1.5 system-ui;background:#f3f5f7;color:#182c3b;margin:0}}main{{max-width:1280px;margin:auto;padding:28px}}section{{background:white;padding:24px;border-radius:10px;margin:20px 0}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}td,th{{padding:9px;text-align:left;border-bottom:1px solid #d7dfe5}}th{{font-size:12px}}.notice{{background:#fff0ce;padding:16px}}img{{max-width:100%}}summary{{cursor:pointer;padding:8px}}@media(max-width:800px){{section{{overflow:auto}}main{{padding:10px}}}}</style>
<main><h1>Does confidence predict numeric accuracy?</h1><p>Source-checked diagnostic · {data['primary_eligible_crops']} eligible table crops · six PDFs / five issuers · snapshot {data['snapshot_utc']}</p>
<p class="notice">Provisional: references were visually checked by the assistant, not a human reviewer. Numeric F1 measures number transcription within detected crops. It is not table-structure accuracy or probability of a correct financial table.</p>
<p>{cohort_note}</p>
<section><h2>Within-model relationship</h2><table><thead><tr><th>Model</th><th>Crops</th><th>Mean numeric F1</th><th>Financial-value recall (secondary)</th><th>Spearman ρ [cluster 95% interval]</th><th>Error-detection AUROC</th><th>Exact numeric inventories</th><th>Error reduction after rejecting lowest 20%</th></tr></thead><tbody>{''.join(lines)}</tbody></table>
<p>Positive ρ means higher confidence accompanies better numeric transcription. AUROC above 0.5 means lower confidence ranks numeric mismatches better than chance; a single outcome class cannot produce AUROC. Positive error reduction means confidence filtering helped on this subset. Partial runs must not be compared as matched samples.</p></section>
<section><h2>Confidence and numeric F1</h2><img src="confidence_vs_numeric_accuracy.png" alt="Within-model confidence versus numeric transcription F1"></section>
<section><h2>High-confidence numeric mismatches to review</h2>{''.join(examples_html)}</section>
<section><h2>What accuracy means here</h2><p>For each crop, M is the number of matching numeric occurrences, R the reference count, and P the predicted count. Numeric transcription F1 = 2M / (R + P). The reported mean weights each crop equally. Repeated values count separately. Missing and extra numbers reduce the score; row and column positions are ignored.</p><p>A table with the correct revenue numbers assigned to the wrong years can still score 100%. This metric is a transcription diagnostic, not financial extraction accuracy.</p></section>
<section><h2>Recommended next evaluation</h2><ol><li>Human-review the 19 reference grids, including row labels, periods, signs, currency and scale. Score complete financial facts and the fraction of tables with every critical fact correct.</li><li>Measure missed tables and clipped headers separately. Add a structure metric such as <a href="https://arxiv.org/abs/2203.12555">GriTS</a> when comparing cell-grid outputs; plain OCR text needs a separately evaluated structure stage.</li><li>Expand to harder documents from new issuers. Split by issuer, then measure remaining critical errors at fixed automatic-acceptance coverage. Use this to decide whether confidence supports review routing before training a quality predictor.</li></ol></section>
<section><h2>Method and limits</h2><ul>{''.join('<li>'+escape(s)+'</li>' for s in data['limitations'])}</ul><p>Primary confidence: geometric mean over emitted native units. Secondary mean, p10 and content-only analyses are in tracking.json; they use their own available subsets and are exploratory. No threshold was fitted to these outcomes.</p></section></main></html>'''
    (dest/'report.html').write_text(page)


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--root',type=Path,default=ROOT/'runs/sponsor_all')
    cli.add_argument('--require-complete',action='store_true')
    args=cli.parse_args()
    result=evaluate(args.root,args.require_complete)
    for e,s in result['models'].items():print(e,s['primary'])
