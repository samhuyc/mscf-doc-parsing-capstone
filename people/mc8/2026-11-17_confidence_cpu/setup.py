"""Reproduce installation/data preparation. This script never runs inference."""
import argparse
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from common import HERE, LOCAL, config, read, write, sha

LLAMA_REVISION='52975342ff6b85127ff31930d39e36725fd08809'


def call(args,**kwargs):
    subprocess.run([str(x) for x in args],cwd=HERE,check=True,**kwargs)


def environments():
    python=HERE/'.venv/bin/python'
    if not python.exists():
        manager=LOCAL/'micromamba'
        if not manager.exists():
            archive=LOCAL/'micromamba.tar.bz2';LOCAL.mkdir(parents=True,exist_ok=True)
            with urllib.request.urlopen('https://micro.mamba.pm/api/micromamba/osx-64/latest',timeout=120) as r:archive.write_bytes(r.read())
            with tarfile.open(archive) as tf:manager.write_bytes(tf.extractfile('bin/micromamba').read())
            manager.chmod(0o755)
        call([manager,'create','--yes','--no-rc','--root-prefix',LOCAL/'mamba','--prefix',HERE/'.venv',
              '--override-channels','--channel','conda-forge','python=3.10','pip','tesseract=5.5.3'])
    call([python,'-m','pip','install','--only-binary=:all:','-r',HERE/'requirements-cpu.txt'])
    convert=LOCAL/'convert-venv'
    if not (convert/'bin/python').exists():call([python,'-m','venv','--system-site-packages',convert])
    call([python,'-m','pip','--python',convert/'bin/python','install','--only-binary=:all:','-r',HERE/'requirements-convert.txt'])


def source():
    pin=LOCAL/'llama-revision.txt';dest=LOCAL/'llama-src'
    if dest.exists() and pin.exists():
        if pin.read_text().strip()!=LLAMA_REVISION:raise RuntimeError('Existing llama.cpp revision differs')
        return
    LOCAL.mkdir(exist_ok=True);archive=LOCAL/'llama-source.tar.gz'
    with urllib.request.urlopen(f'https://codeload.github.com/ggml-org/llama.cpp/tar.gz/{LLAMA_REVISION}',timeout=120) as r,archive.open('wb') as f:
        shutil.copyfileobj(r,f,4*1024*1024)
    prefix=f'llama.cpp-{LLAMA_REVISION}/'
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            if not member.name.startswith(prefix):continue
            rel=PurePosixPath(member.name[len(prefix):])
            if str(rel)=='.':continue
            if rel.is_absolute() or '..' in rel.parts:raise ValueError('Unsafe archive member')
            out=dest.joinpath(*rel.parts)
            if member.isdir():out.mkdir(parents=True,exist_ok=True)
            elif member.isfile():
                out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(tf.extractfile(member).read());out.chmod(member.mode)
    pin.write_text(LLAMA_REVISION+'\n')


def build():
    source()
    developer=Path('/Library/Developer/CommandLineTools')
    sdk=developer/'SDKs/MacOSX26.5.sdk'
    if not sdk.exists():sdk=developer/'SDKs/MacOSX.sdk'
    options=[]
    if (developer/'usr/bin/clang++').exists():
        options=[f'-DCMAKE_C_COMPILER={developer}/usr/bin/clang',f'-DCMAKE_CXX_COMPILER={developer}/usr/bin/clang++',
                 f'-DCMAKE_MAKE_PROGRAM={developer}/usr/bin/make',f'-DCMAKE_OSX_SYSROOT={sdk}']
    call(['cmake','-S',HERE,'-B',LOCAL/'cpu-build','-DCMAKE_BUILD_TYPE=Release',*options])
    call(['cmake','--build',LOCAL/'cpu-build','--target','confidence-vlm','-j','4'])
    write(HERE/'runtime-build.json',dict(llama_revision=LLAMA_REVISION,native_source_sha256=sha(HERE/'native_vlm.cpp'),
       cmake_sha256=sha(HERE/'CMakeLists.txt'),binary_sha256=sha(LOCAL/'cpu-build/bin/confidence-vlm'),
       cpu_only=True,metal=False,accelerate=True,compiler=str(developer/'usr/bin/clang++'),sdk=str(sdk),inference_run=False))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--stage',choices=['environments','download','build','convert','data','all'],required=True)
    args=p.parse_args()
    if sys.platform!='darwin':p.error('This setup targets Intel macOS')
    LOCAL.mkdir(exist_ok=True)
    stages=['environments','download','build','convert','data'] if args.stage=='all' else [args.stage]
    for stage in stages:
        if stage=='environments':environments()
        elif stage=='download':call([HERE/'.venv/bin/python',HERE/'download_assets.py','--models','--data'])
        elif stage=='build':build()
        elif stage=='convert':
            call([LOCAL/'convert-venv/bin/python',HERE/'prepare_models.py'])
            call([HERE/'.venv/bin/python',HERE/'inspect_gguf.py'])
        elif stage=='data':call([HERE/'.venv/bin/python',HERE/'prepare_data.py'])
    print('Setup stages complete. Inference, fitting and evaluation have NOT been started.')


if __name__=='__main__':main()
