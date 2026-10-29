"""Same PP-StructureV3 inference, with durable checkpoints for requested pages."""
import argparse
import faulthandler
import hashlib
import importlib.metadata
import os
from pathlib import Path
import time

from common import environment
from paddle_worker import config, create_pipeline, model_manifest
from selected_support import atomic_dump, checkpoints, sha


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument('pdf',type=Path)
    cli.add_argument('work',type=Path)
    cli.add_argument('--pages',type=int,nargs='+',required=True)
    args=cli.parse_args()
    faulthandler.enable()
    faulthandler.dump_traceback_later(180,repeat=True)
    os.environ.update(environment())
    completed=checkpoints(args.work)
    requested=sorted(set(args.pages))
    missing=[i for i in requested if i not in completed]
    if not missing:
        print('All requested pages already checkpointed; no models loaded.',flush=True)
        return
    import pymupdf
    import numpy as np
    started=time.perf_counter()
    pipeline=create_pipeline()
    pipeline.export_paddlex_config_to_yaml(str(args.work/'selected_pipeline_config.yaml'))
    settings=dict(config(),render_dpi=300,markdown_ignore_labels=[])
    versions={p:importlib.metadata.version(p) for p in ('paddleocr','paddlex','paddlepaddle','pymupdf','numpy')}
    model_files=model_manifest()
    atomic_dump(args.work/'selected_worker.json',dict(settings=settings,versions=versions,
                model_files_sha256=model_files,requested_pages=requested,new_pages=missing))
    with pymupdf.open(args.pdf) as pdf:
        if not all(1 <= i <= len(pdf) for i in requested):
            raise ValueError('Requested page outside source PDF')
        for i in missing:
            print(f'Parsing requested physical page {i}/{len(pdf)}',flush=True)
            raw_path=args.work/'raw'/f'page_{i:03}.json'
            raw_md=args.work/'raw'/f'page_{i:03}.md'
            if raw_path.exists() or raw_md.exists():
                raise FileExistsError(f'Uncommitted native output exists; preserve and inspect it before retry: {raw_path}')
            page_started=time.perf_counter()
            # Identical rendering and predict call to the original paddle_worker.
            pix=pdf[i-1].get_pixmap(dpi=300,colorspace=pymupdf.csRGB,alpha=False)
            bgr=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)[:,:,::-1].copy()
            results=list(pipeline.predict(bgr,markdown_ignore_labels=[]))
            if len(results)!=1:
                raise ValueError(f'Expected one prediction for physical page {i}')
            result=results[0]
            native=result.json
            payload=native.get('res',native)
            atomic_dump(raw_path,native)
            data=result.markdown
            raw_markdown=data['markdown_texts']
            markdown=raw_markdown
            for name,image in data.get('markdown_images',{}).items():
                portable=f'images/page_{i:03}/'+Path(name).name
                target=args.work/portable
                if not target.resolve().is_relative_to(args.work.resolve()):
                    raise ValueError(f'Invalid image destination: {name}')
                target.parent.mkdir(parents=True,exist_ok=True)
                image.save(target)
                markdown=markdown.replace(name,portable)
            raw_md.write_text(raw_markdown)
            audit=dict(page=i,image_width=pix.width,image_height=pix.height,render_dpi=300,
                image_pixels_sha256=hashlib.sha256(pix.samples).hexdigest(),
                raw_prediction=str(raw_path.relative_to(args.work)),raw_sha256=sha(raw_path),
                blocks=len(payload.get('parsing_res_list',[])),tables=len(payload.get('table_res_list',[])),
                elapsed_seconds=round(time.perf_counter()-page_started,3))
            entry=dict(audit=audit,chunk=dict(text=markdown,native=dict(page_index=i-1,
                raw_prediction=audit['raw_prediction'],parsing_res_list=payload.get('parsing_res_list',[]))),
                raw_markdown_sha256=sha(raw_md),provenance='selected_page_worker')
            atomic_dump(args.work/'page_checkpoints'/f'page_{i:03}.json',entry)
            completed[i]=entry
            atomic_dump(args.work/'selected_progress.json',dict(completed_pages=len(completed),
                expected_pages=len(pdf),requested_pages=requested,completed_page_ids=sorted(completed),
                remaining_requested_pages=[n for n in requested if n not in completed]))
            print(f'Checkpointed physical page {i}: {audit["elapsed_seconds"]:.1f}s',flush=True)
    atomic_dump(args.work/'selected_timing.json',dict(elapsed_seconds=round(time.perf_counter()-started,3),new_pages=missing))
    faulthandler.cancel_dump_traceback_later()


if __name__=='__main__':
    main()
