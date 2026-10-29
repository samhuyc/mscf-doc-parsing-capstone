"""Verify complete outputs, provenance, report links and unchanged baseline metrics."""
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
from bs4 import BeautifulSoup
from benchmark import ROOT, PARSERS, read_json, read_jsonl, prediction_dir, sha, write_json
def code_hashes():
    return {name: sha(ROOT/name) for name in ("run_pymupdf_vlm.py", "vlm_ocr_worker.py")}


def verify():
    result=read_json(ROOT/'results/preliminary.json')
    baseline=read_json(ROOT/'results/baseline_2026-10-05.json')
    assert result['label_sha256']==baseline['label_sha256']==sha(ROOT/'labels.jsonl')
    assert result['selected_labels']==baseline['selected_labels']==54
    for parser in PARSERS[:3]:
        assert result['aggregate'][parser]==baseline['aggregate'][parser],parser+' metrics changed'
        assert [x for x in result['inputs'] if x['parser']==parser]==[x for x in baseline['inputs'] if x['parser']==parser],parser+' original inputs changed'
    counts={p:0 for p in PARSERS};vlm_pages=0;regions=0
    for doc in read_json(ROOT/'documents.json'):
        for parser in PARSERS:
            work=prediction_dir(doc['id'],parser)
            run=read_json(work/'run.json');pages=read_json(work/'pages.json')
            assert run['status']=='success',(doc['id'],parser,run['status'])
            assert pages['source_sha256']==run['input_sha256']==doc['sha256']
            assert pages['parser']==parser
            assert [p['page'] for p in pages['pages']]==list(range(1,doc['pages']+1))
            assert run['document_sha256']==sha(work/'document.md')
            for link in re.findall(r'!\[[^\]]*\]\(([^)]+)\)', (work/'document.md').read_text()):
                assert not Path(link).is_absolute() and (work/link).is_file(), (work,link)
            counts[parser]+=len(pages['pages'])
            if parser=='pymupdf4llm_vlm':
                chunks=read_json(work/'raw_chunks.json')
                assert [c['metadata']['page_number'] for c in chunks]==list(range(1,doc['pages']+1))
                assert run['parsed_pages']==len(chunks)==len(pages['pages'])
                assert run['code_sha256']==code_hashes()
                assert run['export_adapter_sha256']==sha(ROOT/'export_vlm.py')
                audit=read_json(work/'ocr_pages.json')['pages']
                assert run['ocr_pages']==[x['page'] for x in audit]
                assert run['vlm_pages']==[x['page'] for x in audit if x['recognized_regions']]
                assert run['recognized_regions']==sum(x['recognized_regions'] for x in audit)
                for call in audit:
                    if 'raw_prediction' in call:
                        raw=read_json(work/call['raw_prediction'])
                        assert raw['status']=='success'
                        assert len(raw['predictions'])==call['recognized_regions']
                        for prediction in raw['predictions']:
                            assert isinstance(prediction['text'],str)
                            assert len(prediction['box'])==4
                vlm_pages+=len(run['vlm_pages']);regions+=run['recognized_regions']
    links=0
    for report in (ROOT/'review').glob('*.html'):
        soup=BeautifulSoup(report.read_text(),'html.parser')
        for tag in soup.select('[href], [src]'):
            link=tag.get('href',tag.get('src',''))
            parsed=urlsplit(link)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target=(report.parent/unquote(parsed.path)).resolve()
            assert target.exists(),f'{report.name}: broken link {link}'
            links+=1
    verified=dict(status='passed',complete_documents=24,pages_per_pipeline=counts,
                  baseline_metrics_unchanged=True,baseline_files_unchanged=True,labels_unchanged=True,
                  vlm_recognition_pages=vlm_pages,recognized_regions=regions,local_report_links_checked=links,
                  scorer_sha256=sha(ROOT/'benchmark.py'),label_sha256=sha(ROOT/'labels.jsonl'))
    write_json(ROOT/'results/verification.json',verified)
    print(json.dumps(verified,indent=2))
    return verified

if __name__=='__main__':
    verify()
