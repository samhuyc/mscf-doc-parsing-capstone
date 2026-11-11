"""Compare native confidence with independent reference text; inference never reads labels."""
import argparse
from collections import defaultdict
import itertools
import json
import math
from pathlib import Path
import re
import unicodedata

from rapidfuzz.distance import Levenshtein

from core import ROOT, PILOT, read, sha, sources, summarize, write


def norm(s):
    s=unicodedata.normalize('NFKC',s).casefold().replace('’',"'").replace('−','-')
    # Model text can serialize a printed currency sign as \$; retain the sign.
    s=re.sub(r'\\([$%&_#{}])',r'\1',s)
    return re.sub(r'\s+',' ',s).strip()


def ranks(values):
    ordered=sorted(range(len(values)),key=lambda i:values[i])
    result=[0.0]*len(values)
    pos=0
    while pos<len(values):
        end=pos+1
        while end<len(values) and values[ordered[end]]==values[ordered[pos]]:
            end+=1
        for i in ordered[pos:end]:
            result[i]=(pos+end-1)/2+1
        pos=end
    return result


def pearson(x,y):
    if len(x)!=len(y):
        raise ValueError('Unaligned vectors')
    if len(x)<3:
        return None
    a,b=sum(x)/len(x),sum(y)/len(y)
    denom=math.sqrt(sum((v-a)**2 for v in x)*sum((v-b)**2 for v in y))
    return sum((v-a)*(w-b) for v,w in zip(x,y))/denom if denom else None


def association(x,y):
    if len(x)!=len(y):raise ValueError('Unaligned vectors')
    pairs=[(a,b) for a,b in zip(x,y) if a is not None and b is not None]
    a,b=[p[0] for p in pairs],[p[1] for p in pairs]
    rho=pearson(ranks(a),ranks(b))
    # Exact permutation test is inexpensive for the six document-level observations.
    p=None
    if rho is not None and len(pairs)<=8:
        permutations=list(itertools.permutations(ranks(b)))
        p=sum(abs(pearson(ranks(a),v)) >= abs(rho)-1e-12 for v in permutations)/len(permutations)
    return {'n':len(pairs),'spearman':rho,'pearson':pearson(a,b),'exact_permutation_p_two_sided':p}


def word_reliability(reference, units):
    """Exploratory exact-word correctness within a reference-selected window.

    Only word-score engines qualify; line/token scores cannot be relabeled as word scores.
    """
    if not units or any(u.get('unit_kind')!='word' for u in units):return None
    expected=norm(reference).split()
    actual=[norm(u['text']) for u in units]
    correct=[False]*len(actual)
    deleted=0
    for op in Levenshtein.opcodes(expected,actual):
        if op.tag=='equal':
            for i in range(op.dest_start,op.dest_end):correct[i]=True
        if op.tag=='delete':deleted+=op.src_end-op.src_start
    return {'words':[{'text':u['text'],'confidence':u['score'],'correct':c} for u,c in zip(units,correct)],
            'deleted_reference_words':deleted}


def reliability_summary(words):
    if not words:return None
    bins=[]
    for i in range(10):
        selected=[w for w in words if min(9,int(w['confidence']*10))==i]
        if not selected:continue
        bins.append({'lower':i/10,'upper':(i+1)/10,'n':len(selected),
                     'mean_confidence':sum(w['confidence'] for w in selected)/len(selected),
                     'observed_word_accuracy':sum(w['correct'] for w in selected)/len(selected)})
    return {'n':len(words),'bins':bins,
            'brier':sum((w['confidence']-w['correct'])**2 for w in words)/len(words),
            'ece_10_equal_width_bins':sum(b['n']*abs(b['mean_confidence']-b['observed_word_accuracy']) for b in bins)/len(words),
            'scope':'Native word scores treated as probability proxies; draft best-window alignment, not independently validated calibration'}


def best_edit_window(target, prediction):
    """Semi-global Levenshtein alignment: free output prefix/suffix, full reference.

    Unlike fuzzy partial-ratio alignment, this optimizes the edit metric we report
    and does not add neighboring characters just to fill a fixed-size window.
    """
    previous=[0]*(len(prediction)+1)
    starts=list(range(len(prediction)+1))
    for i,char in enumerate(target,1):
        current=[i]+[0]*len(prediction)
        current_starts=[0]*(len(prediction)+1)
        for j,other in enumerate(prediction,1):
            diagonal=previous[j-1]+(char!=other)
            deletion=previous[j]+1
            insertion=current[j-1]+1
            if diagonal<=deletion and diagonal<=insertion:
                current[j]=diagonal;current_starts[j]=starts[j-1]
            elif deletion<=insertion:
                current[j]=deletion;current_starts[j]=starts[j]
            else:
                current[j]=insertion;current_starts[j]=current_starts[j-1]
        previous,starts=current,current_starts
    end=min(range(len(prediction)+1),key=lambda j:(previous[j],abs(j-starts[j]-len(target)),starts[j]))
    return starts[end],end


