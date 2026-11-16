"""Download pinned official checkpoints, with resumable files and LFS SHA checks."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import shutil
import time
import threading
import urllib.request

ROOT = Path(__file__).resolve().parent / 'work/extra-models'


def ranged_download(url, part, size, label):
    """Bounded parallel ranges write disjoint offsets into one resumable file."""
    step = 64 * 1024 * 1024
    journal = part.with_suffix('.chunks.json')
    if journal.exists():
        state = json.loads(journal.read_text())
        if state['url'] != url or state['size'] != size or state['step'] != step:
            raise ValueError('Range-download provenance changed')
    else:
        prefix = part.stat().st_size if part.exists() else 0
        state = dict(url=url, size=size, step=step, done=list(range(prefix // step)))
        with part.open('ab') as stream:
            stream.truncate(size)
        journal.write_text(json.dumps(state))
    lock = threading.Lock()
    done = set(state['done'])
    tasks = [i for i in range((size + step - 1) // step) if i not in done]

    def chunk(index):
        start, end = index * step, min(size, (index+1)*step)-1
        for attempt in range(4):
            request = urllib.request.Request(url, headers={'Range': f'bytes={start}-{end}'})
            try:
                with urllib.request.urlopen(request, timeout=90) as response:
                    if response.status != 206 or response.headers.get('Content-Range') != f'bytes {start}-{end}/{size}':
                        raise ValueError('Server did not honor exact byte range')
                    count = 0
                    with part.open('r+b') as stream:
                        stream.seek(start)
                        while block := response.read(min(4*1024*1024, end-start+1-count)):
                            stream.write(block)
                            count += len(block)
                            if count == end-start+1:
                                break
                    if count != end-start+1:
                        raise ValueError('Incomplete byte range')
                with lock:
                    done.add(index)
                    state['done'] = sorted(done)
                    temp = journal.with_suffix('.tmp')
                    temp.write_text(json.dumps(state))
                    temp.replace(journal)
                    received = sum(min(step, size-i*step) for i in done)
                    if len(done) % 4 == 0 or not (set(tasks)-done):
                        print(label, f'{received/1e9:.2f}/{size/1e9:.2f} GB', flush=True)
                return
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(chunk, tasks))


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def download(name):
    meta = json.loads((ROOT / f'{name}.manifest.json').read_text())
    target = ROOT / name
    target.mkdir(exist_ok=True)
    records = []
    for info in meta['files']:
        remote = info['rfilename']
        path = target / remote.removeprefix(meta['prefix'])
        expected_size = info.get('size', info.get('lfs', {}).get('size'))
        expected_sha = info.get('lfs', {}).get('sha256')
        if path.exists():
            actual = sha(path)
            if path.stat().st_size != expected_size or (expected_sha and actual != expected_sha):
                raise ValueError(f'Existing file changed: {path}')
        else:
            url = f'https://huggingface.co/{meta["repository"]}/resolve/{meta["revision"]}/{remote}'
            part = path.with_suffix(path.suffix + '.part')
            if expected_size > 128*1024*1024:
                ranged_download(url, part, expected_size, name)
            for attempt in range(4) if expected_size <= 128*1024*1024 else []:
                offset = part.stat().st_size if part.exists() else 0
                if expected_size and offset == expected_size:
                    break
                request = urllib.request.Request(url, headers={'Range': f'bytes={offset}-'} if offset else {})
                try:
                    with urllib.request.urlopen(request, timeout=90) as response:
                        resumed = offset > 0 and response.status == 206
                        received = offset if resumed else 0
                        last_report = received
                        with part.open('ab' if resumed else 'wb') as stream:
                            while block := response.read(4 * 1024 * 1024):
                                stream.write(block)
                                received += len(block)
                                if received - last_report >= 256 * 1024 * 1024:
                                    print(name, path.name, f'{received/1e9:.2f}/{expected_size/1e9:.2f} GB', flush=True)
                                    last_report = received
                    if expected_size and part.stat().st_size != expected_size:
                        raise ValueError('Incomplete download')
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    time.sleep(2 ** attempt)
            actual = sha(part)
            if expected_sha and actual != expected_sha:
                raise ValueError(f'Hash mismatch: {name}/{path.name}')
            part.replace(path)
        records.append(dict(file=path.name, sha256=actual, bytes=path.stat().st_size))
    provenance = dict(repository=meta['repository'], revision=meta['revision'], files=records)
    (target / 'download_provenance.json').write_text(json.dumps(provenance, indent=2)+'\n')
    print('READY', name, sum(r['bytes'] for r in records), 'bytes', flush=True)


if __name__ == '__main__':
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('names', nargs='+', choices=('paddle_vl', 'monkey', 'glm', 'deepseek'))
    args = cli.parse_args()
    policy_path = ROOT.parent.parent / 'extra_trial_policy.json'
    if policy_path.exists():
        policy = json.loads(policy_path.read_text())
        if set(args.names) & set(policy['excluded']):
            cli.error('A requested model has been excluded by the user')
        for name in args.names:
            manifest = json.loads((ROOT / f'{name}.manifest.json').read_text())
            if sum(f['size'] for f in manifest['files']) > policy['checkpoint_byte_limit']:
                cli.error(f'{name} exceeds the requested checkpoint size limit')
    remaining = 0
    for name in args.names:
        meta = json.loads((ROOT / f'{name}.manifest.json').read_text())
        for info in meta['files']:
            path = ROOT / name / info['rfilename'].removeprefix(meta['prefix'])
            part = path.with_suffix(path.suffix+'.part')
            if not path.exists():
                remaining += max(0, info['size'] - (part.stat().st_blocks*512 if part.exists() else 0))
    if shutil.disk_usage(ROOT).free < remaining + 4 * 1024**3:
        raise RuntimeError('Insufficient disk space to retain all checkpoints plus 4 GiB headroom')
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(download, args.names))
