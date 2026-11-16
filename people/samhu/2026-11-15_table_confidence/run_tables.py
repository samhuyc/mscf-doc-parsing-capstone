"""Shared detector -> fixed table crops -> independent native OCR evidence.

This is a development pilot. No quality predictor, financial-relevance classifier,
table structure validation, or correctness probabilities are fitted or inferred.
"""
import argparse
import importlib.metadata
import os
from pathlib import Path
import shutil
import subprocess
import time

from regions import NATIVE, assign_units, padded_box, pool_assignment, table_summary, deduplicate_tables
from core import digest, read, sha, sources, SPONSOR, write

ROOT = Path(__file__).resolve().parent
LAYOUT_NAME = 'PP-DocLayout_plus-L'
PADDLE_CONFIG = dict(text_detection_model_name='PP-OCRv5_mobile_det',
                     text_recognition_model_name='PP-OCRv5_mobile_rec',
                     use_doc_orientation_classify=False, use_doc_unwarping=False,
                     use_textline_orientation=False, device='cpu', cpu_threads=4,
                     enable_mkldnn=False, text_det_limit_side_len=1280,
                     text_det_limit_type='max', text_rec_score_thresh=0.0)


def environment():
    for key in ('PADDLE_PDX_CACHE_HOME', 'PADDLE_HOME', 'HF_HOME', 'XDG_CACHE_HOME', 'MPLCONFIGDIR'):
        path = ROOT / 'work/cache' / key.lower()
        path.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(path)
    os.environ.update(PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True',
                      TOKENIZERS_PARALLELISM='false', OMP_NUM_THREADS='2')


def file_manifest(folder):
    return {p.name: sha(p) for p in sorted(folder.iterdir())
            if p.suffix in ('.json', '.yml', '.pdiparams')}


def guard(path, data):
    if path.exists() and read(path) != data:
        raise ValueError(f'Provenance changed; use a new output directory: {path}')
    write(path, data)


def baseline(source, page_no, engine, regions, size):
    run = 'paddle_v2' if engine == 'paddle' else 'tesseract'
    path = NATIVE / 'runs' / run / source['id'] / f'page_{page_no:03}.json'
    settings_path = NATIVE / 'runs' / run / 'settings.json'
    if not path.exists():
        return [dict(status='missing', confidence=table_summary([])) for _ in regions]
    page = read(path)
    if page['source_sha256'] != source['sha256']:
        raise ValueError('Baseline source mismatch')
    if page['settings_sha256'] != digest(read(settings_path)):
        raise ValueError('Baseline settings mismatch')
    outputs = []
    for assigned in assign_units(page, regions, size):
        result = pool_assignment(assigned, engine)
        result.update(status=page['status'], source_record=str(path), source_record_sha256=sha(path),
                      source_settings=read(settings_path),
                      source_unit_indices=assigned['source_unit_indices'],
                      boundary_units=assigned['boundary_units'], ambiguous_units=assigned['ambiguous_units'])
        outputs.append(result)
    return outputs


def paddle_crop(model, bgr, verify=False):
    from paddlex.inference.models.text_recognition.processors import CTCLabelDecode
    from run_paddle import parse_result
    from score_probes import paddle_probe, attach_characters
    original = parse_result(list(model.predict(bgr))[0]) if verify else None
    started = time.monotonic()
    with paddle_probe(CTCLabelDecode) as evidence:
        lines = parse_result(list(model.predict(bgr))[0])
        units = attach_characters(lines, evidence)
    if original is not None:
        if [(u['text'], u['score']) for u in original] != [(u['text'], u['score']) for u in lines]:
            raise RuntimeError('Instrumentation changed Paddle output')
    return dict(status='success', text='\n'.join(u['text'] for u in lines), units=lines,
                confidence_units=units, confidence=table_summary(units),
                seconds=round(time.monotonic()-started, 3),
                hook_equivalence_checked=verify, hook_equivalence_passed=True if verify else None)


