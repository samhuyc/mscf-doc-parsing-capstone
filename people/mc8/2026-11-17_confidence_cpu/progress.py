"""Read-only terminal tracker. Never imports or starts a recognizer."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time

from common import HERE, DATA, config, read, write


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def alive(pid):
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def optional_read(path):
    try:
        return read(path)
    except FileNotFoundError:
        return {}


def epoch(value):
    return datetime.fromisoformat(value).timestamp() if value else None


def elapsed_seconds(status):
    """Exclude pauses; dead processes stop accumulating at their last checkpoint."""
    if not status:
        return 0
    now = time.time()
    updated = epoch(status.get('updated_utc'))
    running = status.get('state') == 'running' and alive(status.get('pid'))
    if 'elapsed_seconds' in status:
        return status['elapsed_seconds'] + (max(0, now-updated) if running and updated else 0)
    # Read summaries created before cumulative timers were added. Retained
    # per-table time also includes cached pilot outputs from older sessions.
    started = epoch(status.get('started_utc'))
    end = now if running else updated
    span = max(0, end-started) if started is not None and end is not None else 0
    return max(status.get('seconds', 0), span)


class ElapsedTimer:
    def __init__(self, previous):
        self.previous_seconds = elapsed_seconds(previous)
        self.started = time.monotonic()
        self.first_started_utc = previous.get('first_started_utc') or previous.get('started_utc') or timestamp()

    def update(self, state):
        state['elapsed_seconds'] = self.previous_seconds + max(0, time.monotonic()-self.started)
        state['first_started_utc'] = self.first_started_utc


class InferenceProgress:
    """Small atomic summaries; existing records are counted once on resume."""

    def __init__(self, root, engine, split, tables):
        self.path = root / 'progress.json'
        self.records = {}
        for table in tables:
            record = optional_read(root / (table['table_id'] + '.json'))
            if record:
                self.records[table['table_id']] = (record['status'], record.get('seconds', 0))
        previous = optional_read(self.path)
        if not previous:
            previous = dict(seconds=sum(seconds for _, seconds in self.records.values()))
        self.timer = ElapsedTimer(previous)
        self.state = dict(engine=engine, split=split, total=len(tables), pid=os.getpid(),
                          state='running', started_utc=timestamp(), current_table=None,
                          current_started_epoch=None, last_error=None)
        self.save()

    def save(self):
        counts = Counter(status for status, _ in self.records.values())
        self.timer.update(self.state)
        self.state.update(succeeded=counts['success'], failed=counts['failed'],
                          processed=counts['success'] + counts['failed'],
                          seconds=sum(seconds for _, seconds in self.records.values()),
                          updated_utc=timestamp())
        write(self.path, self.state)

    def start(self, table_id):
        self.state.update(current_table=table_id, current_started_epoch=time.time())
        self.save()

    def record(self, table_id, record):
        self.records[table_id] = (record['status'], record['seconds'])
        self.state.update(current_table=None, current_started_epoch=None,
                          last_error=record.get('error'))
        self.save()

    def finish(self, state):
        self.state.update(state=state, current_table=None, current_started_epoch=None)
        self.save()


class ScoringProgress:
    def __init__(self, phase, total):
        self.path = phase / 'scoring-progress.json'
        self.state = dict(state='running', pid=os.getpid(), total=total, completed=0,
                          started_utc=timestamp())
        self.save()

    def save(self):
        self.state['updated_utc'] = timestamp()
        write(self.path, self.state)

    def advance(self, completed):
        self.state['completed'] = completed
        # At most one checkpoint per ten tables, independent of table size.
        if completed % 10 == 0 or completed == self.state['total']:
            self.save()

    def finish(self):
        self.state['state'] = 'complete'
        self.save()


def snapshot(run, tables=None, engines=None):
    """Read only 14 small counters, even when 14,000 large records exist."""
    tables = tables if tables is not None else read(DATA / 'tables.json')['tables']
    engines = engines if engines is not None else config()['engines']
    split_sizes = Counter(t['split'] for t in tables)
    rows = []
    active = []
    for engine in engines:
        row = dict(engine=engine, total=len(tables), succeeded=0, failed=0, processed=0,
                   seconds=0, elapsed_seconds=0, current_table_seconds=0, splits={})
        for split in ('development', 'test'):
            status = optional_read(run / split / engine / 'progress.json')
            counts = {k: status.get(k, 0) for k in ('succeeded', 'failed', 'processed', 'seconds')}
            counts['total'] = split_sizes[split]
            row['splits'][split] = counts
            for key in ('succeeded', 'failed', 'processed', 'seconds'):
                row[key] += counts[key]
            row['elapsed_seconds'] += elapsed_seconds(status)
            if status.get('state') == 'running':
                running = alive(status.get('pid'))
                end = time.time() if running else epoch(status.get('updated_utc'))
                current = max(0, end-status['current_started_epoch']) if end is not None and status.get('current_started_epoch') else 0
                if running:
                    row['current_table_seconds'] += current
                active.append(dict(engine=engine, split=split,
                                   table=status.get('current_table'),
                                   seconds_in_table=current,
                                   state='running' if running else 'interrupted',
                                   last_error=status.get('last_error')))
            elif status.get('state') in ('failed', 'interrupted'):
                active.append(dict(engine=engine, split=split, table=None,
                                   seconds_in_table=0, state=status['state'],
                                   last_error=status.get('last_error')))
        row['percent'] = 100 * row['processed'] / row['total'] if row['total'] else 0
        remaining = row['total']-row['processed']
        row['remaining_inference_seconds_estimate'] = (
            max(0, remaining*row['seconds']/row['processed']-row['current_table_seconds'])
            if remaining and row['succeeded'] and not row['failed'] else 0 if not remaining else None)
        rows.append(row)
    total = len(tables) * len(engines)
    processed = sum(r['processed'] for r in rows)
    stage = optional_read(run / 'pipeline-status.json')
    total_elapsed = elapsed_seconds(stage) if stage else sum(r['elapsed_seconds'] for r in rows)
    if stage.get('state') == 'running' and not alive(stage.get('pid')):
        stage['state'] = 'interrupted'
    estimate = None
    remaining = [r for r in rows if r['processed'] < r['total']]
    if not remaining:
        estimate = 0
    elif all(r['succeeded'] and r['processed'] and not r['failed'] for r in remaining):
        estimate = sum(r['remaining_inference_seconds_estimate'] for r in remaining)
    scoring = {split: optional_read(run / split / 'scoring-progress.json')
               for split in ('development', 'test')}
    for status in scoring.values():
        if status.get('state') == 'running' and not alive(status.get('pid')):
            status['state'] = 'interrupted'
    return dict(run_dir=str(run), planned_outputs=total, processed=processed,
                succeeded=sum(r['succeeded'] for r in rows), failed=sum(r['failed'] for r in rows),
                inference_percent=100*processed/total if total else 0,
                total_elapsed_seconds=total_elapsed,
                total_elapsed_scope='pipeline' if stage else 'model workers',
                remaining_inference_seconds_estimate=estimate, engines=rows, active=active,
                pipeline=stage, scoring=scoring,
                calibration_frozen=(run/'calibrators-frozen.json').exists())


def duration(seconds):
    seconds = max(0, int(seconds))
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return (f'{days}d ' if days else '') + f'{hours:02}:{minutes:02}:{seconds:02}'


def render(data):
    done, total = data['processed'], data['planned_outputs']
    percent = data['inference_percent']
    bar = '#' * int(percent/4) + '-' * (25-int(percent/4))
    lines = [f"Run: {data['run_dir']}",
             f'Inference [{bar}] {percent:6.2f}%  {done:,}/{total:,} processed',
             f"Successful: {data['succeeded']:,}   Failed: {data['failed']:,}",
             'Percent counts completed attempts, including failures; scoring/calibration are separate.']
    stage = data['pipeline']
    stage_count = (f"batch {stage['batch_number']}/{stage['total_batches']}; "
                   f"{stage['completed_batches']} batches finished"
                   if stage.get('mode') == 'batches' else
                   f"{len(stage.get('completed_stages', []))}/6 stages finished")
    lines.append(f"Pipeline: {stage.get('state', 'not started')} | "
                 f"Stage: {stage.get('stage', 'waiting')} ({stage_count})")
    lines.append(f"Total running time ({data['total_elapsed_scope']}): {duration(data['total_elapsed_seconds'])}")
    if stage.get('error'):
        lines.append('Error: ' + stage['error'])
    lines += ['', f"{'Configuration':<16} {'Processed':>12} {'%':>7} {'Success':>8} {'Failed':>7} {'Runtime':>12} {'Left (est.)':>12}"]
    for row in data['engines']:
        left = row['remaining_inference_seconds_estimate']
        lines.append(f"{row['engine']:<16} {row['processed']:>5}/{row['total']:<6} "
                     f"{row['percent']:>6.2f}% {row['succeeded']:>8} {row['failed']:>7} "
                     f"{duration(row['elapsed_seconds']):>12} {duration(left) if left is not None else '--':>12}")
    lines.append('Runtime includes model loading and processing; resume pauses are excluded.')
    for split in ('development', 'test'):
        count = sum(r['splits'][split]['processed'] for r in data['engines'])
        total_split = sum(r['splits'][split]['total'] for r in data['engines'])
        scoring = data['scoring'][split]
        score_text = f"{scoring.get('completed', 0)}/{scoring['total']} tables ({scoring['state']})" if scoring else 'not started'
        lines.append(f'{split.capitalize()}: inference {count:,}/{total_split:,}; scoring {score_text}')
    lines.append('Calibration: ' + ('frozen' if data['calibration_frozen'] else 'pending'))
    for item in data['active']:
        lines.append(f"{item['engine']} / {item['split']}: {item['state']} | "
                     f"{item['table'] or 'loading/resuming'} | elapsed {duration(item['seconds_in_table'])}")
        if item.get('last_error'):
            lines.append('  ' + item['last_error'])
    eta = data['remaining_inference_seconds_estimate']
    lines.append('Rough inference time remaining: ' + (duration(eta) if eta is not None else
                 'available after successful timing samples for every remaining configuration'))
    if eta is not None:
        lines.append('Rough total inference runtime: ' + duration(sum(r['elapsed_seconds'] for r in data['engines'])+eta)
                     + ' (scoring/calibration excluded)')
    lines.append('Ctrl+C closes this tracker; it does not stop the experiment in the other terminal.')
    return '\n'.join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', type=Path, default=HERE/'runs/cpu_v1')
    p.add_argument('--watch', action='store_true', help='Refresh until Ctrl+C; never starts inference')
    p.add_argument('--interval', type=float, default=5, help='Refresh interval in seconds (default: 5)')
    p.add_argument('--json', action='store_true', help='Print a machine-readable snapshot')
    args = p.parse_args()
    if args.interval < 1:
        p.error('--interval must be at least 1 second')
    tables = read(DATA/'tables.json')['tables']
    engines = config()['engines']
    try:
        while True:
            data = snapshot(args.run_dir.resolve(), tables, engines)
            if args.watch and sys.stdout.isatty() and not args.json:
                print('\033[2J\033[H', end='')
            print(json.dumps(data, indent=2) if args.json else render(data), flush=True)
            if not args.watch:
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
