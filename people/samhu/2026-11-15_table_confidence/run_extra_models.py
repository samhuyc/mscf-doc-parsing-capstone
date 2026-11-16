"""Run unchanged official small checkpoints on shared table crops with MLX."""
import argparse
import importlib.metadata
import os
from pathlib import Path
import resource
import time
import traceback
import tempfile

from regions import table_summary
from core import digest, read, sha, write
from extra_scores import LogitObserver, collect, classify_content

ROOT = Path(__file__).resolve().parent
PROMPTS = dict(paddle_vl='Table Recognition:', glm='Table Recognition:',
              monkey='This is the image of a table. Please output the table in html format.')


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('engine', choices=list(PROMPTS))
    cli.add_argument('--root', type=Path, default=ROOT / 'runs/pilot_v2')
    cli.add_argument('--limit', type=int)
    cli.add_argument('--report-every', type=int, default=0)
    args = cli.parse_args()
    os.environ.update(HF_HUB_OFFLINE='1', TOKENIZERS_PARALLELISM='false')
    import mlx.core as mx
    from mlx_vlm import stream_generate
    from mlx_vlm.utils import load_model, load_processor, StoppingCriteria
    from mlx_vlm.tokenizer_utils import load_tokenizer
    from mlx_vlm.prompt_utils import apply_chat_template
    from PIL import Image

    model_path = ROOT / 'work/extra-models' / args.engine
    provenance = read(model_path / 'download_provenance.json')
    policy = read(ROOT / 'extra_trial_policy.json')
    assert args.engine not in policy['excluded']
    assert sum(f['bytes'] for f in provenance['files']) < policy['checkpoint_byte_limit']
    for file in provenance['files']:
        assert sha(model_path / file['file']) == file['sha256'], file['file']
    bundle = read(args.root / 'tables.json')
    folder = args.root / 'extra' / args.engine
    generation = dict(max_tokens=4096, temperature=0.0, top_p=1.0, top_k=0,
                      repetition_penalty=None, presence_penalty=None, frequency_penalty=None)
    settings = dict(engine=args.engine, source_bundle_sha256=sha(args.root / 'tables.json'),
        model=provenance, checkpoint_bytes=sum(f['bytes'] for f in provenance['files']),
        prompt=PROMPTS[args.engine], generation=generation, quantization=None,
        versions={k:importlib.metadata.version(k) for k in ('mlx','mlx-vlm','transformers','pillow')},
        scope='Shared detected table crops; recognition component, not full publisher pipeline',
        score_capture='Passive identity logits_processor; FP32 normalization for reporting only',
        image_preprocessing='Pinned backend model-specific processor; no external crop resize',
        primary_summary='All emitted token geometric mean, including formatting; EOS excluded',
        backend_note='GLM MLX sanitizer omits auxiliary MTP layer 16; no checkpoint quantization')
    if args.engine == 'glm':
        settings['config_adapter'] = 'Remove redundant vision rope_parameters only after checking axial theta=10000 matches MLX hardcoded vision rotary implementation'
    if args.engine == 'monkey':
        settings['eos_token_ids'] = read(model_path / 'generation_config.json')['eos_token_id']
    if (folder / 'settings.json').exists() and read(folder / 'settings.json') != settings:
        raise ValueError('Settings changed; use a new output directory')
    write(folder / 'settings.json', settings)
    print('Loading', args.engine, flush=True)
    started = time.monotonic()
    mx.reset_peak_memory()
    config = read(model_path / 'config.json')
    if args.engine == 'glm':
        assert config['vision_config']['rope_parameters'] == dict(rope_theta=10000.0, rope_type='axial')
        adapted = read(model_path / 'config.json')
        del adapted['vision_config']['rope_parameters']
        with tempfile.TemporaryDirectory(prefix='glm-config-') as temp:
            prepared = Path(temp)
            for child in model_path.iterdir():
                if child.name != 'config.json':
                    (prepared / child.name).symlink_to(child.resolve())
            write(prepared / 'config.json', adapted)
            model = load_model(prepared)
    else:
        model = load_model(model_path)
    eos = config.get('eos_token_id', config.get('text_config',{}).get('eos_token_id'))
    if args.engine == 'monkey':
        eos = settings['eos_token_ids']
    if args.engine == 'paddle_vl':
        from mlx_vlm.models.paddleocr_vl.processing_paddleocr_vl import PaddleOCRVLProcessor
        processor = PaddleOCRVLProcessor.from_pretrained(model_path, trust_remote_code=False)
        processor.detokenizer = load_tokenizer(model_path, return_tokenizer=False)(processor.tokenizer)
        processor.tokenizer.stopping_criteria = StoppingCriteria(eos, processor.tokenizer)
    else:
        processor = load_processor(model_path, eos_token_ids=eos, trust_remote_code=False)
    prompt = apply_chat_template(processor, model.config, PROMPTS[args.engine], num_images=1)
    write(folder / 'load.json', dict(seconds=time.monotonic()-started,
        peak_mlx_gb=mx.get_peak_memory()/1e9, process_peak_rss_gb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9,
        rendered_prompt=prompt, processor_class=type(processor).__name__))
    verified, failures = False, 0
    for table_index, table in enumerate(bundle['tables'][:args.limit], 1):
        image_path = args.root / table['image']
        assert sha(image_path) == table['image_sha256']
        identity = dict(table_id=table['table_id'], image_sha256=table['image_sha256'],
                        source_sha256=table['source_sha256'], settings_sha256=digest(settings))
        output = folder / (table['table_id'] + '.json')
        if output.exists():
            old = read(output)
            assert all(old[k] == v for k,v in identity.items())
            if old['status'] == 'success':
                verified = verified or old.get('hook_equivalence_passed',False)
                continue
        image = Image.open(image_path).convert('RGB')
        record = dict(**identity)
        started = time.monotonic()
        try:
            control = None
            if not verified:
                control = collect(stream_generate(model, processor, prompt, image=[image], **generation))
                record['control_seconds'] = time.monotonic()-started
            mx.clear_cache()
            mx.reset_peak_memory()
            started = time.monotonic()
            observer = LogitObserver(mx, processor.tokenizer)
            result = collect(stream_generate(model, processor, prompt, image=[image],
                                            logits_processors=[observer], **generation), observer)
            if control is not None:
                assert all(control[k] == result[k] for k in ('text','token_ids','stop_reason')), 'Observer changed output'
                verified = True
            record.update(result)
            record.update(status='success', hook_equivalence_passed=True if control else None,
                          confidence=table_summary(result['confidence_units']),
                          content_only=classify_content(result['confidence_units'],processor.tokenizer))
        except Exception as exc:
            failures += 1
            traceback.print_exc()
            record.update(status='failed', error=f'{type(exc).__name__}: {exc}', confidence=table_summary([]))
        record.update(seconds=round(time.monotonic()-started,3),
                      process_peak_rss_gb=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1e9)
        write(output, record)
        if args.report_every > 0 and (table_index == 1 or table_index % args.report_every == 0):
            from report import build
            build(args.root)
        print(table['table_id'], record['status'], record.get('stop_reason'), record['seconds'],
              'MLX GB', record.get('peak_mlx_gb'), flush=True)
        mx.clear_cache()
    if args.report_every > 0:
        from report import build
        build(args.root)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
