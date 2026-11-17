"""Local source-versus-grid review; only explicit human approvals become ground truth."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
CHECKS = ('values', 'associations', 'units', 'complete')


def digest_bytes(data):
    return hashlib.sha256(data).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


class GridParser(HTMLParser):
    """Expand merged headers so each editable column keeps its header context."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.rows = None
        self.row = None
        self.cell = None
        self.depth = 0

    def handle_starttag(self, tag, attrs):
        if tag == 'table':
            self.depth += 1
            if self.depth == 1:
                self.rows = []
        if self.depth != 1:
            return
        if tag == 'tr':
            self.row = []
        elif tag in ('td', 'th'):
            attrs = dict(attrs)
            def span(k):
                try:
                    return max(1, min(100, int(attrs.get(k, 1))))
                except ValueError:
                    return 1
            self.cell = {'parts': [], 'rowspan': span('rowspan'), 'colspan': span('colspan')}
        elif tag == 'br' and self.cell is not None:
            self.cell['parts'].append('\n')

    def handle_data(self, data):
        if self.cell is not None and self.depth == 1:
            self.cell['parts'].append(data)

    def handle_endtag(self, tag):
        if self.depth == 1:
            if tag in ('td', 'th') and self.cell is not None:
                if self.row is None:
                    self.row = []
                self.cell['text'] = ''.join(self.cell.pop('parts')).strip()
                self.row.append(self.cell)
                self.cell = None
            elif tag == 'tr' and self.row is not None:
                self.rows.append(self.row)
                self.row = None
            elif tag == 'table' and self.rows is not None:
                self.tables.append(self.expand(self.rows))
                self.rows = None
        if tag == 'table':
            self.depth = max(0, self.depth - 1)

    @staticmethod
    def expand(rows):
        cells = {}
        for r, row in enumerate(rows):
            c = 0
            for cell in row:
                while (r, c) in cells:
                    c += 1
                for dr in range(cell['rowspan']):
                    for dc in range(cell['colspan']):
                        if (r + dr, c + dc) in cells:
                            raise ValueError('Overlapping table spans; manual reconstruction required')
                        cells[r + dr, c + dc] = cell['text']
                c += cell['colspan']
        if not cells:
            return [['']]
        nr, nc = max(r for r, _ in cells) + 1, max(c for _, c in cells) + 1
        return [[cells.get((r, c), '') for c in range(nc)] for r in range(nr)]


def parse_grids(text):
    parser = GridParser()
    parser.feed(text)
    return [{'name': f'Table {i + 1}', 'cells': cells} for i, cells in enumerate(parser.tables)]


def load_dataset(run):
    refs_path = ROOT / 'accuracy_references.json'
    refs = json.loads(refs_path.read_text())
    selected = {r['table_id']: r for r in refs['references'] if r['primary_eligible']}
    bundle = json.loads((run / 'tables.json').read_text())
    pages = {(p['document'], p['page']): p for p in bundle['pages']}
    tables, assets = [], {}
    for table in bundle['tables']:
        tid = table['table_id']
        if tid not in selected:
            continue
        ref = selected[tid]
        image = run / table['image']
        if digest_bytes(image.read_bytes()) != ref['image_sha256'] or table['source_sha256'] != ref['source_sha256']:
            raise ValueError(f'Source mismatch: {tid}')
        draft_path = run / 'extra' / 'monkey' / (tid + '.json')
        draft_bytes = draft_path.read_bytes()
        prediction = json.loads(draft_bytes)
        if prediction['image_sha256'] != ref['image_sha256']:
            raise ValueError(f'Draft source mismatch: {tid}')
        grids = parse_grids(prediction['text'])
        if not grids:
            raise ValueError(f'No editable draft table: {tid}')
        page = run / pages[table['document'], table['page']]['overview']
        assets[f'/images/{tid}/crop.png'] = image
        assets[f'/images/{tid}/page.png'] = page
        tables.append(dict(table_id=tid, document=table['document'], page=table['page'],
            image_sha256=ref['image_sha256'], source_sha256=ref['source_sha256'],
            draft_sha256=digest_bytes(draft_bytes), grids=grids,
            original_reference_text=ref['reference_text'],
            crop_url=f'/images/{tid}/crop.png', page_url=f'/images/{tid}/page.png',
            bbox_px=table['bbox_px']))
    if set(selected) != {t['table_id'] for t in tables}:
        raise ValueError('Missing members of the fixed review cohort')
    assistant_path = ROOT / 'assistant_table_review.json'
    if assistant_path.exists():
        assistant = json.loads(assistant_path.read_text())
        if assistant['reference_sha256'] != digest_bytes(refs_path.read_bytes()):
            raise ValueError('Assistant review references are stale')
        for table in tables:
            review = assistant['reviews'].get(table['table_id'])
            if review:
                if any(review[k] != table[k] for k in ('image_sha256', 'source_sha256', 'draft_sha256')):
                    raise ValueError('Assistant review source mismatch')
                table['assistant_review'] = review
    return tables, assets, digest_bytes(refs_path.read_bytes())


