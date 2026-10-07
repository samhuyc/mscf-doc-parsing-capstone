"""Read-only, hash-checked imports of the historical O6 1.1.0 engine."""
import hashlib
import importlib.util
import sys

from config import BASELINE

PINNED = {
    'rules': '05b4d61529f86fa88bde9243ee799d3e3d0c8800743f71c3a64225d5e8737b8d',
    'inputs': '4ab0efee34618b0702c11d3b1cb015ca78cc51069e223c234a0df971cb754fe5',
}


def load(name):
    path = BASELINE / (name + '.py')
    if hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest() != PINNED[name]:
        raise ValueError(f'Historical O6 {name} has changed; do not silently change the baseline')
    module_name = '_metadata_o6_110_' + name
    if module_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return sys.modules[module_name]


inputs = load('inputs')
rules = load('rules')
