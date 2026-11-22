"""Explicit offline scoring using Sam's financial association F1 and GriTS."""
import argparse
from pathlib import Path
from common import HERE, DATA, config, read, write, sha, digest, environment, implementation_hashes
from progress import ScoringProgress
from score_summary import summarize_engines

STRUCTURED=('paddle_vl','glm','monkey','mineru_table')


def feature_row(record):
    f=record.get('native_features',{})
    def get(a,b):return f.get(a,{}).get(b)
    result=dict(native_numeric=get('numeric_tokens','geometric_mean'),native_all=get('all_tokens','geometric_mean'),
                native_numeric_p10=get('numeric_tokens','p10'),native_number_p10=get('numeric_cells','p10'),
                native_structure=get('structure_tokens','geometric_mean'),native_structure_p10=get('structure_tokens','p10'),
                native_visible=get('visible_tokens','geometric_mean'),native_visible_p10=get('visible_tokens','p10'))
    result.update({k:f.get(k) for k in ('native_header','native_header_p10','native_label','native_label_p10')})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--execute',action='store_true')
    p.add_argument('--split',choices=['development','test'],required=True)
    p.add_argument('--run-dir',type=Path,default=HERE/'runs/cpu_v1')
    p.add_argument('--limit',type=int,help='Score only this cumulative prefix of the split')
    p.add_argument('--cache-scores',action='store_true',help='Reuse unchanged per-table scores between batches')
    args=p.parse_args()
    if not args.execute:p.error('Scoring requires explicit --execute')
    if args.limit is not None and args.limit<1:p.error('--limit must be positive')
    environment()
    from sam_bridge import check_frozen_code,parse_output,flatten_facts,fact_score,content_score,numbers,numeric_score
    check_frozen_code()
    split_tables=[t for t in read(DATA/'tables.json')['tables'] if t['split']==args.split]
    tables=split_tables[:args.limit]
    refs=read(DATA/'references.json');run=args.run_dir.resolve();phase=run/args.split
    if args.split=='test':
        from calibrate import check_freeze
        frozen=check_freeze(run)
        seal=read(phase/'test-seal.json')
        if seal['calibration_sha256']!=sha(run/'calibrators-frozen.json'):raise ValueError('Test/calibration seal mismatch')
    pairs=[]
    settings={e:read(phase/e/'settings.json') if (phase/e/'settings.json').exists() else None for e in config()['engines']}
    current_adapters={n:sha(HERE/n) for n in ('worker.py','native_vlm.cpp','sam_bridge.py')}
    for engine,s in settings.items():
        if s is None:continue
        if s['config_sha256']!=sha(HERE/'config.json') or s['tables_sha256']!=sha(DATA/'tables.json'):
            raise ValueError('Inference configuration/data changed: '+engine)
        if s['adapters_sha256']!=current_adapters or s['runtime_build_sha256']!=sha(HERE/'runtime-build.json'):
            raise ValueError('Inference adapter/build changed; use a versioned experiment: '+engine)
        expected_model=read(HERE/'model-conversions.json').get('mineru' if engine=='mineru_table' else engine)
        if s['model_conversion']!=expected_model:raise ValueError('Model conversion changed: '+engine)
    provenance=dict(tables_sha256=sha(DATA/'tables.json'),references_sha256=sha(DATA/'references.json'),
                    config_sha256=sha(HERE/'config.json'),sam_code_lock_sha256=sha(HERE/'sam-code-lock.json'),
                    adapter_sha256=sha(HERE/'sam_bridge.py'),evaluator_sha256=sha(HERE/'evaluate.py'),implementation=implementation_hashes())
    calibration_sha=sha(run/'calibrators-frozen.json') if args.split=='test' else None
    progress=ScoringProgress(phase,len(tables))
    for table_index,table in enumerate(tables,1):
        tid=table['table_id'];ref=refs[tid]
        expected=None
        for engine in config()['engines']:
            path=phase/engine/(tid+'.json')
            cache=phase/'score-cache'/engine/(tid+'.json')
            if args.cache_scores:
                cache_key=dict(provenance=provenance,record_sha256=sha(path) if path.exists() else None,
                               settings_sha256=digest(settings[engine]),calibration_sha256=calibration_sha)
                if cache.exists():
                    cached=read(cache)
                    if cached['key']==cache_key:
                        pairs.append(cached['row'])
                        continue
            if expected is None:
                expected=flatten_facts(ref['grids'])
                ref_values=[n for f in expected for n in numbers(f['raw'])]
            record=read(path) if path.exists() else dict(status='missing',text='')
            if path.exists() and (record['image_sha256']!=table['image_sha256'] or record['source_sha256']!=table['source_sha256']):raise ValueError('Record provenance mismatch')
            if path.exists() and (settings[engine] is None or record['settings_sha256']!=digest(settings[engine])):raise ValueError('Record settings hash mismatch')
            text=record.get('text','') if record['status']=='success' else ''
            row=dict(table_id=tid,issuer=table['issuer'],engine=engine,split=args.split,
                     inference_status=record['status'],native_status=record.get('native_status','unavailable'),
                     sam_original=table['sam_original'],human_verified=False,reference_kind=ref['reference_kind'],
                     measurement_flags=ref.get('measurement_flags',[]),reference_facts=len(expected),
                     truncated=record.get('truncated',False),**feature_row(record))
            try:parsed=parse_output(text,engine)
            except Exception as exc:parsed=dict(status='invalid_structure',grids=[],error=str(exc))
            if engine in STRUCTURED:
                predicted=flatten_facts(parsed['grids'])
                row['fact_f1']=fact_score(expected,predicted)['f1'] if expected else None
                if expected and parsed['status']!='structured':row['fact_f1']=0.0
                row['grits_content_f1']=content_score(ref['grids'],parsed['grids'])['f1']
            else:row.update(fact_f1=None,grits_content_f1=None)
            row.update(financial_value_recall=numeric_score(ref_values,numbers(text))['recall'] if ref_values else None,
                       structure_status=parsed['status'],financial_reference_eligible=bool(expected))
            if args.split=='test' and engine in STRUCTURED and row['fact_f1'] is not None:
                from calibrate import forecast
                row.update(forecast(frozen['engines'][engine],row))
            pairs.append(row)
            if args.cache_scores:write(cache,dict(key=cache_key,row=row))
        progress.advance(table_index)
    output=phase/'pairs.json'
    payload=dict(provenance=provenance,pairs=pairs)
    if args.split=='development' and (run/'calibrators-frozen.json').exists():
        if not output.exists() or digest(read(output))!=digest(payload):raise RuntimeError('Development scores are frozen; use a new run version')
    write(output,payload)
    summary=summarize_engines(pairs,include_forecasts=args.split=='test',engines=config()['engines'])
    write(phase/'summary.json',dict(split=args.split,engines=summary,reference_status='Public labels; human audit pending',
                                   scored_tables=len(tables),total_split_tables=len(split_tables),
                                   table_correctness_probability=None))
    progress.finish()
    print('Saved',len(pairs),'scored records including missing/failed cases:',output)


if __name__=='__main__':main()
