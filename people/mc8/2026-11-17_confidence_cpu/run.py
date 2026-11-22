"""Plan or explicitly launch a sequential, resumable CPU experiment."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
from common import HERE, DATA, LOCAL, config, read, write, sha


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--execute',action='store_true',help='Actually run inference; omitted means plan only')
    cli.add_argument('--engines',nargs='+',choices=config()['engines'],default=config()['engines'])
    cli.add_argument('--limit',type=int);cli.add_argument('--run-dir',type=Path,default=HERE/'runs/cpu_v1')
    cli.add_argument('--retry-failed',action='store_true')
    cli.add_argument('--split',choices=['development','test'],default='development')
    args=cli.parse_args()
    if args.limit is not None and args.limit<1:cli.error('--limit must be positive')
    bundle=read(DATA/'tables.json')
    tables=[t for t in bundle['tables'] if t['split']==args.split][:args.limit]
    phase_dir=args.run_dir.resolve()/args.split
    plan=dict(tables=len(tables),engines=args.engines,planned_outputs=len(tables)*len(args.engines),
              one_model_at_a_time=True,run_dir=str(phase_dir),split=args.split,
              inference_authorized_by_flag=args.execute,calibration=False,evaluation=False)
    print(json.dumps(plan,indent=2),flush=True)
    if not args.execute:return
    from preflight import check
    check(require_ready=True)
    if args.split=='development' and (args.run_dir/'calibrators-frozen.json').exists():
        raise RuntimeError('Development inference is frozen. Use a new --run-dir to change development outputs.')
    if args.split=='test':
        from calibrate import check_freeze
        frozen=check_freeze(args.run_dir.resolve())
    args.run_dir.mkdir(parents=True,exist_ok=True)
    with (LOCAL/'inference.lock').open('a+') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError('Another CPU recognizer is already running')
        identity=dict(config_sha256=sha(HERE/'config.json'),tables_sha256=sha(DATA/'tables.json'),
                      engines=args.engines)
        identity['split']=args.split
        saved=phase_dir/'plan.json'
        if saved.exists() and read(saved)!=identity:raise RuntimeError('Run settings changed; use a new run directory')
        write(saved,identity)
        if args.split=='test':write(phase_dir/'test-seal.json',dict(calibration_sha256=sha(args.run_dir/'calibrators-frozen.json'),tables_sha256=sha(DATA/'tables.json')))
        failures=[]
        for engine in args.engines:
            command=[sys.executable,str(HERE/'worker.py'),'--execute','--engine',engine,'--run-dir',str(phase_dir),'--split',args.split]
            if args.limit:command+=['--limit',str(args.limit)]
            if args.retry_failed:command+=['--retry-failed']
            print('Starting',engine,flush=True)
            # Wait for this model process to exit before loading another.
            result=subprocess.run(command,cwd=HERE)
            if result.returncode<0:
                failures.append(engine)
                print(f'{engine} was terminated by signal {-result.returncode}; stopping the batch.',flush=True)
                break
            if result.returncode:failures.append(engine)
        write(phase_dir/'batch-status.json',dict(failed_engines=failures,inference_finished=not failures,
                                                  calibration_run=False,evaluation_run=False))
        if failures:raise SystemExit('Failures retained in run records: '+', '.join(failures))


if __name__=='__main__':main()