def tesseract_crop(path, dpi):
    from run_tesseract import parse_tsv
    binary = shutil.which('tesseract') or '/opt/homebrew/bin/tesseract'
    command = [binary, str(path), 'stdout', '--tessdata-dir', str(SPONSOR / 'cache/tessdata'),
               '-l', 'eng', '--psm', '3', '--dpi', str(dpi), '-c', 'tessedit_create_tsv=1']
    started = time.monotonic()
    output = subprocess.run(command, capture_output=True, text=True, check=True, timeout=180,
                            env={**os.environ, 'OMP_THREAD_LIMIT': '2'})
    units = parse_tsv(output.stdout)
    return dict(status='success', text='\n'.join(u['text'] for u in units), units=units,
                confidence_units=units, confidence=table_summary(units),
                seconds=round(time.monotonic()-started, 3))


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--selection', type=Path, default=ROOT / 'pilot.json')
    cli.add_argument('--output', type=Path, default=ROOT / 'runs/pilot_v2')
    cli.add_argument('--engines', nargs='+', choices=('paddle', 'tesseract'), default=['paddle', 'tesseract'])
    cli.add_argument('--dpi', type=int, default=200)
    cli.add_argument('--layout-threshold', type=float, default=0.5)
    cli.add_argument('--padding', type=float, default=0.02)
    args = cli.parse_args()
    if args.dpi <= 0 or not 0 <= args.layout_threshold <= 1 or not 0 <= args.padding <= 0.25:
        cli.error('Invalid DPI, threshold or padding')
    environment()
    import numpy as np
    import pymupdf
    from PIL import Image, ImageDraw
    from paddleocr import LayoutDetection, PaddleOCR

    selection = read(args.selection)
    detector_dir = ROOT / 'work/models' / LAYOUT_NAME
    detector_manifest = read(detector_dir / 'provenance.json')
    for name, info in detector_manifest['files'].items():
        if sha(detector_dir / name) != info['sha256']:
            raise ValueError(f'Layout model changed: {name}')
    ocr_dir = NATIVE / 'work/paddlex/official_models'
    settings = dict(schema_version=1, render_dpi=args.dpi,
                    layout=dict(name=LAYOUT_NAME, provenance=detector_manifest,
                                threshold=args.layout_threshold, nms=True, padding=args.padding,
                                nested_table_suppression='retain larger box at >= 95% containment'),
                    selection=selection, engines=args.engines, paddle=PADDLE_CONFIG,
                    paddle_models={name: file_manifest(ocr_dir / name) for name in
                                   ('PP-OCRv5_mobile_det', 'PP-OCRv5_mobile_rec')},
                    versions={k: importlib.metadata.version(k) for k in
                              ('paddlepaddle', 'paddleocr', 'paddlex', 'numpy', 'pymupdf', 'pillow')},
                    primary_summary='geometric_mean',
                    secondary_summaries=['mean', 'p10', 'fraction_below_0_90'],
                    baseline_assignment='maximum bbox overlap >= 0.5; exclusive line/word assignment',
                    financial_scope='All detected tables retained as candidates; financial relevance unreviewed',
                    completeness='Unverified. Missing tables cannot be identified by recognition confidence.')
    if 'tesseract' in args.engines:
        settings['tesseract'] = dict(version=subprocess.check_output(['tesseract', '--version'], text=True).splitlines()[0],
                                     psm=3, language='eng', render_dpi=args.dpi,
                                     tessdata_sha256=sha(SPONSOR / 'cache/tessdata/eng.traineddata'))
    guard(args.output / 'settings.json', settings)
    settings_hash = digest(settings)
    detector = LayoutDetection(model_name=LAYOUT_NAME, model_dir=str(detector_dir),
                               device='cpu', cpu_threads=4, enable_mkldnn=False)
    paddle = None
    if 'paddle' in args.engines:
        paddle = PaddleOCR(**PADDLE_CONFIG,
                           text_detection_model_dir=str(ocr_dir / 'PP-OCRv5_mobile_det'),
                           text_recognition_model_dir=str(ocr_dir / 'PP-OCRv5_mobile_rec'))
    inventory = {s['id']: s for s in sources()}
    pages, tables = [], []
    verified = False
    for document, selected_pages in selection['pages'].items():
        source = inventory[document]
        pdf_path = SPONSOR / 'inputs' / (document + '.pdf')
        if sha(pdf_path) != source['sha256']:
            raise ValueError('Source PDF changed')
        with pymupdf.open(pdf_path) as pdf:
            if len(set(selected_pages)) != len(selected_pages) or any(p < 1 or p > len(pdf) for p in selected_pages):
                raise ValueError('Invalid selected pages')
            for number in selected_pages:
                page_id = f'{document}_p{number:03}'
                folder = args.output / page_id
                folder.mkdir(parents=True, exist_ok=True)
                page = pdf[number - 1]
                pix = page.get_pixmap(dpi=args.dpi, colorspace=pymupdf.csRGB, alpha=False)
                image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                bgr = np.asarray(image)[:, :, ::-1].copy()
                page_record = dict(document=document, page=number, source_sha256=source['sha256'],
                                   settings_sha256=settings_hash, width=pix.width, height=pix.height)
                try:
                    cache = folder / 'layout.json'
                    if cache.exists():
                        layout = read(cache)
                        if layout['provenance'] != page_record:
                            raise ValueError('Cached layout provenance mismatch')
                    else:
                        start = time.monotonic()
                        predicted = list(detector.predict(bgr, batch_size=1, threshold=args.layout_threshold, layout_nms=True))
                        if len(predicted) != 1:
                            raise ValueError('Expected one layout result')
                        raw = predicted[0].json
                        raw = raw.get('res', raw)
                        layout = dict(provenance=page_record, prediction=raw,
                                      seconds=round(time.monotonic()-start, 3))
                        write(cache, layout)
                    regions = []
                    boxes, suppressed = deduplicate_tables([b for b in layout['prediction']['boxes'] if b['label'] == 'table'])
                    for i, box in enumerate(boxes, 1):
                        region = dict(table_id=f'{page_id}_t{i:02}', document=document, page=number,
                                      detector_bbox_px=box['coordinate'], layout_score=box['score'],
                                      bbox_px=padded_box(box['coordinate'], pix.width, pix.height, args.padding))
                        region['bbox_pdf'] = [region['bbox_px'][j] * (page.rect.width / pix.width if j % 2 == 0 else page.rect.height / pix.height)
                                              for j in range(4)]
                        regions.append(region)
                    preview = image.copy()
                    drawing = ImageDraw.Draw(preview)
                    for i, region in enumerate(regions, 1):
                        drawing.rectangle(region['bbox_px'], outline='#e4472e', width=4)
                        drawing.text((region['bbox_px'][0], max(0, region['bbox_px'][1]-22)), f'Table {i}', fill='#e4472e', font_size=20)
                    preview.thumbnail((1200, 1600))
                    preview.save(folder / 'page.png')
                    page_record.update(status='success', tables=len(regions), layout_seconds=layout['seconds'],
                                       overview=str((folder / 'page.png').relative_to(args.output)),
                                       suppressed_nested_detections=suppressed)
                except Exception as exc:
                    page_record.update(status='failed', tables=None, error=f'{type(exc).__name__}: {exc}')
                    pages.append(page_record)
                    write(folder / 'page.json', page_record)
                    print(page_id, page_record['error'], flush=True)
                    continue
                baselines = {e: baseline(source, number, e, regions, image.size) for e in args.engines}
                for index, region in enumerate(regions):
                    table_path = folder / (region['table_id'] + '.json')
                    crop_path = folder / (region['table_id'] + '.png')
                    crop = image.crop(region['bbox_px'])
                    crop.save(crop_path)
                    record = dict(**region, source_sha256=source['sha256'], settings_sha256=settings_hash,
                                  image=str(crop_path.relative_to(args.output)), image_sha256=sha(crop_path),
                                  financial_relevance='unreviewed', table_structure_correct=None,
                                  source_coverage_correct=None, models={})
                    prior = read(table_path) if table_path.exists() else None
                    if prior and any(prior[k] != record[k] for k in ('settings_sha256', 'image_sha256', 'source_sha256')):
                        raise ValueError('Cached table provenance mismatch')
                    for engine in args.engines:
                        if prior and prior['models'].get(engine, {}).get('crop', {}).get('status') == 'success':
                            output = prior['models'][engine]['crop']
                        else:
                            try:
                                if engine == 'paddle':
                                    output = paddle_crop(paddle, np.asarray(crop)[:, :, ::-1].copy(), verify=not verified)
                                else:
                                    output = tesseract_crop(crop_path, args.dpi)
                            except Exception as exc:
                                output = dict(status='failed', error=f'{type(exc).__name__}: {exc}', confidence=table_summary([]))
                        if engine == 'paddle' and output.get('hook_equivalence_passed'):
                            verified = True
                        flags = ['table_structure_unverified', 'crop_context_unverified']
                        if output['status'] != 'success':
                            flags.append('recognition_failed')
                        elif not output.get('text', '').strip():
                            flags.append('empty_recognition')
                        record['models'][engine] = dict(crop=output, full_page_region=baselines[engine][index], flags=flags)
                    write(table_path, record)
                    tables.append(record)
                    print(region['table_id'], {e: v['crop']['status'] for e, v in record['models'].items()}, flush=True)
                pages.append(page_record)
                write(folder / 'page.json', page_record)
                write(args.output / 'progress.json', dict(pages=pages, tables=len(tables)))
    write(args.output / 'tables.json', dict(settings=settings, pages=pages, tables=tables))
    from report import build
    build(args.output)
    failures = sum(p['status'] != 'success' for p in pages) + sum(
        m['crop']['status'] != 'success' for t in tables for m in t['models'].values())
    print(f'Finished: {len(pages)} pages, {len(tables)} table regions, {failures} failures. {args.output / "report.html"}', flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