def score_span(reference,units):
    """Find reference-aligned output window for evaluation ONLY, never inference.

    Position-less draft labels only support a best-window transcription diagnostic.
    A matching copy elsewhere on the same page can pass. Preserve this limitation.
    """
    strings=[]
    owners=[]
    for i,u in enumerate(units):
        s=norm(u['text'])
        if not s:
            continue
        if strings:
            strings.append(' ')
            owners.append(None)
        strings.append(s)
        owners.extend([i]*len(s))
    prediction=''.join(strings)
    target=norm(reference)
    if not target:
        raise ValueError('Empty reference')
    if prediction:
        start,end=best_edit_window(target,prediction)
        actual=prediction[start:end]
        selected=sorted({i for i in owners[start:end] if i is not None})
    else:
        actual=''
        selected=[]
    errors=Levenshtein.distance(target,actual)
    return {'reference':reference,'matched_output':actual,'reference_characters':len(target),
            'edit_errors':errors,'character_accuracy':max(0,1-errors/len(target)),
            'exact':int(actual==target),'matched_unit_indices':selected,
            'matched_native_confidence':summarize([units[i] for i in selected])}


def evaluate(run_roots,output,include_drafts=False,labels_path=None):
    labels_path=Path(labels_path) if labels_path else PILOT/'labels.jsonl'
    all_labels=[json.loads(s) for s in labels_path.read_text().splitlines() if s.strip()]
    labels=[l for l in all_labels if l['kind'] in ('text','footnote') and
            (l['review_status'] in ('human_verified','adjudicated') or include_drafts and l['review_status']=='draft')]
    manifest={s['id']:s for s in sources()}
    if len({l['id'] for l in labels})!=len(labels):raise ValueError('Duplicate reference IDs')
    for label in labels:
        source=manifest[label['document']]
        if not 1<=label['page']<=source['pages'] or label['source_sha256']!=source['sha256']:
            raise ValueError('Invalid reference source/page identity')
    rows=[]
    document_rows=[]
    correlations={}
    seen_engines=set()
    for run in run_roots:
        summaries=read(run/'documents.json')
        engine=summaries[0]['engine'] if summaries else run.name
        if engine in seen_engines:raise ValueError('Consolidate outputs before passing multiple runs of one engine')
        seen_engines.add(engine)
        if any(d['engine']!=engine for d in summaries):raise ValueError('Mixed engines in one run')
        if len({d['document'] for d in summaries})!=len(summaries):raise ValueError('Duplicate documents in run')
        for document in summaries:
            doc=document['document']
            selected=[l for l in labels if l['document']==doc]
            checks=[]
            for label in selected:
                if manifest[doc]['sha256']!=label['source_sha256']:
                    raise ValueError('Reference source identity mismatch')
                path=run/doc/f'page_{label["page"]:03}.json'
                page=read(path) if path.exists() else {'status':'missing','units':[]}
                if path.exists() and page['source_sha256']!=label['source_sha256']:
                    raise ValueError('Prediction source identity mismatch')
                check={'id':label['id'],'document':doc,'page':label['page'],'engine':engine,
                       'prediction_status':page['status'],'review_status':label['review_status'],
                       **score_span(label['text'],page['units'] if page['status']=='success' else [])}
                check['word_reliability']=word_reliability(label['text'],
                    [page['units'][i] for i in check['matched_unit_indices']])
                checks.append(check)
                rows.append(check)
            n_chars=sum(c['reference_characters'] for c in checks)
            document_rows.append({**document,'reference_spans':len(checks),
                'reference_characters':n_chars,'evaluated_pages':sorted({c['page'] for c in checks}),
                'selected_span_character_accuracy':max(0,1-sum(c['edit_errors'] for c in checks)/n_chars) if n_chars else None,
                'selected_span_exact_accuracy':sum(c['exact'] for c in checks)/len(checks) if checks else None,
                'reference_sha256':sha(labels_path)})
        engine_docs=[d for d in document_rows if d['engine']==engine]
        accuracy=[d['selected_span_character_accuracy'] for d in engine_docs]
        correlations[engine]={}
        for name in ('character_weighted_mean','mean','geometric_mean','p10','fraction_below_0_90'):
            values=[d['confidence'][name] for d in engine_docs]
            correlations[engine][name]=association(values,accuracy)
        engine_spans=[r for r in rows if r['engine']==engine]
        correlations[engine]['matched_span_weighted_mean']=association(
            [r['matched_native_confidence']['character_weighted_mean'] for r in engine_spans],
            [r['character_accuracy'] for r in engine_spans])
    report={'label_status':'draft_exploratory' if include_drafts else 'reviewed_only',
            'target':'Selected text/footnote transcription, not whole-document or table correctness',
            'alignment':'Full reference to minimum-edit output substring (semi-global Levenshtein)',
            'normalization':'NFKC, casefold, whitespace collapse, typographic quote/minus, escaped punctuation unescape',
            'primary_confidence':'character_weighted_mean',
            'primary_scope':'All available returned units; page coverage is reported separately',
            'reference_spans':len(labels),'documents':document_rows,'correlations':correlations,'checks':rows,
            'word_reliability':{engine:reliability_summary([w for r in rows if r['engine']==engine and r['word_reliability']
                for w in r['word_reliability']['words']]) for engine in correlations},
            'limitations':['Six documents, five issuers: the two Rolls-Royce documents are related.',
                'Labels are selected spans with no exact boxes; best-window matching can credit repeated text.',
                'Reference labels are assistant-authored drafts unless independently reviewed.',
                'Native scores and their averages are not calibrated document correctness probabilities.',
                'Missing text can coexist with high confidence on returned text.',
                'Repetitive generated text can have high token confidence and dominate an output-length-weighted average; token-limit flags must be read separately.',
                'Permutation p-values assume exchangeable documents, weakened by shared issuer; exploratory only.',
                'Several aggregations are reported without selecting a winner; correlations are not proof of generalization.']}
    output.mkdir(parents=True,exist_ok=True)
    write(output/'evaluation.json',report)
    def fmt(x):return 'N/A' if x is None else f'{x:.4f}'
    lines=['# Native confidence versus transcription correctness','',
           'Raw model confidence only. No cross-model agreement and no fitted calibration.',
           f'Labels: **{report["label_status"]}**; {len(labels)} available reference spans per engine.','',
           '| Engine | Document | Pages processed | Token-limit pages | Native weighted mean | Native p10 | Selected-span character accuracy |',
           '|---|---|---:|---:|---:|---:|---:|']
    for d in document_rows:
        lines.append(f'| {d["engine"]} | {d["document"]} | {d["successful_pages"]}/{d["expected_pages"]} | {len(d.get("truncated_pages",[]))} | {fmt(d["confidence"]["character_weighted_mean"])} | {fmt(d["confidence"]["p10"])} | {fmt(d["selected_span_character_accuracy"])} |')
    truncated=[d for d in document_rows if d.get('truncated_pages')]
    if truncated:
        lines+=['','**Generation limits:** processed-page coverage includes pages that hit the token limit. Their emitted-token scores remain visible, but they are not complete generations. Repetition can have very high native confidence.']
        for d in truncated:lines.append(f'- {d["engine"]}, {d["document"]}: token-limit pages {d["truncated_pages"]}.')
    lines+=['','| Engine | Summary | Spearman rank correlation | Pearson correlation | n documents |',
            '|---|---|---:|---:|---:|']
    for engine,stats in correlations.items():
        for name,value in stats.items():
            if name=='matched_span_weighted_mean':continue
            lines.append(f'| {engine} | {name} | {fmt(value["spearman"])} | {fmt(value["pearson"])} | {value["n"]} |')
    lines+=['','Higher is better for all summaries except fraction_below_0_90 (where a negative correlation is desirable).',
            'Constant correctness or confidence produces N/A, not zero correlation. Different engines have different native score scales.','']
    for engine,stats in report['word_reliability'].items():
        if stats:
            lines += [f'## {engine}: exploratory word-confidence reliability','',
                      f'{stats["n"]} aligned output words; Brier {fmt(stats["brier"])}; 10-bin ECE {fmt(stats["ece_10_equal_width_bins"])}.',
                      'These use normalized native scores as probability proxies and draft, best-window word alignment. They do not establish calibrated probabilities.',
                      '', '| Native score bin | Words | Mean confidence | Observed exact-word accuracy |', '|---|---:|---:|---:|']
            for b in stats['bins']:
                lines.append(f'| {b["lower"]:.1f}–{b["upper"]:.1f} | {b["n"]} | {fmt(b["mean_confidence"])} | {fmt(b["observed_word_accuracy"])} |')
    lines+=['',
            *['- '+s for s in report['limitations']],'']
    (output/'REPORT.md').write_text('\n'.join(lines))
    print('\n'.join(lines[:18]))


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('runs',nargs='+',type=Path)
    cli.add_argument('--output',type=Path,default=ROOT/'results')
    cli.add_argument('--include-drafts',action='store_true')
    cli.add_argument('--labels',type=Path,default=PILOT/'labels.jsonl')
    args=cli.parse_args()
    evaluate(args.runs,args.output,args.include_drafts,args.labels)
