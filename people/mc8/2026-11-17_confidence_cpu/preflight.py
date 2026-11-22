"""Verify installation and frozen inputs without loading or running any model."""
import argparse
import importlib.metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
from common import HERE, LOCAL, MODELS, DATA, SAM, config, read, write, sha


def check(require_ready=False,full_hashes=False):
    errors=[];checks={}
    def require(ok,message):
        if not ok:errors.append(message)
    require((HERE/'.venv/bin/python').exists(),'CPU Python environment missing')
    require((HERE/'.venv/bin/tesseract').exists(),'Tesseract binary missing')
    for name in ['paddlepaddle','paddleocr','paddlex','pyarrow','numpy','Pillow']:
        try:checks[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:errors.append('Missing package: '+name)
    for line in (HERE/'requirements-cpu.txt').read_text().splitlines():
        if '==' not in line or line.lstrip().startswith('#'):continue
        name,expected=line.strip().split('==',1)
        try:require(importlib.metadata.version(name)==expected,'Pinned package version differs: '+name)
        except importlib.metadata.PackageNotFoundError:errors.append('Missing pinned package: '+name)
    binary=LOCAL/'cpu-build/bin/confidence-vlm'
    require(binary.exists(),'CPU VLM executable missing')
    if binary.exists():
        p=subprocess.run([str(binary),'--help'],capture_output=True,text=True,timeout=30)
        require(p.returncode==0,'CPU executable cannot start; '+p.stderr[:300])
        checks['native_cli_help']=p.returncode==0
    tesseract=HERE/'.venv/bin/tesseract'
    if tesseract.exists():
        p=subprocess.run([str(tesseract),'--version'],capture_output=True,text=True,timeout=30)
        require(p.returncode==0,'Tesseract executable cannot start: '+p.stderr[:300])
        checks['tesseract_cli_version']=(p.stdout or p.stderr).splitlines()[0] if p.returncode==0 else None
    checks['free_disk_gib']=round(shutil.disk_usage(HERE).free/1024**3,1)
    conversions=read(HERE/'model-conversions.json') if (HERE/'model-conversions.json').exists() else {}
    for name in config()['models']:
        entry=conversions.get(name)
        require(entry is not None,'Conversion incomplete: '+name)
        if entry:
            for filename,bytes_key,hash_key in [('model-f16.gguf','model_bytes','model_sha256'),('mmproj-f16.gguf','mmproj_bytes','mmproj_sha256')]:
                path=MODELS/'gguf'/name/filename
                require(path.exists(),str(path)+' missing')
                if path.exists():
                    with path.open('rb') as f:magic=f.read(4)
                    require(magic==b'GGUF' and path.stat().st_size==entry[bytes_key],str(path)+' invalid GGUF/size')
                    if full_hashes:require(sha(path)==entry[hash_key],str(path)+' hash mismatch')
        generation=MODELS/'hf'/name/'generation_config.json'
        require(generation.exists(),'Generation settings missing: '+name)
        if generation.exists():
            try:
                stop=read(generation).get('eos_token_id')
                ids=stop if isinstance(stop,list) else [stop] if stop is not None else []
                require(all(isinstance(i,int) and i>=0 for i in ids),'Invalid EOS IDs: '+name)
            except (ValueError,TypeError):errors.append('Invalid generation settings: '+name)
    for name in ('PP-OCRv5_mobile_det','PP-OCRv5_mobile_rec'):
        for file in ('inference.json','inference.pdiparams','inference.yml'):
            require((MODELS/name/file).exists(),name+'/'+file+' missing')
    require((MODELS/'tessdata/eng.traineddata').exists(),'Pinned English Tesseract data missing')
    if full_hashes:
        from download_assets import baseline_items
        for item in baseline_items():
            path=Path(item['path'])
            # Only the recognizers used by this cropped-table experiment.
            if path.parent.name=='PP-DocLayout_plus-L':continue
            require(path.exists(),'Baseline asset missing: '+str(path))
            if path.exists():require(sha(path)==item['sha256'],'Baseline asset hash mismatch: '+str(path))
    require((HERE/'rendered-prompts.json').exists(),'Rendered prompts missing')
    if (HERE/'rendered-prompts.json').exists():
        prompts=read(HERE/'rendered-prompts.json')
        for engine in config()['engines']:
            if engine in ('tesseract','paddle'):continue
            require(engine in prompts and prompts[engine].count('<__media__>')==1,
                    'Missing/invalid multimodal prompt: '+engine)
    manifest=DATA/'tables.json'
    require(manifest.exists(),'2,000-table dataset not prepared')
    if manifest.exists():
        bundle=read(manifest);tables=bundle['tables'];seal=read(DATA/'seal.json')
        require(len(tables)==config()['tables'],'Table count differs from configuration')
        require(sum(t['sam_original'] for t in tables)==71,'Sam original table count is not 71')
        original={t['source_filename']:t for t in read(SAM/'results/native_prototype/input_manifest.json')['tables'] if t['cohort'] in ('benchmark','confirmatory')}
        included=[t for t in tables if t['sam_original']]
        require({t['source_filename'] for t in included}==set(original),'Sam original filenames differ')
        require(all(t['image_sha256']==original[t['source_filename']]['image_sha256'] and t['source_sha256']==original[t['source_filename']]['source_sha256'] for t in included),'Sam original image/annotation hashes differ')
        require(len({t['table_id'] for t in tables})==len(tables),'Duplicate table IDs')
        dev={t['issuer'] for t in tables if t['split']=='development'};test={t['issuer'] for t in tables if t['split']=='test'}
        require(not dev&test,'Issuer leakage across splits')
        require(not any(t['sam_original'] and t['split']=='test' for t in tables),'Sam old data leaked into new test')
        require(sha(manifest)==seal['tables_sha256'],'Table manifest changed after seal')
        require(sha(DATA/'references.json')==seal['references_sha256'],'References changed after seal')
        require(sha(HERE/'config.json')==seal['config_sha256'],'Configuration changed after data freeze')
        for t in tables:
            image=DATA/t['image'];require(image.exists(),'Image missing: '+t['table_id'])
            if full_hashes and image.exists():require(sha(image)==t['image_sha256'],'Image changed: '+t['table_id'])
        checks.update(tables=len(tables),sam_original=71,additional=len(tables)-71,development_issuers=len(dev),test_issuers=len(test))
    from sam_bridge import check_frozen_code
    try:check_frozen_code();checks['sam_code_unchanged']=True
    except Exception as exc:errors.append(str(exc))
    build=HERE/'runtime-build.json'
    require(build.exists(),'Runtime build provenance missing')
    if build.exists():
        b=read(build)
        require(b['native_source_sha256']==sha(HERE/'native_vlm.cpp'),'Native adapter changed after build')
        require(b['cmake_sha256']==sha(HERE/'CMakeLists.txt'),'Build settings changed after build')
        if full_hashes and binary.exists():require(sha(binary)==b['binary_sha256'],'Native executable changed')
    result=dict(ready=not errors,checks=checks,errors=errors,full_hashes=full_hashes,
                inference_run=False,calibration_run=False,evaluation_run=False,
                execution_validation='Not performed at user request; installation/build/static checks only')
    if require_ready and errors:raise RuntimeError('\n'.join(errors))
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--full-hashes',action='store_true');args=p.parse_args()
    result=check(full_hashes=args.full_hashes)
    write(HERE/'readiness.json',result);print(json.dumps(result,indent=2))
    if not result['ready']:raise SystemExit(1)


if __name__=='__main__':main()
