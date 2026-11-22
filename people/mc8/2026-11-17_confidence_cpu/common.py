"""Local paths, atomic records and provenance; no model imports or execution."""
import hashlib
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
CAPSTONE = HERE.parents[3]
SAM = REPO / 'people/samhu/2026-11-15_table_confidence'
NATIVE = SAM.parent / '2026-11-10_native_confidence'
LOCAL = HERE / '.local'
MODELS = LOCAL / 'models'
DATA = HERE / 'data/fintabnet_2000'
# Sam's scientific modules import these names from a module called common.
# Export their original locations to avoid a module-name collision; our I/O
# always uses HERE/DATA and never invokes Sam's preparation/evaluation CLIs.
ROOT = SAM
OLD = SAM / 'runs/sponsor_all'
RUN = SAM / 'runs/native_prototype'
RESULTS = SAM / 'results/native_prototype'


def read(path):
    return json.loads(Path(path).read_text())


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    temp.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n')
    temp.replace(path)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(4*1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def digest(value):
    # Match Sam's ASCII-escaped canonical JSON, including non-ASCII labels.
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def config():
    return read(HERE / 'config.json')


def implementation_hashes():
    return {name:sha(HERE/name) for name in ('common.py','worker.py','native_vlm.cpp','runtime-build.json',
            'model-conversions.json','rendered-prompts.json','requirements-cpu.lock.txt')}


def environment():
    for key, name in {'PADDLE_PDX_CACHE_HOME':'paddlex', 'PADDLE_HOME':'paddle',
                      'HF_HOME':'hf', 'XDG_CACHE_HOME':'xdg', 'MPLCONFIGDIR':'matplotlib'}.items():
        path = LOCAL / 'cache' / name
        path.mkdir(parents=True, exist_ok=True)
        os.environ[key] = str(path)
    os.environ.update(OMP_NUM_THREADS='1', OMP_THREAD_LIMIT='2', TOKENIZERS_PARALLELISM='false',
                      PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK='True', HF_HUB_OFFLINE='1')


def sam_paths():
    import sys
    # Prototype takes priority over the older modules with identical names.
    sys.path[:0] = [str(SAM/'prototype'), str(SAM), str(NATIVE)]
