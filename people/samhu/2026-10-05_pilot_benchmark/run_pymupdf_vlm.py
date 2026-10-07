"""Add PyMuPDF4LLM with a genuine local VLM OCR callback to the Oct 5 pilot.

Source PDFs and labels are never changed. Existing three pipelines are not rerun.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / '2026-09-29_sponsor_samples'
sys.path.insert(0, str(SOURCE))
from parse import dump, export_pages
import pymupdf

PARSER = 'pymupdf4llm_vlm'


class LocalRecognizer:
    def __init__(self, python, config, work):
        env = os.environ.copy()
        env.update(HF_HUB_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1', TOKENIZERS_PARALLELISM='false',
                   OMP_NUM_THREADS='4', MINERU_DEVICE_MODE='cpu', PYTHONUNBUFFERED='1')
        self.log = (work/'vlm_worker.log').open('w')
        self.proc = subprocess.Popen([str(python), str(ROOT/'vlm_ocr_worker.py'), '--model-config', str(config)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.log,
                                     text=True, bufsize=1, env=env)
        try:
            self.info = json.loads(self.wait('READY '))
        except BaseException:
            self.close()
            raise

    def wait(self, prefix):
        for line in self.proc.stdout:
            if line.startswith(prefix):
                return line[len(prefix):].strip()
            self.log.write(line)
            self.log.flush()
        raise RuntimeError('VLM worker stopped; see vlm_worker.log')

    def recognize(self, image, output):
        self.proc.stdin.write(json.dumps(dict(image=str(image), output=str(output)))+'\n')
        self.proc.stdin.flush()
        if self.wait('DONE ') != str(output):
            raise RuntimeError('Worker response mismatch')
        result = json.loads(output.read_text())
        if result['status'] != 'success':
            raise RuntimeError(result['error'])
        return result

    def close(self):
        if self.proc.poll() is None:
            self.proc.stdin.close()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.terminate()
                self.proc.wait(timeout=15)
        self.log.close()


def run(source, args):
    work = ROOT/'results/parsed'/source['id']/PARSER
    pdf = SOURCE/'inputs'/(source['id']+'.pdf')
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != source['sha256']:
        raise ValueError('Input hash mismatch')
    if work.exists():
        old = json.loads((work/'run.json').read_text()) if (work/'run.json').exists() else {}
        if args.skip_existing and old.get('status') == 'success' and old.get('input_sha256') == source['sha256']:
            if old.get('code_sha256') != code_hashes():
                raise ValueError('Existing output uses different code; archive before rerunning')
            print('Skipped', source['id'], flush=True)
            return old
        raise FileExistsError(f'{work} exists; archive before rerunning')
    work.mkdir(parents=True)
    (work/'ocr').mkdir()
    record = dict(parser=PARSER, document=source['id'], input_sha256=source['sha256'], expected_pages=source['pages'],
                  status='started', started_at_utc=datetime.now(timezone.utc).isoformat(), platform=platform.platform(),
                  versions={k:importlib.metadata.version(k) for k in ('pymupdf4llm','pymupdf','pymupdf-layout')},
                  code_sha256=code_hashes(),
                  settings=dict(ocr=True,force_ocr=False,ocr_engine='MinerU2.5-Pro VLM crop recognition',
                                detector='PP-OCRv6 detection only',layout=True,vlm=True,ocr_dpi=300,
                                ocr_language='eng',table_output='html',page_chunks=True,write_images=True,dpi=100),
                  timing_note='New sequential document run; includes worker startup, detector/VLM model loading and OCR, excludes canonical export/scoring. Historical pipelines were run on other dates; not a controlled speed comparison.')
    dump(work/'run.json',record)
    started = time.perf_counter()
    worker = None
    calls = []
    try:
        import pymupdf4llm
        from pymupdf4llm.ocr.exec_ocr_interface import exec_ocr_full
        pymupdf4llm.use_layout(True)

        def callback(page, dpi=300, **kwargs):
            nonlocal worker
            pno = page.number+1
            before = len(page.get_text().strip())
            raw = work/'ocr'/f'page_{pno:03}.json'
            call = dict(page=pno, text_chars_before=before, invoked=True, recognized_regions=0)

            def recognize(array):
                nonlocal worker
                if worker is None:
                    worker = LocalRecognizer(args.mineru_python,args.model_config,work)
                    record['vlm_backend'] = worker.info
                    dump(work/'run.json',record)
                image = work/'ocr'/f'page_{pno:03}.png'
                pymupdf.Pixmap(pymupdf.csRGB, array.shape[1], array.shape[0], array.tobytes(), False).save(image)
                result = worker.recognize(image,raw)
                image.unlink()  # reproducible source render; retain hash and all raw predictions
                call.update(recognized_regions=len(result['predictions']), elapsed_seconds=result['elapsed_seconds'],
                            raw_prediction=str(raw.relative_to(work)))
                return [(x['box'], x['text'], None) for x in result['predictions']]

            # Official helper culls good native text, replaces bad/old OCR, and
            # inserts recognized lines using detected coordinates and fallback font.
            exec_ocr_full(page, recognize, dpi=dpi, language='eng', keep_ocr_text=False)
            call['text_chars_after'] = len(page.get_text().strip())
            calls.append(call)
            dump(work/'ocr_pages.json',dict(engine=record['settings']['ocr_engine'], mode='automatic',pages=calls))
            print(source['id'], 'OCR page', pno, 'regions', call['recognized_regions'], flush=True)

        chunks = pymupdf4llm.to_markdown(str(pdf), page_chunks=True,write_images=True,
                   image_path=str(work/'images'),dpi=100,show_progress=False,use_ocr=True,force_ocr=False,
                   ocr_function=callback,ocr_language='eng',ocr_dpi=300,table_output='html')
        record['elapsed_seconds'] = round(time.perf_counter()-started,3)
        if len(chunks) != source['pages']:
            raise ValueError('Page count mismatch')
        dump(work/'raw_chunks.json',chunks)
        (work/'raw.md').write_text('\n\n'.join(c['text'] for c in chunks))
        dump(work/'ocr_pages.json',dict(engine=record['settings']['ocr_engine'],mode='automatic',pages=calls))
        pages = export_pages(work,[dict(text=c['text'],native={k:v for k,v in c.items() if k!='text'}) for c in chunks],source,PARSER)
        record.update(status='success',parsed_pages=len(pages),nonempty_pages=sum(p['text_chars']>0 for p in pages),
                      ocr_pages=[p['page'] for p in calls],vlm_pages=[p['page'] for p in calls if p['recognized_regions']],
                      recognized_regions=sum(p['recognized_regions'] for p in calls),
                      pages_per_second=round(len(pages)/record['elapsed_seconds'],4),
                      document_sha256=hashlib.sha256((work/'document.md').read_bytes()).hexdigest())
    except BaseException as exc:
        record.update(status='failed',error=repr(exc),elapsed_seconds=round(time.perf_counter()-started,3))
        raise
    finally:
        if worker:
            worker.close()
        dump(work/'run.json',record)
    print(source['id'], 'complete', record['elapsed_seconds'],flush=True)
    return record


def code_hashes():
    return {name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ('run_pymupdf_vlm.py','vlm_ocr_worker.py')}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--mineru-python',required=True,type=Path)
    ap.add_argument('--model-config',required=True,type=Path)
    ap.add_argument('--document',default='all')
    ap.add_argument('--skip-existing',action='store_true')
    args=ap.parse_args()
    args.mineru_python=args.mineru_python.absolute()
    args.model_config=args.model_config.resolve()
    sources=json.loads((SOURCE/'source_manifest.json').read_text())
    selected=[s for s in sources if args.document in ('all',s['id'])]
    if not selected:
        ap.error('Unknown document')
    for source in selected:
        run(source,args)

if __name__=='__main__':
    main()