class ReviewStore:
    def __init__(self, path, tables, reference_sha):
        self.path = Path(path)
        self.tables = {t['table_id']: t for t in tables}
        self.reference_sha = reference_sha
        self.lock = threading.Lock()
        self.records = {}
        if self.path.exists():
            saved = json.loads(self.path.read_text())
            if saved['reference_sha256'] != reference_sha:
                raise ValueError('Reference file changed; review migration required')
            for tid, record in saved['reviews'].items():
                t = self.tables.get(tid)
                if not t or any(record[k] != t[k] for k in ('image_sha256', 'source_sha256', 'draft_sha256')):
                    raise ValueError(f'Review provenance mismatch: {tid}')
            self.records = saved['reviews']

    def default(self, tid):
        t = self.tables[tid]
        a = t.get('assistant_review', {})
        use_assistant = bool(a.get('grids')) and not a.get('requires_recrop')
        return dict(table_id=tid, revision=0, status='unreviewed', human_verified=False,
            reviewer='', notes='', context=a.get('context', '') if use_assistant else '', checks={k: False for k in CHECKS},
            grids=deepcopy(a['grids'] if use_assistant else t['grids']), reviewed_at=None, updated_at=None,
            draft_source='Assistant source-image review of MonkeyOCR draft; not human verified' if use_assistant else 'MonkeyOCR-pro-1.2B; model-assisted draft, not ground truth',
            **{k: t[k] for k in ('image_sha256', 'source_sha256', 'draft_sha256')})

    def evaluation_status(self, tid, record):
        a = self.tables[tid].get('assistant_review', {})
        if a.get('requires_recrop'):
            return 'needs_recrop'
        if a.get('material_correction') and record.get('human_verified') and record['revision'] <= a['based_on_human_revision']:
            return 'needs_recheck'
        return 'human_verified' if record.get('human_verified') else 'unverified'

    def snapshot(self):
        statuses = {tid: self.evaluation_status(tid, self.records.get(tid, {})) for tid in self.tables}
        return dict(schema_version=1, reference_sha256=self.reference_sha,
            protocol='Source-verified cell grids. Values in a wrong row or column are incorrect. '
                     'Require human_verified plus evaluation_status=human_verified; exclude unresolved rechecks and incomplete crops. Merged headers are expanded.',
            draft_bias_note='Drafts originate from MonkeyOCR; verify every cell against the source. '
                            'Model-assisted annotation can bias model comparison.',
            evaluation_status=statuses,
            evaluation_eligible_ids=[tid for tid, status in statuses.items() if status == 'human_verified'],
            assistant_reviews={tid: deepcopy(t['assistant_review']) for tid, t in self.tables.items() if 'assistant_review' in t},
            reviews=deepcopy(self.records))

    def save(self, payload):
        with self.lock:
            tid = payload.get('table_id')
            if tid not in self.tables:
                raise ValueError('Unknown table')
            old = self.records.get(tid, self.default(tid))
            if type(payload.get('revision')) is not int or payload['revision'] != old['revision']:
                raise RuntimeError('This table changed in another tab. Reload before saving.')
            action = payload.get('action')
            if action not in ('save', 'approve', 'flag'):
                raise ValueError('Unknown review action')
            grids = payload.get('grids')
            if not isinstance(grids, list) or not 1 <= len(grids) <= 30:
                raise ValueError('Keep at least one table grid')
            for grid in grids:
                if not isinstance(grid, dict) or not isinstance(grid.get('name'), str) or len(grid['name']) > 300:
                    raise ValueError('Invalid table name')
                cells = grid.get('cells')
                if not isinstance(cells, list) or not 1 <= len(cells) <= 300:
                    raise ValueError('Invalid row count')
                if not isinstance(cells[0], list) or not 1 <= len(cells[0]) <= 60:
                    raise ValueError('Invalid column count')
                width = len(cells[0])
                if any(not isinstance(row, list) or len(row) != width or
                       any(not isinstance(c, str) or len(c) > 10000 for c in row) for row in cells):
                    raise ValueError('Use a rectangular grid with text cells')
            for key in ('reviewer', 'context', 'notes'):
                if not isinstance(payload.get(key), str) or len(payload[key]) > 20000:
                    raise ValueError(f'Invalid {key}')
            checks = payload.get('checks', {})
            if not isinstance(checks, dict) or any(type(checks.get(k)) is not bool for k in CHECKS):
                raise ValueError('Invalid review checks')
            if action == 'approve':
                if self.tables[tid].get('assistant_review', {}).get('requires_recrop'):
                    raise ValueError('This crop omits required labels or headers; recrop before confirming')
                if not payload['reviewer'].strip():
                    raise ValueError('Enter your name or initials before confirming')
                if not all(checks.values()) or set(checks) != set(CHECKS):
                    raise ValueError('Complete all four source checks before confirming')
                if not any(c.strip() for g in grids for row in g['cells'] for c in row):
                    raise ValueError('An empty draft cannot be confirmed')
            if action == 'flag' and not payload['notes'].strip():
                raise ValueError('Add a note explaining what needs attention')
            record = self.default(tid)
            record.update({k: deepcopy(payload[k]) for k in ('grids', 'reviewer', 'notes', 'context')})
            # Every ordinary edit revokes approval. Only the explicit approve action sets it.
            verified = action == 'approve'
            record.update(revision=old['revision'] + 1, status='verified' if verified else
                          'needs_attention' if action == 'flag' else 'draft',
                          human_verified=verified, checks=checks if verified else {k: False for k in CHECKS},
                          updated_at=utc(), reviewed_at=utc() if verified else None)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            history = self.path.parent / 'history'
            history.mkdir(exist_ok=True)
            previous = self.records.get(tid)
            self.records[tid] = record
            try:
                encoded = json.dumps(self.snapshot(), ensure_ascii=False, indent=2) + '\n'
                tmp = self.path.with_suffix('.tmp')
                tmp.write_text(encoded)
                history_file = history / f'{tid}.r{record["revision"]}.{secrets.token_hex(4)}.json'
                history_file.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
                tmp.replace(self.path)
            except Exception:
                if previous is None:
                    self.records.pop(tid, None)
                else:
                    self.records[tid] = previous
                raise
            return deepcopy(record)


