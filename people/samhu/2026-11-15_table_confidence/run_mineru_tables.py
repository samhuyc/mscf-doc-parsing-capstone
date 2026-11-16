"""Add MinerU native token evidence to the same immutable table crops.

Run separately so its MLX dependencies and memory use do not affect Paddle.
"""
import argparse
from collections import Counter
import importlib
import importlib.metadata
import os
from pathlib import Path
import tempfile
import time

from regions import NATIVE, table_summary
from core import digest, read, sha, write

ROOT = Path(__file__).resolve().parent


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--root', type=Path, default=ROOT / 'runs/pilot_v2')
    cli.add_argument('--model', type=Path, default=NATIVE / 'work/mineru-model')
    cli.add_argument('--table-ids', nargs='+')
    cli.add_argument('--report-every', type=int, default=1)
    args = cli.parse_args()
    os.environ.update(HF_HUB_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
    import mlx.core as mx
    from mlx_vlm import load, stream_generate
    from PIL import Image
    from safetensors import safe_open
    from run_mineru import collect_stream
    from score_probes import mineru_probe
    from report import build

    bundle = read(args.root / 'tables.json')
    selected = [t for t in bundle['tables'] if not args.table_ids or t['table_id'] in args.table_ids]
    if not selected or (args.table_ids and set(args.table_ids) != {t['table_id'] for t in selected}):
        cli.error('No tables or unknown table IDs')
    folder = args.root / 'mineru'
    settings = dict(engine='mineru', source_bundle_sha256=sha(args.root / 'tables.json'),
                    weight_sha256=sha(args.model / 'model.safetensors'),
                    config_sha256=sha(args.model / 'config.json'),
                    prompt='\nText Recognition:', temperature=0.0, max_tokens=4096,
                    max_image_side=1536, probability_normalization='original logits -> FP32 log-softmax',
                    hook_equivalence_check='first newly processed table, uninstrumented vs instrumented text and token IDs',
                    versions={k: importlib.metadata.version(k) for k in ('mlx', 'mlx-vlm', 'mlx-lm', 'transformers', 'torch', 'pillow')},
                    scope='Shared detected table crops; recognition component, not original MinerU end-to-end pipeline',
                    primary_summary='geometric_mean')
    previous = folder / 'settings.json'
    if previous.exists() and read(previous) != settings:
        raise ValueError('MinerU settings changed; use a new output directory')
    write(previous, settings)
    config = read(args.model / 'config.json')
    module = importlib.import_module('mlx_vlm.generate')
    failed = 0
    verified = False
    with tempfile.TemporaryDirectory(prefix='table-mineru-') as temp:
        prepared = Path(temp)
        with safe_open(args.model / 'model.safetensors', framework='numpy') as weights:
            has_head = any(k in weights.keys() for k in ('lm_head.weight', 'language_model.lm_head.weight'))
        if config.get('model_type') == 'qwen2_vl' and not has_head:
            config.update(config.get('text_config', {}))
        for child in args.model.iterdir():
            if child.name != 'config.json':
                (prepared / child.name).symlink_to(child.resolve())
        write(prepared / 'config.json', config)
        print('Loading existing local MinerU weights', flush=True)
        model, processor = load(str(prepared), use_fast=True)
        tokenizer = processor.tokenizer
        prompt = processor.apply_chat_template([{'role':'user', 'content':[
            {'type':'image'}, {'type':'text', 'text':settings['prompt']}]}], tokenize=False, add_generation_prompt=True)
        for table_index, table in enumerate(selected, 1):
            output = folder / (table['table_id'] + '.json')
            image_path = args.root / table['image']
            if sha(image_path) != table['image_sha256']:
                raise ValueError('Shared crop changed')
            provenance = dict(table_id=table['table_id'], image_sha256=table['image_sha256'],
                              source_sha256=table['source_sha256'], settings_sha256=digest(settings))
            if output.exists():
                prior = read(output)
                if any(prior[k] != v for k, v in provenance.items()):
                    raise ValueError('Cached MinerU provenance mismatch')
                if prior['status'] == 'success':
                    verified = verified or prior.get('hook_equivalence_passed', False)
                    continue
            started = time.monotonic()
            record = dict(**provenance)
            try:
                image = Image.open(image_path).convert('RGB')
                image.thumbnail((1536, 1536), Image.Resampling.LANCZOS)
                control = None
                if not verified:
                    control_start = time.monotonic()
                    control_stream = stream_generate(model, processor, prompt, image=[image], max_tokens=4096, temperature=0.0)
                    control = collect_stream(control_stream, tokenizer, mx)
                    record['hook_equivalence_control_seconds'] = round(time.monotonic()-control_start, 3)
                    started = time.monotonic()
                with mineru_probe(module, mx, tokenizer) as evidence:
                    stream = stream_generate(model, processor, prompt, image=[image], max_tokens=4096, temperature=0.0)
                    text, tokens, stopped = collect_stream(stream, tokenizer, mx, evidence)
                if control is not None:
                    if (text, [t['token_id'] for t in tokens], stopped) != (control[0], [t['token_id'] for t in control[1]], control[2]):
                        raise RuntimeError('Instrumentation changed MinerU output')
                    verified = True
                record['hook_equivalence_passed'] = True if control is not None else None
                counts = Counter(line.strip() for line in text.splitlines() if len(line.strip()) >= 12)
                repeated = [dict(text=line, count=count) for line, count in counts.items() if count >= 10]
                record.update(status='success', text=text, confidence_units=tokens,
                              confidence=table_summary(tokens), truncated=not stopped,
                              stop_reason='eos' if stopped else 'token_limit',
                              repetition_flag=bool(repeated), repeated_lines=repeated,
                              input_width=image.width, input_height=image.height)
            except Exception as exc:
                failed += 1
                record.update(status='failed', error=f'{type(exc).__name__}: {exc}', confidence=table_summary([]))
            record['seconds'] = round(time.monotonic()-started, 3)
            write(output, record)
            if args.report_every > 0 and (table_index == 1 or table_index % args.report_every == 0):
                build(args.root)
            print(table['table_id'], record['status'], record.get('stop_reason'), record['seconds'], record.get('error',''), flush=True)
            mx.clear_cache()
    build(args.root)
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
