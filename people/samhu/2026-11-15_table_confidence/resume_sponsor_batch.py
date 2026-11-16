"""Resume the interrupted report refresh without repeating saved inference."""
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import subprocess

from regions import NATIVE
from core import read, write, sha

ROOT=Path(__file__).resolve().parent
RUN=ROOT/'runs/sponsor_all'

def now():
    return datetime.now(timezone.utc).isoformat()

def main():
    for lock in (RUN/'batch.lock', RUN/'accuracy/tracking.lock'):
        if lock.exists():
            try: os.kill(int(lock.read_text()),0)
            except ProcessLookupError: lock.unlink()
            else: raise RuntimeError(f'Active process holds {lock}')
    status=read(RUN/'batch_status.json')
    write(RUN/'batch_status_before_recovery.json',status)
    status.update(status='running',pid=os.getpid(),recovery_started_utc=now(),
        recovery_reason='Report image read stalled after Monkey crop 100; saved inference preserved',
        recovery_code_sha256=sha(Path(__file__)))
    (RUN/'batch.lock').write_text(str(os.getpid()))
    try:
        for engine in ('monkey','mineru'):
            stage=next(s for s in status['stages'] if s['engine']==engine)
            stage.update(status='running',resumed_utc=now())
            write(RUN/'batch_status.json',status)
            command=([ROOT/'work/extra-env/bin/python',ROOT/'run_extra_models.py','monkey']
                if engine=='monkey' else [ROOT/'work/mineru-env/bin/python',ROOT/'run_mineru_tables.py'])
            command += ['--root',RUN,'--report-every','0']
            print('Resuming',engine,flush=True)
            with (RUN/f'{engine}.log').open('a') as log:
                p=subprocess.run(list(map(str,command)),cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                    env={**os.environ,'PYTHONUNBUFFERED':'1'})
            stage.update(status='completed' if p.returncode==0 else 'failed',
                         exit_code=p.returncode,finished_utc=now())
            write(RUN/'batch_status.json',status)
            if p.returncode: raise RuntimeError(f'{engine} exited {p.returncode}')
        from report import build
        from verify import verify
        from evaluate_table_accuracy import evaluate
        from plot_table_accuracy import plot
        build(RUN)
        audit=verify(RUN)
        assert not audit['pending'] and not audit['failed']
        assert len(audit['successful'])==6 and set(audit['successful'].values())=={103}
        result=evaluate(RUN,require_complete=True)
        plot(RUN)
        status.update(status='completed',finished_utc=now(),audit='audit.json')
        write(RUN/'batch_status.json',status)
        build(RUN)
        dest=ROOT/'results/sponsor_all/accuracy';dest.mkdir(parents=True,exist_ok=True)
        for name in ('tracking.json','pairs.csv','confidence_vs_numeric_accuracy.png','confidence_vs_numeric_accuracy.svg'):
            shutil.copy2(RUN/'accuracy'/name,dest/name)
        shutil.copy2(RUN/'audit.json',ROOT/'results/sponsor_all/final_audit.json')
        write(RUN/'accuracy/progress.json',dict(status='completed',finished_utc=now(),
            matched_cohort=result['matched_cohort'],models={e:s['primary']['n'] for e,s in result['models'].items()}))
        print('Completed all six models and matched 19-crop evaluation',flush=True)
    except BaseException as exc:
        status.update(status='interrupted_or_failed',error=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        write(RUN/'batch_status.json',status)
        (RUN/'batch.lock').unlink(missing_ok=True)

if __name__=='__main__':main()
