"""Run remaining 100-table batches with cumulative Markdown/JSON results; plan without --execute."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from common import HERE,LOCAL,config,read,write,DATA
from progress import timestamp, ElapsedTimer, optional_read


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--execute',action='store_true',help='Run inference, scoring and calibration for the selected work')
    p.add_argument('--run-dir',type=Path,default=HERE/'runs/cpu_v1')
    p.add_argument('--retry-failed',action='store_true')
    p.add_argument('--batch-size',type=int,default=100,help='Tables per batch (default: 100)')
    mode=p.add_mutually_exclusive_group()
    mode.add_argument('--one-batch',action='store_true',help='Stop after one batch; default continues through all remaining batches')
    mode.add_argument('--full',action='store_true',help='Run the original uninterrupted full experiment')
    args=p.parse_args()
    if args.batch_size<1:p.error('--batch-size must be positive')
    if not args.full:
        from batches import launch
        return launch(args.run_dir,args.batch_size,args.execute,args.retry_failed,one_batch=args.one_batch)
    run=args.run_dir.resolve()
    stages=[('first-table check for every recognizer','run.py',['--split','development','--limit','1']),
            ('development inference','run.py',['--split','development']),
            ('development scoring','evaluate.py',['--split','development']),
            ('freeze development calibration','calibrate.py',[]),
            ('held-out test inference','run.py',['--split','test']),
            ('held-out test scoring','evaluate.py',['--split','test'])]
    print(json.dumps(dict(tables=config()['tables'],sam_original=71,additional=1929,
        recognizers=6,configurations=7,planned_outputs=config()['tables']*7,
        stages=[s[0] for s in stages],execute=args.execute,run_dir=str(run)),indent=2),flush=True)
    if not args.execute:return
    from preflight import check
    check(require_ready=True)
    # Hold the launcher lock across scoring/calibration as well as inference.
    # The existing inference lock still protects separately launched run.py jobs.
    with (LOCAL/'pipeline.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another pipeline launcher is already running')
        timer=ElapsedTimer(optional_read(run/'pipeline-status.json'))
        state=dict(state='running',pid=os.getpid(),started_utc=timestamp(),
                   stage='preparing',completed_stages=[],error=None)
        def save_status():
            timer.update(state)
            state['updated_utc']=timestamp()
            write(run/'pipeline-status.json',state)
        frozen=run/'calibrators-frozen.json'
        try:
            if frozen.exists():
                from calibrate import check_freeze
                check_freeze(run)
                state['completed_stages']=[s[0] for s in stages[:4]]
                stages=stages[4:]
            for label,script,extra in stages:
                state.update(stage=label,updated_utc=timestamp())
                save_status()
                print(label,flush=True)
                command=[sys.executable,str(HERE/script),'--execute','--run-dir',str(run),*extra]
                if args.retry_failed and script=='run.py':command+=['--retry-failed']
                subprocess.run(command,cwd=HERE,check=True)
                state['completed_stages'].append(label)
            state.update(state='complete',stage='finished')
        except BaseException as exc:
            state.update(state='interrupted' if isinstance(exc,KeyboardInterrupt) else 'failed',
                         error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            save_status()
    from markdown_report import regenerate_reports
    regenerate_reports(run)
    print('Experiment complete. Results:',run/'test/summary.md','and',run/'test/summary.json')


if __name__=='__main__':main()
