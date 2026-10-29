"""Download the frozen nine-document pilot and exact upstream evaluator sources."""
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and path.stat().st_size:
        return
    temporary = path.with_suffix(path.suffix + ".part")
    subprocess.run(["curl", "-fLsS", "--retry", "3", "--connect-timeout", "30",
                    "--max-time", "300", url, "-o", str(temporary)], check=True)
    temporary.replace(path)


def hf_url(config, filename):
    return (f"https://huggingface.co/datasets/{config['repo']}/resolve/"
            f"{config['revision']}/{quote(filename, safe='/')}")


def decoded(value):
    return json.loads(value) if isinstance(value, str) else value


def pdf_pages(path):
    try:
        from pypdf import PdfReader
        return len(PdfReader(path).pages)
    except ImportError:
        import pypdfium2
        pdf = pypdfium2.PdfDocument(str(path))
        try:
            return len(pdf)
        finally:
            pdf.close()


def prepare():
    config = read_json(ROOT / "pilot_config.json")
    indexes = {}
    for split in ("short", "medium", "long"):
        path = ROOT / "artifacts" / "metadata" / f"{split}.jsonl"
        download(hf_url(config['datasets']['extractbench'], f"{split}.jsonl"), path)
        for line in path.read_text().splitlines():
            row = json.loads(line)
            indexes[row['id']] = row

    manifest = []
    for number, selected in enumerate(config['documents'], 1):
        dataset = selected['dataset']
        identifier = selected['id']
        local_id = f"{number:02d}_{dataset}"
        folder = ROOT / "data" / local_id
        folder.mkdir(parents=True, exist_ok=True)
        spec = config['datasets'][dataset]
        if dataset == 'extractbench':
            row = indexes[identifier]
            download(hf_url(spec, row['pdf']), folder / 'document.pdf')
            write_json(folder / 'schema.json', decoded(row['data_schema']))
            write_json(folder / 'reference.json', row)
            tags = row['tags']
        else:
            for remote, local in [('document.pdf', 'document.pdf'),
                                  ('schema.json', 'schema.json'),
                                  ('ground_truth.json', 'reference.json')]:
                download(hf_url(spec, identifier + '/' + remote), folder / local)
            tags = []
        pdf = folder / 'document.pdf'
        if not pdf.read_bytes().startswith(b'%PDF-'):
            raise ValueError(f"Not a PDF: {pdf}")
        pages = pdf_pages(pdf)
        record = dict(selected, local_id=local_id, revision=spec['revision'],
                      dataset_repo=spec['repo'], pages=pages, tags=tags,
                      files={name: {'path': str((folder / filename).relative_to(ROOT)),
                                    'sha256': sha256(folder / filename)}
                             for name, filename in [('pdf', 'document.pdf'),
                                                    ('schema', 'schema.json'),
                                                    ('reference', 'reference.json')]})
        manifest.append(record)
        print(local_id, identifier, pages, 'pages', flush=True)
    manifest_path = ROOT / 'manifest.json'
    if manifest_path.exists() and read_json(manifest_path) != manifest:
        raise ValueError('Downloaded data differs from frozen manifest; investigate before replacing it.')
    write_json(manifest_path, manifest)

    for name, spec in config['evaluators'].items():
        archive = ROOT / 'artifacts' / f"{name}-{spec['revision']}.zip"
        download(f"https://codeload.github.com/{spec['repo']}/zip/{spec['revision']}", archive)
        destination = ROOT / 'artifacts' / 'upstream' / name
        if destination.exists():
            continue
        destination.mkdir(parents=True)
        with zipfile.ZipFile(archive) as zipped:
            for info in zipped.infolist():
                parts = Path(info.filename).parts[1:]
                if not parts:
                    continue
                target = destination.joinpath(*parts)
                if not target.resolve().is_relative_to(destination.resolve()):
                    raise ValueError('Unsafe archive path')
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zipped.open(info) as source, target.open('wb') as output:
                        shutil.copyfileobj(source, output)
        print('Evaluator source:', name, spec['revision'], flush=True)


if __name__ == '__main__':
    prepare()