def make_handler(tables, assets, store, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def send_data(self, code, body, kind='application/json; charset=utf-8', download=False):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'")
            if download:
                self.send_header('Content-Disposition', 'attachment; filename="financial_ground_truth.json"')
            self.end_headers()
            self.wfile.write(body)

        def allowed_host(self):
            return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.allowed_host():
                self.send_data(403, {'error': 'Local access only'})
                return
            path = urlparse(self.path).path
            if path == '/':
                self.send_data(200, (ROOT / 'review_panel.html').read_bytes(), 'text/html; charset=utf-8')
            elif path == '/api/session':
                with store.lock:
                    self.send_data(200, dict(tables=tables, reviews=store.records, token=token,
                        save_path=str(store.path)))
            elif path == '/api/export':
                with store.lock:
                    self.send_data(200, store.snapshot(), download=True)
            elif path in assets:
                self.send_data(200, assets[path].read_bytes(), 'image/png')
            else:
                self.send_data(404, {'error': 'Not found'})

        def do_POST(self):
            origin = self.headers.get('Origin')
            allowed = f'http://{self.headers.get("Host")}'
            if not self.allowed_host() or self.headers.get('X-Review-Token') != token or (origin and origin != allowed):
                self.send_data(403, {'error': 'Review request rejected'})
                return
            if self.path != '/api/review':
                self.send_data(404, {'error': 'Not found'})
                return
            try:
                size = int(self.headers.get('Content-Length', 0))
                if not 0 < size <= 2_000_000:
                    raise ValueError('Invalid request size')
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload, dict):
                    raise ValueError('Invalid review')
                record = store.save(payload)
                self.send_data(200, record)
            except RuntimeError as exc:
                self.send_data(409, {'error': str(exc)})
            except (ValueError, KeyError, TypeError) as exc:
                self.send_data(400, {'error': str(exc)})
            except OSError:
                self.send_data(500, {'error': 'Could not write review. Keep this tab open and retry.'})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT / 'runs/sponsor_all')
    parser.add_argument('--port', type=int, default=8766)
    args = parser.parse_args()
    tables, assets, ref_sha = load_dataset(args.root)
    store = ReviewStore(args.root / 'review/financial_ground_truth.json', tables, ref_sha)
    server = ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(tables, assets, store, secrets.token_urlsafe(32)))
    print(f'Review panel: http://127.0.0.1:{server.server_port}', flush=True)
    print(f'Reviews: {store.path}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
