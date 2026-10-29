"""Small, read-only progress summary for long CPU runs."""
import json
from pathlib import Path
import re
import sys
from common import ROOT

if '--compact' in sys.argv:
    summary={}
    for group,base in [('sponsor','results/parsed'),('original_trial','early/results'),('benchmarks','benchmarks/results')]:
        runs=[]
        for path in sorted((ROOT/base).rglob('run.json')):
            record=json.loads(path.read_text())
            if 'document' not in record:
                continue
            progress=path.parent/'selected_progress.json'
            if not progress.exists():
                progress=path.parent/'progress.json'
            done=json.loads(progress.read_text()).get('completed_pages',0) if progress.exists() else 0
            runs.append(dict(document=record['document'],status=record['status'],pages=done,expected=record['expected_pages']))
        summary[group]=dict(completed_documents=sum(r['status'] in {'success','partial','empty'} for r in runs),
                            processed_pages=sum(r['pages'] for r in runs),active=[r for r in runs if r['status']=='started'],
                            failures=[r for r in runs if r['status']=='failed'])
    print(json.dumps(summary,indent=2))
    raise SystemExit(0)


for base in ['results/parsed','early/results','benchmarks/results']:
    for path in sorted((ROOT/base).rglob('run.json')):
        data=json.loads(path.read_text())
        if 'document' not in data:
            continue
        progress=path.parent/'selected_progress.json'
        if not progress.exists():
            progress=path.parent/'progress.json'
        pages=json.loads(progress.read_text()).get('completed_pages',0) if progress.exists() else 0
        print(str(path.parent.relative_to(ROOT)),data['status'],f'{pages}/{data.get("expected_pages",0)} pages',data.get('elapsed_seconds',''))
        if data['status']=='started':
            log=path.parent/'parser.log'
            if log.exists():
                lines=log.read_text(errors='replace').splitlines()
                meaningful=[line for line in lines if line.strip() and not re.match(r'^\[.*\] [\d.]+%',line)]
                print('\n'.join(meaningful[-5:]))
                percentages=[line for line in lines if re.match(r'^\[.*\] [\d.]+%',line)]
                if percentages:
                    print('Last download progress:',percentages[-1].strip())
