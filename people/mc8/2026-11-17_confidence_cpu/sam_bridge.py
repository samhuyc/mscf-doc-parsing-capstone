"""Reuse Sam's frozen scientific functions with explicit CPU token spans."""
from common import HERE, SAM, NATIVE, MODELS, sam_paths, sha, read, write
sam_paths()
import native_evidence
from header_evidence import header_features
from table_structure_v2 import parse_output, facts, fact_score
from standard_metric import content_score
from numeric_accuracy import numbers, numeric_score

_original_alignment=native_evidence.aligned_units


def cpu_alignment(record,engine):
    if record.get('backend')!='llama.cpp-cpu':return _original_alignment(record,engine)
    text=record.get('text','');units=[]
    if record.get('alignment_error'):raise ValueError(record['alignment_error'])
    for i,u in enumerate(record.get('confidence_units',[])):
        a,b=u['decoded_span']
        if not 0<=a<=b<=len(text):raise ValueError('Invalid emitted-token span')
        units.append(dict(index=i,start=a,end=b,score=u['score'],text=text[a:b]))
    return dict(status='aligned_cpu_token_bytes',text=text,units=units)


native_evidence.aligned_units=cpu_alignment


def evidence(record,engine):
    feature,alignment=native_evidence.features(record,engine)
    feature.update(header_features(record.get('text',''),engine,alignment))
    return feature,alignment


def flatten_facts(grids,alignment=None):
    # Same cross-grid repeated-row handling as Sam's evaluator.
    from collections import Counter
    result=[];counts=Counter()
    for index,grid in enumerate(grids):
        row_ids={}
        for fact in facts(grid,alignment)['facts']:
            key=(tuple(fact['section']),fact['row_label']);row_key=(fact['row'],key)
            if row_key not in row_ids:counts[key]+=1;row_ids[row_key]=counts[key]
            result.append(dict(**fact,grid_index=index))
            result[-1]['row_occurrence']=row_ids[row_key]
    return result


def code_inventory():
    paths=[SAM/'prototype'/n for n in ('native_evidence.py','header_evidence.py','table_structure_v2.py',
           'table_structure.py','standard_metric.py','calibration_round2.py','vendor/grits.py')]
    paths += [SAM/'numeric_accuracy.py',SAM/'evaluate_table_accuracy.py',SAM/'regions.py',
              SAM/'run_tables.py',NATIVE/'run_paddle.py',NATIVE/'run_tesseract.py',NATIVE/'score_probes.py']
    return {str(p.relative_to(SAM.parents[2])):sha(p) for p in paths}


def check_frozen_code():
    expected=read(HERE/'sam-code-lock.json')
    if code_inventory()!=expected:raise RuntimeError('Sam scientific source changed; version and freeze a new experiment')
