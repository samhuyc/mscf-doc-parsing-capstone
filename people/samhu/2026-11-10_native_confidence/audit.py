"""Validate saved outputs and export compact provenance/coverage artifacts."""
import argparse
import hashlib
import math
from pathlib import Path
from core import ROOT, digest, document_result, read, sha, sources, summarize, write


def audit(run, output, allow_partial=False):
    settings=read(run/'settings.json')
    engine=settings['engine']
    documents=[]
    page_summaries=[]
    examples=[]
    generation_issues=[]
    for source in sources():
        pages=[]
        for path in sorted((run/source['id']).glob('page_*.json')):
            page=read(path)
            assert page['document']==source['id']
            assert page['engine']==engine
            assert path.name==f'page_{page["page"]:03}.json'
            assert page['source_sha256']==source['sha256']
            assert page['settings_sha256']==digest(settings)
            assert page['status'] in ('success','failed')
            if page['status']=='success':
                units=page.get('confidence_units',page['units'])
                assert page['confidence']==summarize(units)
                for unit in units:
                    if engine=='tesseract':assert unit['score']==unit['native_score']/100
                    elif engine=='paddle':assert unit['score']==unit['native_score']
                    elif engine=='mineru':
                        assert math.isclose(unit['score'],math.exp(unit['log_probability']),abs_tol=1e-7)
                        assert abs(unit['backend_log_probability']-unit['log_normalization_correction']-unit['log_probability'])<1e-5
                if not examples:
                    examples=[{'document':source['id'],'page':page['page'],'units':units[:5]}]
            pages.append(page)
            if page.get('truncated'):
                generation_issues.append({'document':source['id'],'page':page['page'],
                    'stop_reason':page['stop_reason'],'confidence':page['confidence'],
                    'output_tail':page.get('text','')[-200:]})
            page_summaries.append({k:v for k,v in page.items()
                                   if k not in ('units','confidence_units','text')})
            page_summaries[-1]['output_text_sha256']=hashlib.sha256(page.get('text','').encode()).hexdigest()
            page_summaries[-1]['raw_record_sha256']=sha(path)
        doc=document_result(source['id'],engine,pages,source['pages'])
        if not allow_partial:
            assert doc['successful_pages']==doc['expected_pages'], f'Incomplete run: {source["id"]}'
        documents.append(doc)
    dest=output/engine
    write(dest/'settings.json',settings)
    write(dest/'documents.json',documents)
    write(dest/'pages.json',page_summaries)
    write(dest/'native_examples.json',examples)
    write(dest/'generation_issues.json',generation_issues)
    result={'engine':engine,'successful_pages':sum(d['successful_pages'] for d in documents),
            'expected_pages':sum(d['expected_pages'] for d in documents),
            'scored_units':sum(d['confidence']['scored_units'] for d in documents),
            'inference_seconds_sum':round(sum(p['seconds'] for p in page_summaries),3),
            'truncated_pages':sum(len(d['truncated_pages']) for d in documents),
            'failed_pages':sum(p['status']=='failed' for p in page_summaries)}
    print(result)
    return result


if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('runs',type=Path,nargs='+')
    cli.add_argument('--output',type=Path,default=ROOT/'results')
    cli.add_argument('--allow-partial',action='store_true')
    args=cli.parse_args()
    inventory=[audit(run,args.output,args.allow_partial) for run in args.runs]
    write(args.output/'run_inventory.json',inventory)
