"""Small monotone calibration with nested issuer-separated validation."""
from collections import defaultdict
import math
import random
import statistics
from evaluate_table_accuracy import spearman,error_auc

FEATURES=('native_numeric','native_all','native_numeric_p10','native_number_p10','native_structure','native_structure_p10','native_visible','native_visible_p10')

def fit_isotonic(xs,ys):
    if len(xs)!=len(ys) or not xs:raise ValueError('Nonempty aligned training data required')
    grouped=defaultdict(list)
    for x,y in zip(xs,ys):
        if not math.isfinite(x) or not 0<=y<=1:raise ValueError('Invalid calibration input')
        grouped[x].append(y)
    blocks=[]
    for x,values in sorted(grouped.items()):
        blocks.append([x,x,len(values),sum(values)])
        while len(blocks)>=2 and blocks[-2][3]/blocks[-2][2]>blocks[-1][3]/blocks[-1][2]:
            b=blocks.pop();a=blocks.pop();blocks.append([a[0],b[1],a[2]+b[2],a[3]+b[3]])
    return [dict(low=a,high=b,n=n,prediction=s/n) for a,b,n,s in blocks]

def predict(model,x):
    for i,block in enumerate(model):
        if x<=block['high']:return block['prediction']
        if i+1<len(model) and x<model[i+1]['low']:
            # Piecewise-linear interpolation between fitted block endpoints.
            nxt=model[i+1];fraction=(x-block['high'])/(nxt['low']-block['high'])
            return block['prediction']*(1-fraction)+nxt['prediction']*fraction
    return model[-1]['prediction']

def fit_predict(train,test,feature,target):
    rows=[r for r in train if r.get(feature) is not None]
    if not rows:return [None for _ in test]
    model=fit_isotonic([r[feature] for r in rows],[r[target] for r in rows])
    return [predict(model,r[feature]) if r.get(feature) is not None else None for r in test]

def choose_feature(train,target):
    groups=sorted({r['issuer'] for r in train});losses={}
    for feature in FEATURES:
        if any(r.get(feature) is None for r in train):continue
        errors=[]
        for issuer in groups:
            fitting=[r for r in train if r['issuer']!=issuer];testing=[r for r in train if r['issuer']==issuer]
            if not fitting:continue
            pred=fit_predict(fitting,testing,feature,target)
            errors.extend((p-r[target])**2 for p,r in zip(pred,testing))
        if errors:losses[feature]=statistics.mean(errors)
    return min(losses,key=losses.get) if losses else 'native_numeric',losses

def outer_predictions(rows,target='fact_f1',select=False,feature='native_numeric'):
    results=[]
    groups=sorted({r['issuer'] for r in rows})
    for heldout in groups:
        train=[r for r in rows if r['issuer']!=heldout]
        test=[r for r in rows if r['issuer']==heldout]
        if not train or not test:continue
        chosen,inner=choose_feature(train,target) if select else (feature,{})
        estimates=fit_predict(train,test,chosen,target);baseline=statistics.mean(r[target] for r in train)
        confidences=sorted(r[chosen] for r in train if r.get(chosen) is not None)
        cutoff=confidences[max(0,math.ceil(.2*len(confidences))-1)] if confidences else None
        for row,p in zip(test,estimates):
            results.append(dict(table_id=row['table_id'],issuer=heldout,truth=row[target],prediction=p if p is not None else baseline,baseline=baseline,missing_selected_confidence=p is None,
                                selected_feature=chosen,native=row.get(chosen),review=row.get(chosen) is None or cutoff is None or row[chosen]<=cutoff,
                                training_rows=len(train),training_issuers=sorted({r['issuer'] for r in train}),inner_mse=inner))
    return results

def cluster_interval(rows,statistic,iterations=1000):
    groups=defaultdict(list)
    for r in rows:groups[r['issuer']].append(r)
    if len(groups)<3:return None
    rng=random.Random(20261116);values=[]
    for _ in range(iterations):
        sample=[r for k in rng.choices(list(groups),k=len(groups)) for r in groups[k]]
        value=statistic(sample)
        if value is not None and math.isfinite(value):values.append(value)
    if len(values)<100:return None
    values.sort();return [values[int(.025*(len(values)-1))],values[int(.975*(len(values)-1))]]

def metrics(predictions):
    valid=[r for r in predictions if r['prediction'] is not None]
    if not valid:return dict(n=0,status='No out-of-issuer predictions')
    mse=lambda rs:statistics.mean((r['prediction']-r['truth'])**2 for r in rs)
    gain=lambda rs:statistics.mean((r['baseline']-r['truth'])**2-(r['prediction']-r['truth'])**2 for r in rs)
    kept=[r for r in valid if not r['review']]
    return dict(n=len(valid),issuers=len({r['issuer'] for r in valid}),mse=mse(valid),
                baseline_mse=statistics.mean((r['baseline']-r['truth'])**2 for r in valid),mse_gain=gain(valid),
                mse_gain_issuer_bootstrap_95=cluster_interval(valid,gain),
                mae=statistics.mean(abs(r['prediction']-r['truth']) for r in valid),
                baseline_mae=statistics.mean(abs(r['baseline']-r['truth']) for r in valid),
                selection_counts=dict(__import__('collections').Counter(r['selected_feature'] for r in valid)),
                training_threshold_triage=dict(kept=len(kept),coverage=len(kept)/len(valid),
                  kept_mean_accuracy=statistics.mean(r['truth'] for r in kept) if kept else None,
                  all_mean_accuracy=statistics.mean(r['truth'] for r in valid)))
