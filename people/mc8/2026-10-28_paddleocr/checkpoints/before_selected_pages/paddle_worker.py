"""Image-only PP-StructureV3 inference. No references or other parser outputs read."""
import argparse
import faulthandler
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import time

from common import dump, environment


def config():
    return dict(device='cpu', cpu_threads=4, enable_mkldnn=False,
                text_detection_model_name='PP-OCRv5_mobile_det',
                text_recognition_model_name='PP-OCRv5_mobile_rec',
                text_det_limit_side_len=1280, text_det_limit_type='max',
                use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_textline_orientation=False, use_table_recognition=True,
                use_formula_recognition=False, use_seal_recognition=False,
                use_chart_recognition=False)


def model_manifest():
    from common import ROOT
    base = ROOT / 'cache' / 'paddlex' / 'official_models'
    return {str(p.relative_to(base)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(base.rglob('*')) if p.is_file() and p.suffix in {'.json', '.yml', '.yaml', '.pdiparams'}}


def create_pipeline():
    from paddleocr import PPStructureV3
    from paddlex.inference import load_pipeline_config
    from paddlex.inference.pipelines.layout_parsing.pipeline_v2 import _LayoutParsingPipelineV2
    pipeline_config = load_pipeline_config('PP-StructureV3')
    pipeline_config['markdown_ignore_labels'] = []
    # The table recognizer lazily creates its own OCR pipeline. Keep the same
    # declared orientation policy there as in the main OCR pipeline.
    pipeline_config['SubPipelines']['TableRecognition']['SubPipelines']['GeneralOCR']['use_textline_orientation'] = False
    # PaddleX 3.3.13 unconditionally creates the 1.4 GB Chart2Table model even
    # when chart recognition is disabled. Skip only that unused initializer.
    # All layout/OCR/table create_model calls still use PaddleX's real factory.
    original = _LayoutParsingPipelineV2.create_model

    def enabled_model(self, model_config, *args, **kwargs):
        if model_config.get('module_name') == 'chart_recognition' and not self.use_chart_recognition:
            print('Skipping disabled chart-recognition initializer (PaddleX compatibility fix)',flush=True)
            return None
        return original(self, model_config, *args, **kwargs)

    _LayoutParsingPipelineV2.create_model = enabled_model
    try:
        return PPStructureV3(paddlex_config=pipeline_config, **config())
    finally:
        _LayoutParsingPipelineV2.create_model = original


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('pdf', type=Path)
    cli.add_argument('work', type=Path)
    cli.add_argument('--dpi', type=int, default=300)
    args = cli.parse_args()
    faulthandler.enable()
    faulthandler.dump_traceback_later(180, repeat=True)
    os.environ.update(environment())
    print('Loading PaddleOCR and PaddlePaddle',flush=True)
    import pymupdf

    started = time.perf_counter()
    pipeline = create_pipeline()
    pipeline.export_paddlex_config_to_yaml(str(args.work/'pipeline_config.yaml'))
    dump(args.work / 'pipeline_config.json', config())
    versions = {p: importlib.metadata.version(p) for p in ('paddleocr', 'paddlex', 'paddlepaddle', 'pymupdf', 'numpy')}
    audit, chunks = [], []
    with pymupdf.open(args.pdf) as pdf:
        for i, page in enumerate(pdf, 1):
            print(f'Parsing physical page {i}/{len(pdf)}',flush=True)
            page_started = time.perf_counter()
            # Every page goes through the same OCR/layout/table models, including digital PDFs.
            # PyMuPDF only renders pixels here; native text is never a prediction source.
            pix = page.get_pixmap(dpi=args.dpi, colorspace=pymupdf.csRGB, alpha=False)
            import numpy as np
            bgr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)[:, :, ::-1].copy()
            # Sam retains notes, headers and footers. Paddle's default Markdown filter
            # would drop them, so retain all recognized block classes before export.
            results = list(pipeline.predict(bgr, markdown_ignore_labels=[]))
            if len(results) != 1:
                raise ValueError(f'Expected exactly one result for physical page {i}')
            result = results[0]
            native = result.json
            payload = native.get('res', native)
            raw_path = args.work / 'raw' / f'page_{i:03}.json'
            dump(raw_path, native)
            markdown_data = result.markdown
            raw_markdown = markdown_data['markdown_texts']
            markdown = raw_markdown
            # Keep the untouched native Markdown and all figure crops as produced by Paddle.
            for name, image in markdown_data.get('markdown_images', {}).items():
                portable = f'images/page_{i:03}/' + Path(name).name
                target = args.work / portable
                if not target.resolve().is_relative_to(args.work.resolve()):
                    raise ValueError(f'Invalid Paddle image destination: {name}')
                target.parent.mkdir(parents=True, exist_ok=True)
                image.save(target)
                markdown = markdown.replace(name, portable)
            raw_md = args.work / 'raw' / f'page_{i:03}.md'
            raw_md.write_text(raw_markdown)
            chunks.append(dict(text=markdown, native=dict(page_index=i-1, raw_prediction=str(raw_path.relative_to(args.work)),
                                                         parsing_res_list=payload.get('parsing_res_list', []))))
            record = dict(page=i, image_width=pix.width, image_height=pix.height, render_dpi=args.dpi,
                          image_pixels_sha256=hashlib.sha256(pix.samples).hexdigest(),
                          raw_prediction=str(raw_path.relative_to(args.work)), raw_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                          blocks=len(payload.get('parsing_res_list', [])), tables=len(payload.get('table_res_list', [])),
                          elapsed_seconds=round(time.perf_counter()-page_started, 3))
            audit.append(record)
            dump(args.work / 'progress.json', dict(completed_pages=len(audit), expected_pages=len(pdf), pages=audit))
            print(f'page {i}/{len(pdf)}: {record["blocks"]} blocks, {record["tables"]} tables, {record["elapsed_seconds"]:.1f}s', flush=True)
    dump(args.work / 'raw_chunks.json', chunks)
    (args.work / 'raw.md').write_text('\n\n'.join(c['text'] for c in chunks))
    dump(args.work / 'ocr_pages.json', dict(engine='PaddleOCR PP-StructureV3', mode='forced all-page image parsing', pages=audit))
    dump(args.work / 'worker.json', dict(versions=versions, settings=config(), render_dpi=args.dpi,
                                       compatibility='Skip unused Chart2Table initialization when use_chart_recognition=False; real layout/OCR/table predictors unchanged.',
                                       model_files_sha256=model_manifest(), elapsed_seconds=round(time.perf_counter()-started, 3)))
    faulthandler.cancel_dump_traceback_later()


if __name__ == '__main__':
    main()
