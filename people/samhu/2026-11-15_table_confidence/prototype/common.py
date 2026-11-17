"""Paths and provenance shared by the incremental prototype."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from regions import NATIVE
from core import read, write, sha, digest
# Keep prototype modules ahead of legacy modules with the same filename.
sys.path.insert(0,str(Path(__file__).resolve().parent))
OLD = ROOT / 'runs/sponsor_all'
RUN = ROOT / 'runs/native_prototype'
RESULTS = ROOT / 'results/native_prototype'
def issuer(document):
    return 'rolls_royce' if document.startswith('rolls_royce') else document.split('_20')[0]
