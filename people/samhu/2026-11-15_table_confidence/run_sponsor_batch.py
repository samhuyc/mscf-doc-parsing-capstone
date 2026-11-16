"""Complete sequential recognition on the already preprocessed sponsor corpus.

Run with the base .venv Python and GPU access. Each model uses its own process
and existing environment. The report updates after the first crop and every ten
crops. Restarting resumes matching successful per-table records.
"""
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import time
import traceback

from regions import table_summary
from core import read, write, sha
from report import build
from verify import verify

ROOT = Path(__file__).resolve().parent


def now():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'runs/sponsor_all')
    args = parser.parse_args()
    root = args.root.resolve()
    bundle = read(root / 'tables.json')
    expected = sum(len(p) for p in bundle['settings']['selection']['pages'].values())
    if len(bundle['pages']) != expected or any(p['status'] != 'success' for p in bundle['pages']):
        raise ValueError('Finish preprocessing all selected pages before recognition')
    lock = root / 'batch.lock'
    try:
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError:
        pid = int(lock.read_text())
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            lock.unlink()
            fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        else:
            raise RuntimeError(f'Batch process {pid} already holds the run lock')
    with os.fdopen(fd, 'w') as stream:
        stream.write(str(os.getpid()))
    stages = [dict(engine=e, status='queued') for e in ('paddle_vl', 'glm', 'monkey', 'mineru')]
    status = dict(status='running', pid=os.getpid(), started_utc=now(),
                  source_bundle_sha256=sha(root / 'tables.json'), pages=expected,
                  table_regions=len(bundle['tables']), stages=stages,
                  implementation_sha256={name:sha(ROOT/name) for name in
                    ('run_sponsor_batch.py','run_extra_models.py','run_mineru_tables.py',
                     'extra_scores.py','regions.py','report.py','verify.py')})
    status_path = root / 'batch_status.json'
    try:
        for stage in stages:
            engine = stage['engine']
            stage.update(status='running', started_utc=now())
            write(status_path, status)
            build(root)
            if engine == 'mineru':
                command = [ROOT/'work/mineru-env/bin/python', ROOT/'run_mineru_tables.py',
                           '--root', root, '--report-every', '10']
            else:
                command = [ROOT/'work/extra-env/bin/python', ROOT/'run_extra_models.py', engine,
                           '--root', root, '--report-every', '10']
            log = root / f'{engine}.log'
            started = time.monotonic()
            print('Starting', engine, flush=True)
            with log.open('a') as stream:
                result = subprocess.run([str(c) for c in command], cwd=ROOT,
                                        stdout=stream, stderr=subprocess.STDOUT,
                                        env={**os.environ, 'PYTHONUNBUFFERED':'1'})
            stage.update(status='completed' if result.returncode == 0 else 'failed',
                         exit_code=result.returncode, finished_utc=now(),
                         seconds=round(time.monotonic()-started,3), log=log.name)
            write(status_path, status)
            build(root)
            print('Finished', engine, stage['status'], flush=True)
        audit = verify(root)
        expected_engines = {'paddle','tesseract','paddle_vl','glm','monkey','mineru'}
        complete = (not audit['pending'] and not audit['failed'] and
                    set(audit['successful']) == expected_engines and
                    all(n == len(bundle['tables']) for n in audit['successful'].values()) and
                    all(s['status'] == 'completed' for s in stages))
        status.update(status='completed' if complete else 'completed_with_errors', finished_utc=now(), audit='audit.json')
    except BaseException as exc:
        status.update(status='interrupted_or_failed', error=f'{type(exc).__name__}: {exc}', finished_utc=now())
        traceback.print_exc()
        raise
    finally:
        write(status_path, status)
        build(root)
        lock.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
