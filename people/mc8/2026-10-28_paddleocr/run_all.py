"""Execute the current experiment scope, keeping model runs sequential."""
from datetime import datetime, timezone
import subprocess
import sys

from common import ROOT, dump, environment


def main():
    stages=[
        ('sponsor_inputs',['prepare.py']),
        ('model_downloads',['download_models.py']),
        ('sponsor_parsing',['run.py','--skip-existing']),
        ('sponsor_evaluation',['evaluate.py']),
        ('sponsor_report',['report.py']),
        ('sponsor_verification',['verify.py']),
        ('original_trial',['early_trial.py','--skip-existing']),
        ('dataset_preparation',['prepare_benchmarks.py']),
        ('dataset_parsing_scoring',['run_benchmarks.py','--skip-existing']),
        ('earlier_reports',['earlier_report.py']),
        ('final_verification',['verify.py']),
    ]
    workflow='workflow.json'
    if (ROOT/'results/selected_plan.json').exists():
        # The user's accuracy-first scope persists. Never silently resume all
        # 140 pages or launch earlier experiments after that decision.
        stages=[('selected_page_parsing',['selected_pages.py']),
                ('sponsor_evaluation',['evaluate.py']),
                ('sponsor_report',['report.py']),
                ('selected_page_verification',['verify.py'])]
        workflow='selected_workflow.json'
    records=[]
    for name,args in stages:
        entry=dict(stage=name,started_at_utc=datetime.now(timezone.utc).isoformat())
        result=subprocess.run([sys.executable,*args],cwd=ROOT,env=environment())
        entry.update(return_code=result.returncode,status='success' if result.returncode==0 else 'failed')
        records.append(entry)
        dump(ROOT/'results'/workflow,records)
        if result.returncode:
            raise SystemExit(result.returncode)


if __name__=='__main__':
    main()
