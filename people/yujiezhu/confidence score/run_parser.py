"""Run a frozen MinerU CPU baseline, retaining full outputs and failure records."""
import argparse
import importlib.metadata
import os
import platform
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from prepare import ROOT, read_json, sha256, write_json


def parser_environment():
    env = os.environ.copy()
    for key, directory in {
        'HF_HOME': 'huggingface', 'XDG_CACHE_HOME': 'cache', 'TORCH_HOME': 'torch',
        'MPLCONFIGDIR': 'matplotlib', 'YOLO_CONFIG_DIR': 'yolo', 'TMPDIR': 'tmp',
    }.items():
        path = ROOT / 'artifacts' / directory
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    env.update(MINERU_DEVICE_MODE='cpu', MINERU_MODEL_SOURCE='huggingface',
               MINERU_TOOLS_CONFIG_JSON=str(ROOT / 'artifacts' / 'mineru.json'),
               MINERU_MIN_BATCH_INFERENCE_SIZE='4',
               TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='4',
               MKL_NUM_THREADS='4', HF_HUB_DISABLE_XET='1',
               HF_HUB_DISABLE_TELEMETRY='1', DO_NOT_TRACK='1')
    write_json(ROOT / 'artifacts' / 'mineru.json', {'config_version': '1.3.2'})
    return env


def verify_source(record):
    for key in ('pdf', 'schema'):
        item = record['files'][key]
        if sha256(ROOT / item['path']) != item['sha256']:
            raise ValueError(f"Changed {key} for {record['local_id']}")


def run_one(record, run_root, timeout):
    verify_source(record)
    output = run_root / record['local_id']
    status_path = output / 'run.json'
    if status_path.exists():
        previous = read_json(status_path)
        if previous['status'] == 'success':
            for item in previous['outputs']:
                if sha256(ROOT / item['path']) != item['sha256']:
                    raise ValueError('Existing parser artifact changed')
            print(record['local_id'], 'already complete', flush=True)
            return
        raise ValueError(f"Existing unfinished/failed run: {status_path}; use a new --run name.")
    output.mkdir(parents=True, exist_ok=True)
    command = [str(Path(sys.executable).parent / 'mineru'),
               '-p', str(ROOT / record['files']['pdf']['path']),
               '-o', str(output / 'parsed'), '-b', 'pipeline', '-m', 'auto',
               '-f', 'false', '-t', 'true', '-l', 'ch_lite']
    meta = {'id': record['id'], 'local_id': record['local_id'],
            'source_sha256': record['files']['pdf']['sha256'],
            'expected_pages': record['pages'], 'status': 'running',
            'started_utc': datetime.now(timezone.utc).isoformat(),
            'parser': 'mineru', 'version': importlib.metadata.version('mineru'),
            'backend': 'pipeline', 'device': 'cpu', 'language': 'ch_lite', 'formula': False, 'tables': True,
            'batch_pages': 4, 'omp_threads': 4,
            'python': sys.version, 'platform': platform.platform(),
            'timeout_seconds': timeout, 'command': command,
            'timing_scope': 'CLI wall time including initialization and uncached model downloads'}
    write_json(status_path, meta)
    print(record['local_id'], 'started', record['pages'], 'pages', flush=True)
    started = time.monotonic()
    try:
        with (output / 'mineru.log').open('w') as log:
            process = subprocess.Popen(command, cwd=ROOT, env=parser_environment(),
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, KeyboardInterrupt):
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise
        meta['return_code'] = code
        markdown = list((output / 'parsed').rglob('*.md'))
        middle = list((output / 'parsed').rglob('*_middle.json'))
        if code or len(markdown) != 1 or len(middle) != 1:
            raise RuntimeError('MinerU did not produce exactly one Markdown and middle JSON; inspect mineru.log')
        pages = read_json(middle[0])['pdf_info']
        indices = [page['page_idx'] for page in pages]
        if sorted(indices) != list(range(record['pages'])):
            meta['status'] = 'partial'
            raise RuntimeError('Parsed page indices do not match all source pages')
        if not markdown[0].read_text().strip():
            meta['status'] = 'empty'
            raise RuntimeError('Empty Markdown')
        outputs = [p for p in (output / 'parsed').rglob('*') if p.is_file()]
        meta.update(status='success', parsed_pages=len(pages),
                    markdown=str(markdown[0].relative_to(ROOT)),
                    middle=str(middle[0].relative_to(ROOT)),
                    outputs=[{'path': str(p.relative_to(ROOT)), 'sha256': sha256(p)} for p in outputs])
    except subprocess.TimeoutExpired:
        meta.update(status='timeout', error='Parser exceeded per-document timeout')
    except KeyboardInterrupt:
        meta.update(status='interrupted', error='User interrupted parser')
        raise
    except Exception as error:
        if meta['status'] == 'running':
            meta['status'] = 'failed'
        meta['error'] = str(error)
    finally:
        meta['runtime_seconds'] = round(time.monotonic() - started, 3)
        meta['finished_utc'] = datetime.now(timezone.utc).isoformat()
        write_json(status_path, meta)
        print(record['local_id'], meta['status'], meta['runtime_seconds'], 'seconds', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', nargs='+', help='Local document IDs, default all nine')
    parser.add_argument('--run', default='mineru_cpu_v1')
    parser.add_argument('--timeout', type=int, default=1800)
    args = parser.parse_args()
    if args.timeout <= 0 or Path(args.run).name != args.run:
        parser.error('Use a positive timeout and a simple run directory name')
    manifest = read_json(ROOT / 'manifest.json')
    if args.only and set(args.only) - {r['local_id'] for r in manifest}:
        parser.error('Unknown document ID')
    run_root = ROOT / 'runs' / args.run
    run_root.mkdir(parents=True, exist_ok=True)
    write_json(run_root / 'environment.json', {
        'manifest_sha256': sha256(ROOT / 'manifest.json'),
        'packages': {d.metadata['Name']: d.version for d in importlib.metadata.distributions()},
        'runner_sha256': sha256(Path(__file__)),
    })
    for record in manifest:
        if not args.only or record['local_id'] in args.only:
            run_one(record, run_root, args.timeout)


if __name__ == '__main__':
    main()
