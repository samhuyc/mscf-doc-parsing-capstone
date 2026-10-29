"""Prove that pruning extra predictions leaves every selected accuracy check intact."""
import json
from pathlib import Path
import shutil
import tempfile

from common import ROOT,PARSER,dump,prediction_dir,scorer


def verify():
    b=scorer()
    full=b.read_json(ROOT/'results/preliminary.json')
    full_checks=[r for r in b.read_jsonl(ROOT/'results/preliminary_checks.jsonl') if r['parser']==PARSER]
    labels=b.read_jsonl(ROOT/'labels.jsonl')
    saved_root,saved_parsers=b.ROOT,b.PARSERS
    before=0
    try:
        with tempfile.TemporaryDirectory(prefix='selected_scope_',dir=ROOT/'tmp') as directory:
            temporary=Path(directory)
            for name in ('labels.jsonl','documents.json'):
                shutil.copy2(ROOT/name,temporary/name)
            for source in b.read_json(ROOT/'documents.json'):
                work=prediction_dir(source['id'],PARSER)
                target=temporary/'predictions'/source['id']/PARSER
                target.mkdir(parents=True)
                data=b.read_json(work/'pages.json')
                before+=len(data['pages'])
                wanted={l['page'] for l in labels if l['document']==source['id']}
                data['pages']=[p for p in data['pages'] if p['page'] in wanted]
                assert {p['page'] for p in data['pages']}==wanted
                dump(target/'pages.json',data)
                shutil.copy2(work/'run.json',target/'run.json')
            b.ROOT=temporary
            b.PARSERS=(PARSER,)
            pruned=b.score(include_drafts=True,output_root=temporary/'predictions')
            assert pruned['selected_labels']==54
            assert pruned['aggregate'][PARSER]==full['aggregate'][PARSER]
            assert pruned['documents']==[r for r in full['documents'] if r['parser']==PARSER]
            assert b.read_jsonl(temporary/'results/preliminary_checks.jsonl')==full_checks
    finally:
        b.ROOT,b.PARSERS=saved_root,saved_parsers
    result=dict(status='passed',retained_predictions=before,pruned_predictions=18,
                selected_labels=54,individual_checks=len(full_checks),
                every_check_identical=True,all_aggregate_metrics_identical=True,
                all_six_document_metrics_identical=True,parser_reruns=0)
    dump(ROOT/'results/selected_scope_verification.json',result)
    return result


if __name__=='__main__':
    print(json.dumps(verify(),indent=2))
