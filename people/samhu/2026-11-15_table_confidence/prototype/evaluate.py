"""Source-linked exploratory accuracy and native confidence pairs."""
from collections import Counter,defaultdict
from copy import deepcopy
from pathlib import Path
import argparse
import statistics
from common import ROOT,OLD,RUN,RESULTS,read,write,sha,digest,issuer
from extract_evidence import outputs
from native_evidence import features
from table_structure import parse_output,facts,fact_score,fact_key,ordered_grid_score,label
from numeric_accuracy import numbers,numeric_score
from standard_metric import content_score
from reference_annotations import annotated_reference
from review_panel import load_dataset,ReviewStore


def reference_sets():
    tables,_,refsha=load_dataset(OLD)
    reviews=ReviewStore(OLD/'review/financial_ground_truth.json',tables,refsha)
    assistant=read(ROOT/'assistant_table_review.json')['reviews'];refs={}
    for t in tables:
        tid=t['table_id'];a=assistant[tid]
        if a['requires_recrop']:continue
        human=reviews.records.get(tid,{})
        verified=reviews.evaluation_status(tid,human)=='human_verified'
        refs[tid]=dict(table_id=tid,grids=human['grids'] if verified else a['grids'],
                      reference_kind='human_confirmed' if verified else 'assistant_source_checked',
                      human_verified=verified,issuer=issuer(t['document']),image_sha256=t['image_sha256'],source_sha256=t['source_sha256'])
    yield 'sponsor_development',OLD,refs
    for name in ('repairs','benchmark','fresh_public','sponsor_table_mode'):
        root=RUN/name
        if (root/'references.json').exists():yield name,root,read(root/'references.json')

def flatten_facts(grids,alignment=None):
    result=[];counts=Counter()
    for index,grid in enumerate(grids):
        row_ids={}
        for fact in facts(grid,alignment)['facts']:
            key=(tuple(fact['section']),fact['row_label'])
            row_key=(fact['row'],key)
            if row_key not in row_ids:
                counts[key]+=1;row_ids[row_key]=counts[key]
            result.append(dict(**fact,grid_index=index))
            result[-1]['row_occurrence']=row_ids[row_key]
    return result

def join_grid_text(grids):return '\n'.join(' '.join(row) for g in grids for row in g['cells'])

