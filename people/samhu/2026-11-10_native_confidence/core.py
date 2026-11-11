"""Native OCR confidence summaries. No cross-model agreement or fitted scores."""
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SPONSOR = ROOT.parent / '2026-09-29_sponsor_samples'
PILOT = ROOT.parent / '2026-10-05_pilot_benchmark'
PADDLE = ROOT.parents[1] / 'mc8/2026-10-28_paddleocr'


def read(path):
    return json.loads(Path(path).read_text())


def write(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    temporary.replace(path)


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def summarize(units):
    """Raw summaries of returned units. Scores are NOT calibrated probabilities.

    Character weights make a long recognized line count more than a short line.
    This still does not make scores comparable between different engines.
    """
    scored = [u for u in units if u.get('score') is not None and
              (u.get('text', '').strip() or u.get('unit_kind') in ('subword_token','character'))]
    for u in scored:
        p = u['score']
        if isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError('Invalid native score')
    values = sorted(u['score'] for u in scored)
    weights = [max(1, len(u['text'].strip())) for u in scored]
    total = sum(weights)
    return {
        'returned_units': len(units), 'scored_units': len(scored),
        'mean': sum(values) / len(values) if values else None,
        'character_weighted_mean': sum(u['score']*w for u, w in zip(scored, weights))/total if total else None,
        'geometric_mean': (0.0 if 0 in values else math.exp(sum(math.log(v) for v in values)/len(values))) if values else None,
        'p10': values[int((len(values)-1)*0.1)] if values else None,
        'fraction_below_0_90': sum(v < .9 for v in values)/len(values) if values else None,
        'minimum': min(values) if values else None,
        'probability_document_correct': None,
        'calibrated': False,
    }


def document_result(document, engine, pages, expected_pages):
    ids = [p['page'] for p in pages]
    if len(ids) != len(set(ids)) or any(i < 1 or i > expected_pages for i in ids):
        raise ValueError('Invalid page inventory')
    successful = [p for p in pages if p['status'] == 'success']
    units = [u for p in successful for u in p.get('confidence_units', p['units'])]
    return {'document': document, 'engine': engine, 'expected_pages': expected_pages,
            'successful_pages': len(successful), 'successful_page_ids': sorted(p['page'] for p in successful),
            'missing_or_failed_page_ids': sorted(set(range(1,expected_pages+1)) - {p['page'] for p in successful}),
            'page_coverage': len(successful)/expected_pages,
            'empty_successful_pages': sum(not any(u.get('text','').strip() for u in p['units']) for p in successful),
            'truncated_pages': [p['page'] for p in successful if p.get('truncated', False)],
            'all_pages_finished_without_token_limit': len(successful)==expected_pages and not any(p.get('truncated',False) for p in successful),
            'confidence': summarize(units)}


def sources():
    return read(PILOT / 'documents.json')
