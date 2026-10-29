"""Conservative schema adapter v1: explicit labels and HTML table headers only.

No reference answers, source PDF, network, model, computed totals, or imputation.
Unsupported fields are omitted. Scores evaluate this adapter together with MinerU.
"""
import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from bs4 import BeautifulSoup

VERSION = 'explicit-labels-tables-v1'
MISSING = object()
STOP = {'of', 'the', 'and', 'or', 'in', 'at', 'by', 'for'}
SYNONYMS = {'qty': 'quantity', 'no': 'number', 'num': 'number', 'amt': 'amount'}


def normalize(text):
    words = re.findall(r'[a-z0-9]+', str(text).lower())
    return ' '.join(SYNONYMS.get(w, w) for w in words if w not in STOP)


def resolve(schema, root):
    schema = dict(schema)
    seen = set()
    while '$ref' in schema:
        ref = schema.pop('$ref')
        if not ref.startswith('#/') or ref in seen:
            return {}
        seen.add(ref)
        value = root
        for component in ref[2:].split('/'):
            value = value[component.replace('~1', '/').replace('~0', '~')]
        schema = {**value, **schema}
    for operator in ('anyOf', 'oneOf'):
        if operator in schema:
            options = [resolve(x, root) for x in schema[operator] if x.get('type') != 'null']
            if len(options) == 1:
                schema = {**schema, **options[0]}
    return schema


def kind(schema):
    types = schema.get('type', '')
    if isinstance(types, list):
        types = next((t for t in types if t != 'null'), '')
    return types or ('object' if 'properties' in schema else '')


def aliases(name, schema):
    values = {normalize(name), normalize(schema.get('title', ''))}
    description = schema.get('description', '')
    # Only explicit label lists, not examples of expected values.
    match = re.search(r'Labels?:\s*(.*?)(?:\.\s+[A-Z]|$)', description, re.S)
    if match:
        values.update(normalize(x) for x in re.findall(r"['\"]([^'\"]+)['\"]", match.group(1)))
    return values - {''}


def label_score(label, choices):
    label = normalize(label)
    if not label:
        return 0
    if label in choices:
        return 1.0
    a = set(label.split())
    return max((2 * len(a & set(b.split())) / (len(a) + len(set(b.split())))
                for b in choices), default=0)


def convert(text, schema):
    text = re.sub(r'\s+', ' ', text).strip()
    if not text or text in ('-', '—', '–'):
        return MISSING
    field_type = kind(schema)
    if field_type in ('number', 'integer'):
        numeric = text.replace(',', '').replace('$', '').replace('£', '').replace('€', '').strip()
        if numeric.endswith('%'):
            numeric = numeric[:-1].strip()
        if numeric.startswith('(') and numeric.endswith(')'):
            numeric = '-' + numeric[1:-1]
        if not re.fullmatch(r'[+-]?\d+(?:\.\d+)?', numeric):
            return MISSING
        try:
            value = Decimal(numeric)
        except InvalidOperation:
            return MISSING
        if field_type == 'integer':
            return int(value) if value == value.to_integral_value() else MISSING
        return float(value)
    if field_type == 'boolean':
        return {'true': True, 'false': False, 'yes': True, 'no': False}.get(text.lower(), MISSING)
    if field_type != 'string':
        return MISSING
    if schema.get('format') == 'date' or 'YYYY-MM-DD' in schema.get('description', ''):
        for pattern in ('%Y-%m-%d', '%m/%d/%Y', '%m/%d/%y', '%m-%d-%Y'):
            try:
                return datetime.strptime(text, pattern).date().isoformat()
            except ValueError:
                pass
        return MISSING
    if 'enum' in schema and text not in schema['enum']:
        return MISSING
    return text


def table_grid(table):
    """Expand spans without losing row/header coordinates; duplicate cells retain text."""
    cells = {}
    rows = table.find_all('tr', recursive=True)
    for row_index, row in enumerate(rows):
        column = 0
        for cell in row.find_all(['td', 'th'], recursive=False):
            while (row_index, column) in cells:
                column += 1
            rowspan = max(1, min(1000, int(cell.get('rowspan', 1))))
            colspan = max(1, min(1000, int(cell.get('colspan', 1))))
            value = cell.get_text(' ', strip=True)
            for dr in range(rowspan):
                for dc in range(colspan):
                    cells[row_index + dr, column + dc] = value
            column += colspan
    width = max((c for _, c in cells), default=-1) + 1
    return [[cells.get((r, c), '') for c in range(width)] for r in range(len(rows))]


def leaves(schema, root, prefix=()):
    result = []
    for name, field in resolve(schema, root).get('properties', {}).items():
        field = resolve(field, root)
        if kind(field) == 'object':
            result.extend(leaves(field, root, prefix + (name,)))
        elif kind(field) != 'array':
            result.append((prefix + (name,), field))
    return result


