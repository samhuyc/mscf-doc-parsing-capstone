"""Common document/page contract for PyMuPDF4LLM and both MinerU backends.

No reference labels are read. Parser outputs are never repaired or summarized.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / '2026-09-20_evaluation'))
from formats import canonical, plain_text


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def block_md(item):
    kind = item.get('type')
    if kind == 'text':
        level = min(6, item.get('text_level', 0))
        return ('#' * level + ' ' if level else '') + item.get('text', '')
    if kind == 'table':
        return '\n\n'.join([*item.get('table_caption', []), item.get('table_body', ''), *item.get('table_footnote', [])])
    if kind in ('image', 'chart'):
        img = f"![Extracted image]({item['img_path']})" if item.get('img_path') else ''
        return '\n\n'.join([img, item.get('content', ''), *item.get(kind + '_caption', []), *item.get(kind + '_footnote', [])])
    if kind == 'list':
        return '\n'.join('- ' + str(x) for x in item.get('list_items', []))
    return item.get('text', '')


def export_pages(work, chunks, source, parser):
    pages = []
    toc = []
    for i, chunk in enumerate(chunks, 1):
        md = canonical(chunk['text'], 'markdown')
        # Absolute PyMuPDF image paths are made portable; MinerU paths already relative.
        md = md.replace(str(work) + '/', '')
        pages.append(dict(page=i, markdown=md, native=chunk.get('native'),
                          text_chars=len(plain_text(md)), confidence=None))
        for match in re.finditer(r'^(#{1,6})\s+(.+)$', md, re.M):
            toc.append(dict(page=i, level=len(match[1]), title=match[2], origin='parser_heading'))
    dump(work / 'pages.json', dict(schema_version=1, source_sha256=source['sha256'],
                                 parser=parser, page_numbering='1-based physical PDF pages', pages=pages))
    (work / 'document.md').write_text('\n\n'.join(f"<!-- source page {p['page']} -->\n\n{p['markdown']}" for p in pages))
    dump(work / 'metadata.json', dict(source=source, parser=parser, source_outline=source['outline'],
                                    generated_heading_index=toc, confidence=None,
                                    confidence_note='No calibrated document confidence is available. Native scores are not comparable across parsers.'))
    return pages


def pymupdf_worker(pdf, work):
    import pymupdf4llm
    chunks = pymupdf4llm.to_markdown(str(pdf), page_chunks=True, write_images=True,
                                   image_path=str(work / 'images'), dpi=100, show_progress=False)
    if not isinstance(chunks, list):
        raise ValueError('Expected page_chunks output')
    dump(work / 'raw_chunks.json', chunks)
    (work / 'raw.md').write_text('\n\n'.join(c['text'] for c in chunks))


def subprocess_run(command, env, log_path, timeout):
    with log_path.open('w') as log:
        proc = subprocess.Popen(command, cwd=log_path.parent, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
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
    if code:
        raise RuntimeError(f'Parser exited {code}; see parser.log')


def parse_one(source, args):
    pdf = ROOT / 'inputs' / (source['id'] + '.pdf')
    work = ROOT / 'results' / source['id'] / args.parser
    if work.exists():
        if args.skip_existing and (work / 'run.json').exists():
            prior = json.loads((work / 'run.json').read_text())
            if prior.get('status') in ('success', 'partial', 'empty') and prior.get('input_sha256') == source['sha256']:
                print('Skipping completed', work, flush=True)
                return prior
        raise FileExistsError(f'{work} exists; archive it before rerunning')
    work.mkdir(parents=True)
    record = dict(parser=args.parser, document=source['id'], input_sha256=source['sha256'],
                  expected_pages=source['pages'], status='started', started_at_utc=datetime.now(timezone.utc).isoformat(),
                  platform=platform.platform(), machine=platform.machine(), python=sys.version,
                  timing_note='Single sequential full-document run; wall time includes child process startup and model loading, excludes download/export/scoring; cached MinerU weights.')
    dump(work / 'run.json', record)
    started = None
    try:
        if hashlib.sha256(pdf.read_bytes()).hexdigest() != source['sha256']:
            raise ValueError('Input hash mismatch')
        env = os.environ.copy()
        if args.parser == 'pymupdf4llm':
            command = [sys.executable, str(Path(__file__).resolve()), '--worker', str(pdf), str(work)]
            record['versions'] = {p: importlib.metadata.version(p) for p in ('pymupdf4llm', 'pymupdf')}
            record['settings'] = dict(ocr=False, page_chunks=True, write_images=True, dpi=100, table_strategy='lines_strict')
        else:
            if not args.mineru or not args.model_config:
                raise ValueError('--mineru and --model-config required')
            backend = 'pipeline' if args.parser == 'mineru_ocr' else 'vlm-engine'
            for key, value in {'XDG_CACHE_HOME':'cache/xdg', 'MPLCONFIGDIR':'cache/matplotlib', 'TMPDIR':'tmp', 'MINERU_API_OUTPUT_ROOT':'tmp/api'}.items():
                location = ROOT / value
                location.mkdir(parents=True, exist_ok=True)
                env[key] = str(location)
            env.update(MINERU_TOOLS_CONFIG_JSON=str(Path(args.model_config).resolve()), MINERU_MODEL_SOURCE='local',
                       MINERU_PROCESSING_WINDOW_SIZE='4', MINERU_API_MAX_CONCURRENT_REQUESTS='1',
                       MINERU_INTRA_OP_NUM_THREADS='4', MINERU_INTER_OP_NUM_THREADS='1', OMP_NUM_THREADS='4',
                       PYTORCH_ENABLE_MPS_FALLBACK='1', TOKENIZERS_PARALLELISM='false', PYTHONUNBUFFERED='1',
                       HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1')
            if backend == 'pipeline':
                env['MINERU_DEVICE_MODE'] = 'cpu'
            command = [str(Path(args.mineru).resolve()), '-p', str(pdf), '-o', str(work / 'raw'), '-b', backend,
                       '-m', 'ocr', '-f', 'false', '-t', 'true']
            if backend == 'vlm-engine':
                command += ['--image-analysis', 'false']
            record['settings'] = dict(backend=backend, method='ocr' if backend == 'pipeline' else 'vlm',
                                      device='cpu' if backend == 'pipeline' else 'auto (MLX on Apple Silicon)',
                                      formulas=False, tables=True, image_analysis=False)
            record['versions'] = dict(mineru=subprocess.check_output([args.mineru, '--version'], text=True).strip())
            record['model_config'] = json.loads(Path(args.model_config).read_text())
        record['command'] = command
        dump(work / 'run.json', record)
        started = time.perf_counter()
        subprocess_run(command, env, work / 'parser.log', args.timeout)
        record['elapsed_seconds'] = round(time.perf_counter() - started, 3)
        if args.parser == 'pymupdf4llm':
            raw = json.loads((work / 'raw_chunks.json').read_text())
            chunks = [dict(text=c['text'], native={k:v for k,v in c.items() if k != 'text'}) for c in raw]
        else:
            middle = list((work / 'raw').rglob('*_middle.json'))
            lists = list((work / 'raw').rglob('*_content_list.json'))
            if len(middle) != 1 or len(lists) != 1:
                raise ValueError('Expected one middle.json and content_list.json')
            info = json.loads(middle[0].read_text())['pdf_info']
            if len(info) != source['pages']:
                raise ValueError('MinerU page count mismatch')
            items = json.loads(lists[0].read_text())
            if any(not 0 <= x.get('page_idx', -1) < len(info) for x in items):
                raise ValueError('Invalid MinerU page index')
            shutil.copy2(lists[0], work / 'raw_content_list.json')
            native_md = list(lists[0].parent.glob('*.md'))
            if len(native_md) != 1:
                raise ValueError('Missing raw Markdown')
            shutil.copy2(native_md[0], work / 'raw.md')
            if (lists[0].parent / 'images').exists():
                shutil.copytree(lists[0].parent / 'images', work / 'images')
            chunks = [dict(text='\n\n'.join(block_md(x) for x in items if x['page_idx'] == i),
                           native=dict(page_idx=i)) for i in range(len(info))]
        if len(chunks) != source['pages']:
            raise ValueError('Page count mismatch')
        pages = export_pages(work, chunks, source, args.parser)
        nonempty = sum(p['text_chars'] > 0 for p in pages)
        record.update(status='success' if nonempty == len(pages) else ('empty' if not nonempty else 'partial'),
                      parsed_pages=len(pages), nonempty_pages=nonempty, pages_per_second=round(len(pages) / record['elapsed_seconds'], 4),
                      document_sha256=hashlib.sha256((work / 'document.md').read_bytes()).hexdigest())
    except Exception as error:
        record.update(status='failed', error=str(error))
        if started is not None and 'elapsed_seconds' not in record:
            record['elapsed_seconds'] = round(time.perf_counter() - started, 3)
    dump(work / 'run.json', record)
    print(source['id'], args.parser, record['status'], record.get('elapsed_seconds'), record.get('error', ''), flush=True)
    return record


def main():
    if len(sys.argv) == 4 and sys.argv[1] == '--worker':
        pymupdf_worker(Path(sys.argv[2]), Path(sys.argv[3]))
        return
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parser', choices=['pymupdf4llm', 'mineru_ocr', 'mineru_vlm'], required=True)
    p.add_argument('--document', default='all')
    p.add_argument('--mineru')
    p.add_argument('--model-config')
    p.add_argument('--timeout', type=int, default=14400)
    p.add_argument('--skip-existing', action='store_true')
    args = p.parse_args()
    if args.timeout <= 0:
        p.error('--timeout must be positive')
    sources = json.loads((ROOT / 'source_manifest.json').read_text())
    selected = [s for s in sources if args.document in ('all', s['id'])]
    if not selected:
        p.error('Unknown document')
    results = [parse_one(s, args) for s in selected if s['status'] == 'success']
    if len(results) != len(selected) or any(r['status'] == 'failed' for r in results):
        raise SystemExit(1)

if __name__ == '__main__':
    main()
