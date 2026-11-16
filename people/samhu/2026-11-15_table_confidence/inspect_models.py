"""Resolve public model revisions and file inventories before local trials."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent
MODELS = {
    'paddle_vl': ('PaddlePaddle/PaddleOCR-VL-1.6', ''),
    'monkey': ('echo840/MonkeyOCR-pro-1.2B', 'Recognition/'),
    'glm': ('zai-org/GLM-OCR', ''),
    'deepseek': ('deepseek-ai/DeepSeek-OCR-2', ''),
}


def get(url):
    with urllib.request.urlopen(url, timeout=90) as stream:
        return json.load(stream)


def inspect(item):
    name, (repo, prefix) = item
    meta = get(f'https://huggingface.co/api/models/{repo}?blobs=true')
    files = [f for f in meta['siblings'] if f['rfilename'].startswith(prefix) and
             '/' not in f['rfilename'][len(prefix):] and
             f['rfilename'].endswith(('.safetensors', '.json', '.model', '.txt', '.jinja', '.py'))]
    config = get(f'https://huggingface.co/{repo}/resolve/{meta["sha"]}/{prefix}config.json')
    result = dict(name=name, repository=repo, prefix=prefix, revision=meta['sha'], files=files,
                  config=config, safetensors=meta.get('safetensors'))
    target = ROOT / 'work/extra-models'
    target.mkdir(parents=True, exist_ok=True)
    (target / f'{name}.manifest.json').write_text(json.dumps(result, indent=2)+'\n')
    return dict(name=name, repository=repo, revision=meta['sha'],
                architecture=config.get('architectures'), model_type=config.get('model_type'),
                bytes=sum(f.get('size', f.get('lfs', {}).get('size', 0)) for f in files),
                safetensors=meta.get('safetensors'), files=[f['rfilename'] for f in files])


if __name__ == '__main__':
    with ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(inspect, MODELS.items()):
            print(json.dumps(result), flush=True)
    version = get('https://pypi.org/pypi/mlx-vlm/json')['info']['version']
    print('Latest mlx-vlm', version)