def assign(obj, path, value):
    for part in path[:-1]:
        obj = obj.setdefault(part, {})
    obj[path[-1]] = value


def header_mapping(headers, fields):
    candidates = []
    for path, field in fields:
        scores = [(label_score(header, aliases(path[-1], field)), col)
                  for col, header in enumerate(headers)]
        scores.sort(reverse=True)
        if not scores or scores[0][0] < 0.8:
            continue
        if len(scores) > 1 and scores[0][0] == scores[1][0]:
            continue  # Ambiguous column, including duplicated spanning headers.
        candidates.append((scores[0][1], path, field, scores[0][0]))
    counts = defaultdict(int)
    for col, *_ in candidates:
        counts[col] += 1
    return [(c, p, f, s) for c, p, f, s in candidates if counts[c] == 1]


def extract(markdown, schema):
    soup = BeautifulSoup(markdown, 'html.parser')
    grids = [table_grid(t) for t in soup.find_all('table') if t.find_parent('table') is None]
    scalar_fields = leaves(schema, schema)
    scalar_candidates = defaultdict(list)
    evidence = []
    # Explicit colon-delimited prose and horizontal/vertical table label-value pairs.
    pairs = []
    for line in soup.get_text('\n').splitlines():
        if ':' in line:
            label, value = line.split(':', 1)
            if len(label) < 80:
                pairs.append((label, value, 'text'))
    for table_number, grid in enumerate(grids):
        for r, row in enumerate(grid):
            for c, label in enumerate(row):
                if c + 1 < len(row):
                    pairs.append((label, row[c + 1], f'table:{table_number}:row:{r}:col:{c + 1}'))
                if r + 1 < len(grid):
                    pairs.append((label, grid[r + 1][c], f'table:{table_number}:row:{r + 1}:col:{c}'))
    for label, value, location in pairs:
        matching = [(path, field) for path, field in scalar_fields
                    if normalize(label) in aliases(path[-1], field)]
        if len(matching) != 1:
            continue
        path, field = matching[0]
        # Avoid treating the next field's label as a string-valued answer.
        if any(normalize(value) in aliases(p[-1], f) for p, f in scalar_fields):
            continue
        converted = convert(value, field)
        if converted is not MISSING:
            scalar_candidates[path].append((converted, location))
    result = {}
    for path, candidates in scalar_candidates.items():
        if all(value == candidates[0][0] for value, _ in candidates):
            assign(result, path, candidates[0][0])
            evidence.append({'path': list(path), 'location': candidates[0][1], 'method': 'exact_label'})

    array_fields = []
    for name, field in resolve(schema, schema).get('properties', {}).items():
        field = resolve(field, schema)
        if kind(field) == 'array' and kind(resolve(field.get('items', {}), schema)) == 'object':
            array_fields.append((name, leaves(field['items'], schema)))
    for table_number, grid in enumerate(grids):
        options = []
        for name, fields in array_fields:
            best = None
            for start in range(min(6, len(grid))):
                for depth in (1, 2, 3):
                    if start + depth >= len(grid):
                        continue
                    headers = [' '.join(dict.fromkeys(grid[r][c] for r in range(start, start + depth)
                                                     if grid[r][c])) for c in range(len(grid[0]))]
                    mapping = header_mapping(headers, fields)
                    rank = (len(mapping), sum(x[3] for x in mapping), -depth, -start)
                    if len(mapping) >= 2 and (best is None or rank > best[0]):
                        best = (rank, start + depth, mapping)
            if best:
                options.append((best[0], name, best[1], best[2]))
        options.sort(key=lambda x: x[0], reverse=True)
        if not options or (len(options) > 1 and options[0][0][:2] == options[1][0][:2]):
            continue  # Cannot distinguish the intended array from another schema array.
        _, name, start, mapping = options[0]
        records = []
        for row_number, row in enumerate(grid[start:], start):
            item = {}
            for column, path, field, _ in mapping:
                raw = row[column]
                if normalize(raw) in aliases(path[-1], field):
                    continue  # Repeated header inside a table.
                value = convert(raw, field)
                if value is not MISSING:
                    assign(item, path, value)
            if len(item) >= 2:
                records.append(item)
                evidence.append({'path': [name, len(result.get(name, [])) + len(records) - 1],
                                 'location': f'table:{table_number}:row:{row_number}',
                                 'method': 'header_alignment'})
        if records:
            result.setdefault(name, []).extend(records)
    return result, {'adapter': VERSION, 'html_tables': len(grids), 'matches': evidence,
                    'limitations': ['Omitted unsupported/ambiguous fields',
                                    'No implicit unit scaling or contextual inference',
                                    'No inferred page/bounding-box citations',
                                    'Nested arrays and Markdown pipe tables unsupported']}
