"""Run local parsers or import external predictions; never reads reference labels."""
import argparse
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

from formats import canonical, digest, read_jsonl, write_jsonl

ROOT = Path(__file__).resolve().parent


def mineru(source, work, args):
    env = os.environ.copy()
    for key, value in {'HF_HOME': 'cache/huggingface', 'XDG_CACHE_HOME': 'cache/xdg',
                       'MPLCONFIGDIR': 'cache/matplotlib', 'MINERU_API_OUTPUT_ROOT': 'tmp/api'}.items():
        env.setdefault(key, str(ROOT / value))
        Path(env[key]).mkdir(parents=True, exist_ok=True)
    config = ROOT / 'cache/mineru.json'
    config.parent.mkdir(exist_ok=True)
    if not config.exists():
        config.write_text(json.dumps({'config_version': '1.3.2', 'model-source': 'huggingface'}))
    env.update(MINERU_TOOLS_CONFIG_JSON=str(config), MINERU_MODEL_SOURCE='huggingface',
               MINERU_PROCESSING_WINDOW_SIZE='4', MINERU_API_MAX_CONCURRENT_REQUESTS='1',
               PYTORCH_ENABLE_MPS_FALLBACK='1', TOKENIZERS_PARALLELISM='false')
    if args.device:
        env['MINERU_DEVICE_MODE'] = args.device
    command = [args.mineru, '-p', str(source), '-o', str(work / 'raw'), '-b', args.backend,
               '-m', 'auto', '-f', 'false', '-t', 'true']
    if args.backend == 'vlm-engine':
        command += ['--image-analysis', 'false']
    with (work / 'parser.log').open('w') as log:
        proc = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = proc.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            raise TimeoutError('Parser timed out; see parser.log')
    files = list((work / 'raw').rglob('*.md'))
    middle = list((work / 'raw').rglob('*_middle.json'))
    if code or len(files) != 1 or not middle:
        raise RuntimeError('MinerU failed or output missing; see parser.log')
    if sum(len(json.loads(p.read_text())['pdf_info']) for p in middle) != 1:
        raise RuntimeError('Expected one parsed page')
    return files[0].read_text(), 'markdown', files[0].parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('--parser', choices=['mineru', 'pymupdf', 'import'], required=True)
    parser.add_argument('--backend', choices=['pipeline', 'vlm-engine'], default='pipeline')
    parser.add_argument('--mineru', default=shutil.which('mineru'))
    parser.add_argument('--device', choices=['cpu', 'mps', 'cuda'])
    parser.add_argument('--input-kind', choices=['image', 'image_pdf', 'native_pdf'], default='image_pdf')
    parser.add_argument('--name', required=True)
    parser.add_argument('--timeout', type=int, default=240)
    parser.add_argument('--predictions', help='Directory containing <sample-id>.md/.html/.txt')
    parser.add_argument('--format', choices=['markdown', 'html', 'text'], default='markdown')
    args = parser.parse_args()
    if not args.name.replace('-', '').replace('_', '').isalnum():
        parser.error('--name must contain only letters, numbers, hyphens and underscores')
    if args.parser == 'mineru' and not args.mineru:
        parser.error('Install MinerU separately or specify --mineru /path/to/mineru')
    if args.parser == 'import' and not args.predictions:
        parser.error('--predictions required for import')
    manifest = Path(args.manifest).resolve()
    samples = read_jsonl(manifest)
    destination = ROOT / 'outputs' / args.name
    destination.mkdir(parents=True, exist_ok=False)  # Never silently reuse stale predictions.
    version = pymupdf.VersionBind if args.parser == 'pymupdf' else None
    if args.parser == 'mineru':
        version = subprocess.check_output([args.mineru, '--version'], text=True).strip()
    metadata = dict(parser=args.parser, version=version, backend=args.backend if args.parser == 'mineru' else None,
                    input_kind=args.input_kind, device=args.device or 'auto', platform=platform.platform(),
                    manifest_sha256=digest(manifest), started_utc=datetime.now(timezone.utc).isoformat(),
                    config=dict(formulas=False, tables=True, image_analysis=False) if args.parser == 'mineru' else {},
                    note='Import runtime excludes original inference; PyMuPDF is native-text only, without OCR.')
    (destination / 'run.json').write_text(json.dumps(metadata, indent=2) + '\n')
    records = []
    for sample in samples:
        sid = sample['id']
        if not sid.replace('_', '').replace('-', '').isalnum():
            raise ValueError(f'Unsafe sample ID: {sid}')
        work = destination / sid
        work.mkdir()
        started = time.perf_counter()
        record = dict(id=sid, status='failed', input_kind=args.input_kind, elapsed_seconds=None)
        try:
            asset_base = None
            source = ROOT / sample[args.input_kind]
            expected = sample.get(args.input_kind + '_sha256')
            if expected and digest(source) != expected:
                raise ValueError('Input checksum mismatch')
            record['input_sha256'] = digest(source)
            if args.parser == 'mineru':
                content, fmt, asset_base = mineru(source, work, args)
            elif args.parser == 'pymupdf':
                with pymupdf.open(source) as document:
                    content = '\n\n'.join(page.get_text(sort=True) for page in document)
                fmt = 'text'
            else:
                suffix = {'markdown': '.md', 'html': '.html', 'text': '.txt'}[args.format]
                content = (Path(args.predictions) / (sid + suffix)).read_text()
                fmt = args.format
            (work / 'raw.txt').write_text(content)
            markdown = canonical(content, fmt)
            if asset_base:
                prefix = os.path.relpath(asset_base, work)
                markdown = re.sub(r'(!\[[^\]]*\]\()(images/[^)]+)(\))',
                                  lambda m: m[1] + prefix + '/' + m[2] + m[3], markdown)
            (work / 'document.md').write_text(markdown)
            record.update(status='success' if content.strip() else 'empty', format=fmt,
                          raw=str((work / 'raw.txt').relative_to(ROOT)),
                          markdown=str((work / 'document.md').relative_to(ROOT)))
        except Exception as error:
            record['error'] = str(error)
        record['elapsed_seconds'] = round(time.perf_counter() - started, 3) if args.parser != 'import' else None
        records.append(record)
        write_jsonl(destination / 'predictions.jsonl', records)
        print(sid, record['status'], record['elapsed_seconds'], flush=True)
    print(destination)


if __name__ == '__main__':
    main()
