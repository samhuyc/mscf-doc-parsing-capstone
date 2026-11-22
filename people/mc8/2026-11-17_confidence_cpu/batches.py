"""Checkpoint batches without changing recognizer settings or existing outputs."""
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys

from common import HERE, LOCAL, DATA, config, read, write, sha
from progress import ElapsedTimer, optional_read, timestamp
from score_summary import summarize_engines
from markdown_report import write_markdown, regenerate_reports


def batch_plan(tables, batch_size):
    batches = []
    # Finish development and freeze calibration before exposing held-out test data.
    for split in ('development', 'test'):
        selected = [t for t in tables if t['split'] == split]
        for start in range(0, len(selected), batch_size):
            chunk = selected[start:start+batch_size]
            batches.append(dict(number=len(batches)+1, split=split,
                                start=start, limit=start+len(chunk),
                                table_ids=[t['table_id'] for t in chunk]))
    return batches


def checkpoint(run, batch_size):
    tables = read(DATA/'tables.json')['tables']
    batches = batch_plan(tables, batch_size)
    identity = dict(batch_size=batch_size, tables_sha256=sha(DATA/'tables.json'),
                    config_sha256=sha(HERE/'config.json'), engines=config()['engines'])
    saved = optional_read(run/'batch-progress.json')
    if saved and (saved['identity'] != identity or saved['batches'] != batches):
        raise RuntimeError('Batch settings/data changed; keep the original --batch-size or use a new --run-dir')
    done = saved.get('completed_batches', 0)
    if not isinstance(done, int) or not 0 <= done <= len(batches):
        raise RuntimeError('Invalid saved batch checkpoint')
    return saved or dict(identity=identity, batches=batches, completed_batches=0), tables


def cumulative_summary(run, ledger, completed):
    batches = ledger['batches'][:completed]
    pairs = []
    splits = {}
    for split in ('development', 'test'):
        ids = {tid for b in batches if b['split'] == split for tid in b['table_ids']}
        if not ids:
            continue
        payload = read(run/split/'pairs.json')
        selected = [r for r in payload['pairs'] if r['table_id'] in ids]
        expected = {(tid, engine) for tid in ids for engine in ledger['identity']['engines']}
        actual = [(r['table_id'], r['engine']) for r in selected]
        if len(actual) != len(expected) or set(actual) != expected:
            raise RuntimeError('Incomplete cumulative scores for '+split)
        pairs.extend(selected)
        splits[split] = read(run/split/'summary.json')
        write_markdown(run/split/'summary.md', splits[split])
    summary = dict(completed_batches=completed, total_batches=len(ledger['batches']),
                   completed_tables=sum(len(b['table_ids']) for b in batches),
                   total_tables=sum(len(b['table_ids']) for b in ledger['batches']),
                   scored_outputs=len(pairs), updated_utc=timestamp(),
                   engines=summarize_engines(pairs, include_forecasts=True,
                                             engines=ledger['identity']['engines']), splits=splits,
                   result_scope='Cumulative completed batches; unrun tables excluded',
                   development_results='Descriptive development scores; not held-out validation',
                   reference_status='Public labels; human audit pending',
                   table_correctness_probability=None)
    # Preserve a reviewable result for every milestone, and replace the latest result atomically.
    write(run/'batch-results'/f'batch-{completed:02d}.json', summary)
    write(run/'summary.json', summary)
    write_markdown(run/'batch-results'/f'batch-{completed:02d}.md', summary)
    write_markdown(run/'summary.md', summary)
    return summary


