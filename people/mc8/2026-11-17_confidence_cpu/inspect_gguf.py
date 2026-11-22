"""Inspect GGUF metadata/tensor descriptors only; never construct a model."""
import json
import sys
from common import HERE, LOCAL, MODELS, config, write


def main():
    sys.path.insert(0,str(LOCAL/'llama-src/gguf-py'))
    from gguf import GGUFReader
    results={}
    for name in config()['models']:
        results[name]={}
        for filename in ('model-f16.gguf','mmproj-f16.gguf'):
            path=MODELS/'gguf'/name/filename
            reader=GGUFReader(str(path),mode='r')
            def field(key):
                f=reader.fields.get(key)
                return f.contents() if f is not None else None
            types=sorted({t.tensor_type.name for t in reader.tensors})
            if not set(types)<={'F32','F16'}:raise ValueError(f'Unexpected quantization in {path}: {types}')
            results[name][filename]=dict(architecture=field('general.architecture'),
                projector_type=field('clip.projector_type'),tensor_count=len(reader.tensors),
                tensor_types=types,bytes=path.stat().st_size,inspection='metadata/descriptors only, no inference')
            del reader
    write(HERE/'gguf-inspection.json',results)
    print(json.dumps(results,indent=2))


if __name__=='__main__':main()
