"""Read official MonkeyOCR recognition prompts; does not execute remote code."""
import json
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent / 'work/upstream-monkey'
ROOT.mkdir(parents=True, exist_ok=True)


def get(url):
    with urllib.request.urlopen(url, timeout=90) as stream:
        return stream.read()


if __name__ == '__main__':
    repo = 'Yuliang-Liu/MonkeyOCR'
    tree = json.loads(get(f'https://api.github.com/repos/{repo}/git/trees/main?recursive=1'))
    revision = tree['sha']
    paths = [f['path'] for f in tree['tree'] if f['type']=='blob' and f['path'].endswith(('.py', '.yaml', '.yml'))
             and any(x in f['path'].lower() for x in ('recognition', 'prompt', 'llm', 'model_configs'))]
    (ROOT/'tree.json').write_text(json.dumps(dict(repository=repo, revision=revision, paths=paths), indent=2))
    for path in paths:
        data = get(f'https://raw.githubusercontent.com/{repo}/{revision}/{path}')
        target = ROOT/path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if any(x in data.lower() for x in (b'prompt', b'table')):
            print(path, flush=True)
