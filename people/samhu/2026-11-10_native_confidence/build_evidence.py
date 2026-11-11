"""Create inspectable evidence for the sponsor brief from saved inference only."""
import json
from pathlib import Path
import statistics

from core import ROOT, PILOT, read, write, sources


def build():
    out=ROOT/'results/v2'
    labels=[json.loads(x) for x in (PILOT/'labels.jsonl').read_text().splitlines()]
    labels=[l for l in labels if l['kind'] in ('text','footnote')]
    checks=read(out/'evaluation.json')['checks']
    refs=[]
    for label in labels:
        refs.append({**label, 'results':[c for c in checks if c['id']==label['id']]})
    write(out/'snippet_examples.json',refs)
    evidence={'paddle':[], 'mineru':[]}
    # Fixed examples chosen for explaining mechanics, not estimating accuracy.
    for doc,number,phrase in [('cvs_2025q2',1,'Second Quarter'),('cvs_2025q2',6,'Returned'),
                              ('rolls_royce_2026h1_release',25,'Underlying operating')]:
        p=read(ROOT/'runs/paddle_v2'/doc/f'page_{number:03}.json')
        matches=[u for u in p['units'] if phrase.casefold() in u['text'].casefold()]
        evidence['paddle'].append({'document':doc, 'page':number, 'lines':matches[:3],
                                    'page_confidence':p['confidence']})
    for doc,number in [('cvs_2025q2',1),('cvs_2025q2',6),('rolls_royce_2026h1_release',25)]:
        p=read(ROOT/'runs/mineru_v2'/doc/f'page_{number:03}.json')
        units=p['confidence_units']
        minimum=min(range(len(units)), key=lambda i:units[i]['score'])
        indices=sorted(set(list(range(min(12,len(units))))+list(range(max(0,minimum-3),min(len(units),minimum+4)))))
        phrase='Underlying operating profit/(loss)'
        excerpt_start=p['text'].find(phrase) if doc=='rolls_royce_2026h1_release' else 0
        excerpt_start=max(0,excerpt_start)
        evidence['mineru'].append({'document':doc, 'page':number,
            'tokens':[dict(units[i],position=i) for i in indices],
            'output_excerpt':p['text'][:750], 'page_confidence':p['confidence'],
            'failure_excerpt':p['text'][excerpt_start:excerpt_start+750],
            'truncated':p['truncated'],
            'repeated_phrase_count':p['text'].count('Underlying operating profit/(loss)')})
    write(out/'decoder_examples.json',evidence)
    audits={}
    for engine in ('paddle','mineru'):
        counts={'pages':0, 'changed_text_pages':0, 'units':0, 'exact_one':0}
        values=[];differences=[];raw_ones=0;v1_ones=0;max_sum_error=0
        for source in sources():
            for n in range(1,source['pages']+1):
                path=ROOT/f'runs/{engine}_v2'/source['id']/f'page_{n:03}.json'
                if not path.exists():continue
                p=read(path)
                old=read(ROOT/f'runs/{engine}'/source['id']/f'page_{n:03}.json')
                if p['status']!='success':raise ValueError(f'Incomplete v2 run: {engine} {source["id"]} {n}')
                counts['pages']+=1;counts['changed_text_pages']+=p['text']!=old['text']
                units=p['confidence_units'];values.extend(u['score'] for u in units)
                if engine=='mineru':
                    for u in units:
                        differences.append(abs(u['score']-u['v1_posthoc_probability']))
                        raw_ones+=u['backend_log_probability']==0
                        v1_ones+=u['v1_posthoc_probability']==1
                else:
                    max_sum_error=max([max_sum_error]+[u['distribution_sum_max_error'] for u in p['units']])
        counts.update(units=len(values),exact_one=sum(v==1 for v in values),
                      mean=statistics.mean(values),median=statistics.median(values),minimum=min(values),
                      below_90=sum(v<.9 for v in values))
        if engine=='mineru':counts.update(backend_exact_one=raw_ones,v1_exact_one=v1_ones,
            mean_absolute_probability_change=statistics.mean(differences),
            max_absolute_probability_change=max(differences),
            comparison='v1 and v2 normalization on the same newly captured original logits')
        else:counts['max_distribution_sum_error']=max_sum_error
        audits[engine]=counts
    fp_path=ROOT/'runs/mineru_fp32_check/cvs_2025q2/page_001.json'
    if fp_path.exists():
        fp=read(fp_path)
        bf=read(ROOT/'runs/mineru_v2/cvs_2025q2/page_001.json')
        if fp['status']=='success':
            audits['float32_forward_check']={
                'document':'cvs_2025q2','page':1,
                'same_text':fp['text']==bf['text'],
                'same_token_ids':[u['token_id'] for u in fp['confidence_units']]==[u['token_id'] for u in bf['confidence_units']],
                'native_mean':bf['confidence']['mean'],'float32_mean':fp['confidence']['mean'],
                'float32_logit_dtypes':sorted({u['logit_dtype'] for u in fp['confidence_units']}),
                'scope':'One-page diagnostic. Checkpoint weights cast from BF16 to FP32; original training precision cannot be recovered.'}
        else:audits['float32_forward_check']={'status':'failed','error':fp.get('error')}
    write(out/'precision_audit.json',audits)
    return refs,evidence,audits


if __name__=='__main__':build()