def launch(run_dir, batch_size=100, execute=False, retry_failed=False, one_batch=False):
    run = Path(run_dir).resolve()
    ledger, tables = checkpoint(run, batch_size)
    done = ledger['completed_batches']
    batch = ledger['batches'][done] if done < len(ledger['batches']) else None
    next_batch = (dict(number=batch['number'], split=batch['split'],
                       tables=len(batch['table_ids']), cumulative_split_tables=batch['limit'])
                  if batch else None)
    print(json.dumps(dict(tables=len(tables), batch_size=batch_size,
                          total_batches=len(ledger['batches']), completed_batches=done,
                          next_batch=next_batch, execute=execute, run_dir=str(run),
                          continue_after_each_batch=not one_batch,
                          cumulative_results=dict(markdown=str(run/'summary.md'),
                                                  json=str(run/'summary.json'))), indent=2), flush=True)
    if not execute:
        return
    from preflight import check
    check(require_ready=True)
    LOCAL.mkdir(parents=True, exist_ok=True)
    with (LOCAL/'pipeline.lock').open('a+') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError('Another pipeline launcher is already running')
        # Re-read under the lock so two invocations cannot claim the same batch.
        ledger, tables = checkpoint(run, batch_size)
        done = ledger['completed_batches']
        if done == len(ledger['batches']):
            regenerate_reports(run)
            print('All batches are complete. Results:', run/'summary.md', flush=True)
            return
        frozen = run/'calibrators-frozen.json'
        timer = ElapsedTimer(optional_read(run/'pipeline-status.json'))
        state = dict(state='running', mode='batches', pid=os.getpid(), started_utc=timestamp(),
                     stage='preparing', completed_stages=[], error=None,
                     batch_number=done+1, total_batches=len(ledger['batches']),
                     completed_batches=done, continue_after_each_batch=not one_batch)

        def save_status():
            timer.update(state)
            state['updated_utc'] = timestamp()
            write(run/'pipeline-status.json', state)

        def stage(label, script, extra):
            state['stage'] = label
            save_status()
            print(label, flush=True)
            command = [sys.executable, str(HERE/script), '--execute', '--run-dir', str(run), *extra]
            if retry_failed and script == 'run.py':
                command.append('--retry-failed')
            subprocess.run(command, cwd=HERE, check=True)
            state['completed_stages'].append(label)

        write(run/'batch-progress.json', ledger)
        try:
            while ledger['completed_batches'] < len(ledger['batches']):
                done = ledger['completed_batches']
                batch = ledger['batches'][done]
                split = batch['split']
                state.update(stage='preparing', completed_stages=[], batch_number=batch['number'],
                             batch_tables=len(batch['table_ids']))
                save_status()
                if split == 'development' and frozen.exists():
                    # Recover an interruption after the last development freeze but before checkpointing.
                    last_dev = max(b['number'] for b in ledger['batches'] if b['split'] == 'development')
                    if batch['number'] != last_dev:
                        raise RuntimeError('Development is already frozen; use --full to resume this older full run, or a new --run-dir')
                extra = ['--split', split, '--limit', str(batch['limit'])]
                if frozen.exists():
                    from calibrate import check_freeze
                    check_freeze(run)
                if not (split == 'development' and frozen.exists()):
                    # The unchanged worker reuses all compatible outputs within this prefix.
                    stage(f'Batch {batch["number"]}: {split} inference', 'run.py', extra)
                    stage(f'Cumulative {split} scoring ({batch["limit"]} tables)',
                          'evaluate.py', [*extra, '--cache-scores'])
                future_dev = any(b['split'] == 'development' for b in ledger['batches'][done+1:])
                if split == 'development' and not future_dev and not frozen.exists():
                    stage('Freeze calibration after all development batches', 'calibrate.py', [])
                summary = cumulative_summary(run, ledger, done+1)
                ledger.update(completed_batches=done+1, updated_utc=timestamp())
                write(run/'batch-progress.json', ledger)
                state.update(stage='batch finished', completed_batches=done+1,
                             completed_tables=summary['completed_tables'])
                save_status()
                print(f'Batch {done+1}/{len(ledger["batches"])} finished; '
                      f'{summary["completed_tables"]}/{len(tables)} tables. '
                      f'Results: {run/"summary.md"} and {run/"summary.json"}', flush=True)
                if one_batch:
                    break
                if done+1 < len(ledger['batches']):
                    print('Continuing to the next batch.', flush=True)
            state.update(state='complete' if ledger['completed_batches'] == len(ledger['batches']) else 'batch_complete',
                         stage='finished')
        except BaseException as exc:
            state.update(state='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                         error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            save_status()
    if ledger['completed_batches'] == len(ledger['batches']):
        print('Experiment complete. Results:', run/'summary.md', flush=True)
    else:
        print('Stopped after one batch (--one-batch). Run again to resume.', flush=True)
