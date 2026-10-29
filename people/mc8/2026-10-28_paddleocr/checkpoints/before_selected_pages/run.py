"""Sam's sequential full-document workflow with PP-StructureV3 replacing MinerU."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time

from common import ROOT, PARSER, dump, environment, export_pages


def code_hashes():
    return {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
            for name in ('run.py', 'paddle_worker.py', 'common.py', 'formats.py')}


def run(source, pdf, work, skip_existing=False, timeout=14400):
    source_hash = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if source_hash != source['sha256']:
        raise ValueError('Input hash mismatch')
    if work.exists():
        prior = json.loads((work/'run.json').read_text()) if (work/'run.json').exists() else {}
        if skip_existing and prior.get('status') in {'success','partial','empty'}:
            if prior.get('input_sha256') != source_hash or prior.get('code_sha256') != code_hashes():
                raise ValueError('Existing output has different input/code; archive it before rerunning')
            if prior.get('document_sha256') != hashlib.sha256((work/'document.md').read_bytes()).hexdigest():
                raise ValueError('Existing document was modified')
            print('Skipped completed', source['id'], flush=True)
            return prior
        raise FileExistsError(f'{work} exists; archive it before retrying')
    work.mkdir(parents=True)
    model_sources=ROOT/'model_sources.json'
    cached=json.loads(model_sources.read_text()) if model_sources.is_file() else []
    precached=len(cached)==10 and all((ROOT/'cache/paddlex/official_models'/m['model']/'inference.pdiparams').is_file() for m in cached)
    record = dict(parser=PARSER, document=source['id'], input_sha256=source_hash, expected_pages=source['pages'],
                  status='started', started_at_utc=datetime.now(timezone.utc).isoformat(), platform=platform.platform(),
                  machine=platform.machine(), python=sys.version, code_sha256=code_hashes(), hosted_model_calls=0,
                  weights_precached=precached, model_sources_sha256=hashlib.sha256(model_sources.read_bytes()).hexdigest() if precached else None,
                  timing_note='Sequential full-document child process; includes Python/model startup, page rendering and native output persistence; excludes canonical export and evaluation. '+('Weights downloaded before timing. ' if precached else 'Any first-time weight downloads are included. ')+'Historical Sam timings are from a different host.')
    command = [sys.executable, str(ROOT/'paddle_worker.py'), str(pdf), str(work)]
    record['command'] = command
    dump(work/'run.json', record)
    started = time.perf_counter()
    try:
        with (work/'parser.log').open('w') as log:
            proc = subprocess.Popen(command, cwd=ROOT, env=environment(), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                raise TimeoutError(f'Exceeded {timeout}s; see parser.log')
            except BaseException:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=15)
                raise
        record['elapsed_seconds'] = round(time.perf_counter()-started, 3)
        if code:
            raise RuntimeError(f'PP-StructureV3 exited {code}; see {work}/parser.log')
        worker = json.loads((work/'worker.json').read_text())
        record.update(versions=worker['versions'], settings=dict(worker['settings'], render_dpi=worker['render_dpi'], markdown_ignore_labels=[]),
                      compatibility=worker['compatibility'],
                      model_files_sha256=worker['model_files_sha256'])
        chunks = json.loads((work/'raw_chunks.json').read_text())
        if len(chunks) != source['pages']:
            raise ValueError('Physical page coverage mismatch')
        pages = export_pages(work, chunks, source)
        nonempty = sum(p['text_chars'] > 0 for p in pages)
        record.update(status='success' if nonempty == len(pages) else ('partial' if nonempty else 'empty'),
                      parsed_pages=len(pages), nonempty_pages=nonempty, ocr_pages=list(range(1,len(pages)+1)),
                      document_sha256=hashlib.sha256((work/'document.md').read_bytes()).hexdigest(),
                      pages_per_second=round(len(pages)/record['elapsed_seconds'],4))
    except BaseException as exc:
        record.update(status='failed', error=repr(exc), elapsed_seconds=round(time.perf_counter()-started,3))
        dump(work/'run.json', record)
        raise
    dump(work/'run.json', record)
    print(source['id'], record['status'], record['parsed_pages'], record['elapsed_seconds'], flush=True)
    return record


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--document', default='all')
    cli.add_argument('--skip-existing', action='store_true')
    cli.add_argument('--timeout', type=int, default=14400)
    args = cli.parse_args()
    sources = json.loads((ROOT/'source_manifest.json').read_text())
    selected = [s for s in sources if args.document in {'all',s['id']}]
    if not selected or args.timeout < 1:
        cli.error('Unknown document or nonpositive timeout')
    for source in selected:
        run(source, ROOT/'inputs'/(source['id']+'.pdf'), ROOT/'results/parsed'/source['id']/PARSER,
            args.skip_existing, args.timeout)


if __name__ == '__main__':
    main()
