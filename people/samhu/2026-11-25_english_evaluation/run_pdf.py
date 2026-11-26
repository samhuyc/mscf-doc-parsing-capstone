"""Replay a single English PDF with one of the two page-parser configurations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
from importlib.metadata import version

def baseline(pdf):
    import pymupdf4llm
    from pymupdf4llm.ocr import tesseract_api
    pymupdf4llm.use_layout(True)
    pages=pymupdf4llm.to_markdown(str(pdf),page_chunks=True,write_images=False,use_ocr=True,
        force_ocr=False,ocr_language='eng',ocr_dpi=300,ocr_function=tesseract_api.exec_ocr,table_output='html')
    return '\n\n'.join(p['text'] for p in pages),version('pymupdf4llm')

def mineru(pdf,weights,settings):
    if not weights or not settings:raise ValueError('Supply --weights and --mineru-config for MinerU.')
    with tempfile.TemporaryDirectory() as work:
        root=Path(work)
        config=json.loads(settings.read_text())
        config.setdefault('models-dir',{})['vlm']=str(weights.resolve())
        local_config=root/'mineru.json'
        local_config.write_text(json.dumps(config))
        os.environ.update(MINERU_DEVICE_MODE='cpu',MINERU_MODEL_SOURCE='local',HF_HUB_OFFLINE='1',
            TRANSFORMERS_OFFLINE='1',MINERU_TOOLS_CONFIG_JSON=str(local_config),MINERU_PROCESSING_WINDOW_SIZE='1',
            TOKENIZERS_PARALLELISM='false',MINERU_INTRA_OP_NUM_THREADS='2',MINERU_INTER_OP_NUM_THREADS='1')
        import torch
        from transformers import Qwen2VLForConditionalGeneration
        torch.set_num_threads(5)
        load=Qwen2VLForConditionalGeneration.from_pretrained
        def fp32(*args,**kwargs):
            kwargs['dtype']=torch.float32
            return load(*args,**kwargs)
        Qwen2VLForConditionalGeneration.from_pretrained=staticmethod(fp32)
        from mineru.cli import common
        from mineru.utils.engine_utils import get_vlm_engine
        common.get_vlm_engine=lambda engine,is_async=False:get_vlm_engine('transformers',is_async)
        common.do_parse(str(root/'out'),['page'],[pdf.read_bytes()],['en'],backend='vlm-engine',parse_method='auto',
            formula_enable=False,table_enable=True,image_analysis=False,f_draw_layout_bbox=False,f_draw_span_bbox=False,
            f_dump_orig_pdf=False,f_dump_content_list=False,model_path=str(weights.resolve()),batch_size=1)
        files=list((root/'out').rglob('*.md'))
        if len(files)!=1:raise RuntimeError(f'Expected one Markdown result, found {len(files)}')
        return files[0].read_text(),version('mineru')

def main():
    cmd=argparse.ArgumentParser(description=__doc__)
    cmd.add_argument('parser',choices=['pymupdf','mineru']);cmd.add_argument('pdf',type=Path)
    cmd.add_argument('output',type=Path);cmd.add_argument('--weights',type=Path);cmd.add_argument('--mineru-config',type=Path)
    args=cmd.parse_args()
    if args.output.exists():raise FileExistsError(args.output)
    tick=time.monotonic()
    text,package=(baseline(args.pdf) if args.parser=='pymupdf' else mineru(args.pdf,args.weights,args.mineru_config))
    result={'parser':args.parser,'package':package,'input_sha256':hashlib.sha256(args.pdf.read_bytes()).hexdigest(),
            'output_sha256':hashlib.sha256(text.encode()).hexdigest(),'seconds':time.monotonic()-tick,'text':text}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False)

if __name__=='__main__':
    main()
