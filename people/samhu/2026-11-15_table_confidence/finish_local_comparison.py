"""Resume the saved MinerU crops and finalize the matched comparison locally."""
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess
import sys
from regions import NATIVE
from core import read,write,sha

ROOT=Path(__file__).resolve().parent
RUN=ROOT/'runs/sponsor_all'
def now():return datetime.now(timezone.utc).isoformat()

def main():
    lock=RUN/'batch.lock'
    if lock.exists():raise RuntimeError('Another batch lock exists; inspect it before resuming')
    status=read(RUN/'batch_status.json')
    write(RUN/'batch_status_before_local_resume.json',status)
    status.update(status='running',pid=os.getpid(),local_resume_utc=now(),
        local_workspace=str(ROOT),local_resume_code_sha256=sha(Path(__file__)))
    status.pop('error',None)
    stage=next(s for s in status['stages'] if s['engine']=='mineru')
    stage.update(status='running',local_resume_utc=now())
    lock.write_text(str(os.getpid()));write(RUN/'batch_status.json',status)
    try:
        print('Resuming MinerU from saved successful crops',flush=True)
        with (RUN/'mineru_local.log').open('a') as log:
            p=subprocess.run([sys.executable,str(ROOT/'run_mineru_tables.py'),'--root',str(RUN),
                              '--report-every','0'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                             env={**os.environ,'PYTHONUNBUFFERED':'1'})
        stage.update(status='completed' if p.returncode==0 else 'failed',exit_code=p.returncode,finished_utc=now())
        if p.returncode:raise RuntimeError(f'MinerU exited {p.returncode}; see mineru_local.log')
        from report import build
        from verify import verify
        from evaluate_table_accuracy import evaluate
        from plot_table_accuracy import plot
        build(RUN);audit=verify(RUN)
        assert not audit['pending'] and not audit['failed']
        assert len(audit['successful'])==6 and set(audit['successful'].values())=={103}
        result=evaluate(RUN,require_complete=True);plot(RUN)
        status.update(status='completed',finished_utc=now(),audit='audit.json',
            finalization_code_sha256={n:sha(ROOT/n) for n in ['report.py','verify.py',
                'evaluate_table_accuracy.py','numeric_accuracy.py','plot_table_accuracy.py']})
        write(RUN/'batch_status.json',status);build(RUN)
        dest=ROOT/'results/sponsor_all/accuracy';dest.mkdir(parents=True,exist_ok=True)
        for n in ['tracking.json','pairs.csv','confidence_vs_numeric_accuracy.png','confidence_vs_numeric_accuracy.svg']:
            shutil.copy2(RUN/'accuracy'/n,dest/n)
        shutil.copy2(RUN/'audit.json',ROOT/'results/sponsor_all/final_audit.json')
        write(RUN/'accuracy/progress.json',dict(status='completed',finished_utc=now(),
            matched_cohort=result['matched_cohort'],models={e:s['primary']['n'] for e,s in result['models'].items()}))
        print('Complete: six models, 103 crops each, identical 19-crop comparison',flush=True)
    except BaseException as exc:
        status.update(status='interrupted_or_failed',error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        write(RUN/'batch_status.json',status);lock.unlink(missing_ok=True)

if __name__=='__main__':main()
