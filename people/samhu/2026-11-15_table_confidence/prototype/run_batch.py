"""Sequential, resumable local inference with a single heavy model at a time."""
import argparse
import os
from pathlib import Path
import subprocess
import time
from datetime import datetime,timezone
from common import ROOT, read, write, sha

def now():return datetime.now(timezone.utc).isoformat()
def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--engines',nargs='+',default=['baselines','paddle_vl','glm','monkey','mineru']);a=p.parse_args()
    root=a.root.resolve();lock=ROOT/'runs/native_prototype/inference.lock'
    if lock.exists():
        pid=int(lock.read_text())
        try:os.kill(pid,0)
        except ProcessLookupError:lock.unlink()
        else:raise RuntimeError(f'Inference already running: {pid}')
    lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('x') as f:f.write(str(os.getpid()))
    status=dict(started_utc=now(),pid=os.getpid(),source_bundle_sha256=sha(root/'tables.json'),stages=[],status='running')
    try:
        for engine in a.engines:
            if engine=='baselines':cmd=[ROOT/'work/base-env/bin/python',ROOT/'prototype/run_baselines.py','--root',root]
            elif engine in ('mineru','mineru_table'):cmd=[ROOT/'work/mineru-env/bin/python',ROOT/'run_mineru_tables.py','--root',root,'--report-every','0','--no-report','--task','table' if engine=='mineru_table' else 'text']
            else:cmd=[ROOT/'work/extra-env/bin/python',ROOT/'run_extra_models.py',engine,'--root',root,'--report-every','0']
            stage=dict(engine=engine,status='running',started_utc=now());status['stages'].append(stage);write(root/'prototype_batch.json',status)
            print('Starting',engine,root.name,flush=True)
            with (root/(engine+'.log')).open('a') as f:
                run=subprocess.run([str(x) for x in cmd],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT,env={**os.environ,'PYTHONUNBUFFERED':'1'})
            stage.update(status='completed' if run.returncode==0 else 'failed',exit_code=run.returncode,finished_utc=now());write(root/'prototype_batch.json',status)
            print('Finished',engine,stage['status'],flush=True)
        status['status']='completed' if all(x['status']=='completed' for x in status['stages']) else 'completed_with_errors'
    finally:
        status['finished_utc']=now();write(root/'prototype_batch.json',status);lock.unlink(missing_ok=True)
if __name__=='__main__':main()