def main():
    p=argparse.ArgumentParser();p.add_argument('--cohorts',nargs='+');a=p.parse_args()
    code_files=('evaluate.py','table_structure.py','native_evidence.py','reference_annotations.py')
    code_hashes={n:sha(ROOT/'prototype'/n) for n in code_files}
    pairs=[];details=[];pending=[];availability=[]
    for cohort,root,refs in reference_sets():
        if a.cohorts and cohort not in a.cohorts:continue
        for table in read(root/'tables.json')['tables']:
            tid=table['table_id']
            if tid not in refs:continue
            ref=annotated_reference(refs[tid])
            assert ref['image_sha256']==table['image_sha256']==sha(root/table['image'])
            assert ref['source_sha256']==table['source_sha256']
            expected=flatten_facts(ref['grids']);ref_values=[n for f in expected for n in numbers(f['raw'])]
            records=list(outputs(root,table))
            planned=('mineru_table',) if cohort=='sponsor_table_mode' else ('paddle','tesseract','paddle_vl','glm','monkey','mineru')+ (('mineru_table',) if cohort in ('benchmark','fresh_public') else ())
            present={engine:record for engine,record,_ in records}
            for engine in planned:
                availability.append(dict(cohort=cohort,table_id=tid,engine=engine,status=present.get(engine,{}).get('status','pending')))
            for engine,record,identity in records:
                feature_path=RUN/'evidence'/root.name/engine/(tid+'.json')
                evidence=read(feature_path) if feature_path.exists() else {}
                expected_provenance=dict(**identity,code_sha256=sha(ROOT/'prototype/native_evidence.py'),image_sha256=table['image_sha256'])
                native_ready=evidence.get('status')=='success' and evidence.get('provenance')==expected_provenance
                if native_ready:
                    feature=evidence['features'];alignment=dict(units=evidence['aligned_units'],text=record.get('text',''))
                else:
                    pending.append(dict(cohort=cohort,engine=engine,table_id=tid,reason=evidence.get('error','Native evidence pending or stale')))
                    feature={k:dict(geometric_mean=None,p10=None) for k in ('all_tokens','numeric_tokens','numeric_cells','structure_tokens','visible_tokens')}
                    alignment=None
                # Failed inference remains an error, never silently removed from accuracy.
                record=dict(record,text=record.get('text',''))
                row=dict(cohort=cohort,engine=engine,inference_status=record['status'],native_status='available' if native_ready else 'pending_or_failed',table_id=tid,issuer=ref['issuer'],reference_kind=ref['reference_kind'],
                         human_verified=ref['human_verified'],image_sha256=table['image_sha256'],
                         native_all=feature['all_tokens']['geometric_mean'],native_visible=feature['visible_tokens']['geometric_mean'],native_visible_p10=feature['visible_tokens']['p10'],native_numeric=feature['numeric_tokens']['geometric_mean'],
                         native_numeric_p10=feature['numeric_tokens']['p10'],native_number_p10=feature['numeric_cells']['p10'],
                         native_structure=feature['structure_tokens']['geometric_mean'],native_structure_p10=feature['structure_tokens']['p10'],
                         truncated=record.get('truncated',False),runtime_seconds=record.get('seconds'),reference_facts=len(expected))
                try:parsed=parse_output(record['text'],engine)
                except Exception as exc:parsed=dict(status='invalid_structure',format='invalid',grids=[],error=str(exc))
                predicted=flatten_facts(parsed['grids'],alignment)
                if parsed['status']=='structured':
                    metric=fact_score(expected,predicted)
                    data_numeric=numeric_score(ref_values,[n for f in predicted for n in numbers(f['raw'])]) if ref_values else {'f1':None}
                    grid=ordered_grid_score([r for g in ref['grids'] for r in g['cells']],[r for g in parsed['grids'] for r in g['cells']])
                    row.update(fact_f1=metric['f1'] if expected else None,fact_exact=metric['exact'] if expected else None,numeric_data_f1=data_numeric['f1'],grid_f1=grid['f1'],predicted_facts=len(predicted))
                else:
                    required=engine in ('paddle_vl','glm','monkey','mineru_table')
                    row.update(fact_f1=0. if required and expected else None,fact_exact=False if required and expected else None,numeric_data_f1=0. if required and expected else None,grid_f1=0. if required else None,predicted_facts=0)
                if engine in ('paddle_vl','glm','monkey','mineru_table') or parsed['status']=='structured':
                    key=digest(dict(reference=ref['grids'],predicted=parsed['grids'],code=sha(ROOT/'prototype/standard_metric.py'),vendor=sha(ROOT/'prototype/vendor/grits.py'),normalization=sha(ROOT/'prototype/table_structure.py')))
                    cached=RUN/'grits_cache'/(key+'.json')
                    if cached.exists():standard=read(cached)
                    else:standard=content_score(ref['grids'],parsed['grids']);write(cached,standard)
                    row['grits_content_f1']=standard['f1']
                else:row['grits_content_f1']=None
                row['financial_reference_eligible']=bool(expected)
                # Six-engine transcription recall is explicitly separate: extra
                # numbers/metadata are not penalized and association is ignored.
                transcription=numeric_score(ref_values,numbers(record['text'])) if ref_values else {'recall':None}
                row.update(structure_status=parsed['status'],financial_value_recall=transcription['recall'])
                counts=Counter(fact_key(f) for f in expected)
                cell_rows=[]
                for f in predicted:
                    key=fact_key(f);correct=counts[key]>0
                    if correct:counts[key]-=1
                    cell_rows.append(dict(**{k:v for k,v in f.items() if k!='key'},correct=correct))
                missing=[]
                for f in expected:
                    key=fact_key(f)
                    if counts[key]>0:missing.append(f);counts[key]-=1
                pairs.append(row)
                details.append(dict(**row,reference_grids=ref['grids'],predicted_grids=parsed['grids'],expected_facts=expected,predicted_facts_detail=cell_rows,
                                    missing_facts=missing,image_path=str((root/table['image']).resolve()),output_text=record['text'],parse_error=parsed.get('error')))
    assert code_hashes=={n:sha(ROOT/'prototype'/n) for n in code_files}, 'Scoring code changed during evaluation; rerun'
    results=dict(status='exploratory_development',pairs=pairs,pending=pending,availability=availability,
                 code_sha256=code_hashes,
                 caveats=['Fact extraction is deterministic and under audit; no broad accuracy claim until scoring disagreements are inspected.',
                          'Baseline OCR and text-only output do not necessarily provide explicit table structure; no fabricated association score.',
                          'Public benchmark may overlap model pretraining. Human, assistant and dataset references are distinguished.'])
    RESULTS.mkdir(parents=True,exist_ok=True);write(RESULTS/'pairs.json',results);write(RUN/'evaluation_details.json',details)
    for cohort in sorted({r['cohort'] for r in pairs}):
        for engine in sorted({r['engine'] for r in pairs if r['cohort']==cohort}):
            rows=[r for r in pairs if r['cohort']==cohort and r['engine']==engine];valid=[r for r in rows if r['fact_f1'] is not None]
            print(cohort,engine,'n',len(rows),'structured',len(valid),'fact F1',round(statistics.mean(r['fact_f1'] for r in valid),3) if valid else None,'numeric recall',round(statistics.mean(r['financial_value_recall'] for r in rows if r['financial_value_recall'] is not None),3) if any(r['financial_value_recall'] is not None for r in rows) else None)
    print('Native evidence pending:',len(pending))

if __name__=='__main__':main()
