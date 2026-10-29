"""Shared paths and unmodified Sam adapters; parsing never loads labels."""
import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REFERENCE = ROOT / 'reference' / 'samhu'
PARSER = 'paddleocr_ppstructurev3'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dump(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + '\n')


def environment():
    env = os.environ.copy()
    for key, folder in {'PADDLE_PDX_CACHE_HOME': 'cache/paddlex', 'HF_HOME': 'cache/huggingface',
                        'XDG_CACHE_HOME': 'cache/xdg', 'MPLCONFIGDIR': 'cache/matplotlib',
                        'PADDLE_HOME': 'cache/paddle', 'TMPDIR': 'tmp'}.items():
        location = ROOT / folder
        location.mkdir(parents=True, exist_ok=True)
        env[key] = str(location)
    env.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
               TOKENIZERS_PARALLELISM='false', PYTHONUNBUFFERED='1',
               PADDLE_PDX_MODEL_SOURCE='huggingface', PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True',
               HF_HUB_DISABLE_XET='1')
    return env


def export_pages(work, chunks, source):
    # Use Sam's exact canonicalization, page numbering, metadata and confidence policy.
    adapter = load('sam_export', REFERENCE / '2026-09-29_sponsor_samples' / 'parse.py')
    return adapter.export_pages(work, chunks, source, PARSER)


def prediction_dir(document, parser, output_root=None):
    if output_root is not None:
        return Path(output_root) / document / parser
    if parser == PARSER:
        base = ROOT / 'results' / 'parsed'
    elif parser == 'pymupdf4llm_vlm':
        base = REFERENCE / '2026-10-05_pilot_benchmark' / 'results' / 'parsed'
    else:
        base = REFERENCE / '2026-09-29_sponsor_samples' / 'results'
    return base / document / parser


def scorer():
    import benchmark
    benchmark.ROOT = ROOT
    benchmark.SOURCE = ROOT
    benchmark.PARSERS = ('mineru_ocr', 'mineru_vlm', 'pymupdf4llm', 'pymupdf4llm_vlm', PARSER)
    benchmark.prediction_dir = prediction_dir
    return benchmark
