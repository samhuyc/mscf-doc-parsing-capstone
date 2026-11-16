"""Finite evaluation stage for the current sponsor recognition batch.

Recompute source-checked relationships as selected results arrive, then finalize
after the recognition coordinator releases its lock. No recurring automation,
new inference, notifications, or external services are involved.
"""
import argparse
from datetime import datetime,timezone
import os
from pathlib import Path
import shutil
import time
import traceback

from regions import table_summary
from core import read,write,sha
from evaluate_table_accuracy import evaluate
from plot_table_accuracy import plot
from report import build

ROOT=Path(__file__).resolve().parent


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--root',type=Path,default=ROOT/'runs/sponsor_all')
    args=cli.parse_args();root=args.root.resolve();dest=root/'accuracy'
    dest.mkdir(exist_ok=True)
    lock=dest/'tracking.lock'
    fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    with os.fdopen(fd,'w') as f:f.write(str(os.getpid()))
    started=time.monotonic();previous=None;last_count=-100
    status=dict(status='following_recognition_batch',pid=os.getpid(),started_utc=datetime.now(timezone.utc).isoformat(),
        references_sha256=sha(ROOT/'accuracy_references.json'),
        evaluation_code_sha256=sha(ROOT/'evaluate_table_accuracy.py'),metric_code_sha256=sha(ROOT/'numeric_accuracy.py'))
    selected=[r['table_id'] for r in read(ROOT/'accuracy_references.json')['references']]
    try:
        while True:
            batch=read(root/'batch_status.json')
            terminal=batch['status']!='running' and not (root/'batch.lock').exists()
            counts={engine:sum((folder/(tid+'.json')).exists() for tid in selected)
                    for engine,folder in [('paddle_vl',root/'extra/paddle_vl'),('glm',root/'extra/glm'),
                                          ('monkey',root/'extra/monkey'),('mineru',root/'mineru')]}
            signature=(batch['status'],tuple((s['engine'],s['status']) for s in batch['stages']),tuple(counts.items()))
            changed_stage=previous is None or signature[:2]!=previous[:2]
            total=sum(counts.values())
            if terminal or changed_stage or total-last_count>=3:
                result=evaluate(root);plot(root);build(root)
                status.update(last_update_utc=datetime.now(timezone.utc).isoformat(),selected_output_counts=counts,
                              models={e:s['primary']['n'] for e,s in result['models'].items()})
                write(dest/'progress.json',status)
                previous=signature;last_count=total
                print(status['last_update_utc'],counts,flush=True)
            if terminal:
                status.update(status='completed' if batch['status']=='completed' else 'completed_with_incomplete_recognition',
                              finished_utc=datetime.now(timezone.utc).isoformat())
                outputs=ROOT/'results'/root.name/'accuracy';outputs.mkdir(parents=True,exist_ok=True)
                for name in ('tracking.json','pairs.csv','confidence_vs_numeric_accuracy.png','confidence_vs_numeric_accuracy.svg'):
                    shutil.copy2(dest/name,outputs/name)
                break
            try:os.kill(batch['pid'],0)
            except ProcessLookupError:
                status.update(status='coordinator_stopped_before_completion');break
            if time.monotonic()-started>6*3600:
                status.update(status='stopped_after_six_hours_partial_results_saved');break
            time.sleep(30)
    except BaseException as exc:
        status.update(status='failed',error=f'{type(exc).__name__}: {exc}')
        traceback.print_exc();raise
    finally:
        write(dest/'progress.json',status);lock.unlink(missing_ok=True)


if __name__=='__main__':main()
