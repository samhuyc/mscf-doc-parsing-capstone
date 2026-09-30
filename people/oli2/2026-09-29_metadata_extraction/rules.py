"""Deterministic O6 rules. No document IDs, filenames, labels, or issuer rules."""
from datetime import date
import json
import re

RULESET_VERSION = '1.1.0'
FIELDS = ('document_type', 'reference_period', 'reference_date', 'document_date')
MONTHS = {name: i for i, name in enumerate(
    ('january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
     'september', 'october', 'november', 'december'), 1)}
MONTHS.update({name[:3]: value for name, value in list(MONTHS.items())})
MONTH = r'(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?'
DATE = re.compile(rf'\b(?:\d{{1,2}}(?:st|nd|rd|th)?\s+{MONTH}\s+\d{{4}}|{MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}|\d{{4}}-\d{{2}}-\d{{2}}|\d{{1,2}}/\d{{1,2}}/\d{{4}})\b', re.I)
REPORT_PREFIX = re.compile(r'(?P<kind>half[ -]year|six months|three months|quarter|(?:financial )?year)\s+(?:ended|ending|to)\s*$', re.I)


def parse_date(text):
    clean = re.sub(r'(\d)(st|nd|rd|th)\b', r'\1', text, flags=re.I).replace(',', '').replace('.', '')
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', clean):
            return date.fromisoformat(clean).isoformat(), None
        if '/' in clean:
            a, b, year = map(int, clean.split('/'))
            if a <= 12 and b <= 12 and a != b:
                return None, 'ambiguous_numeric_date'
            day, month = (a, b) if a > 12 or a == b else (b, a)
        else:
            parts = clean.lower().split()
            if parts[0].isdigit():
                day, month, year = int(parts[0]), MONTHS[parts[1]], int(parts[2])
            else:
                month, day, year = MONTHS[parts[0]], int(parts[1]), int(parts[2])
        return date(year, month, day).isoformat(), None
    except (ValueError, KeyError, IndexError):
        return None, 'invalid_date'


class Evidence:
    def __init__(self):
        self.items = []
        self.keys = {}

    def add(self, view, start, end):
        item = view.evidence(start, end)
        key = (item['file'], item['json_pointer'], item['start'], item['end'])
        if key not in self.keys:
            eid = f'e{len(self.items) + 1}'
            self.keys[key] = eid
            self.items.append(dict(id=eid, **item))
        return self.keys[key]


def candidate(value, role, rule, priority, evidence_ids, reason=None):
    return dict(value=value, role=role, rule_id=rule, priority=priority,
                evidence_ids=evidence_ids, exclusion_reason=reason, disposition='pending')


def resolve(candidates, role):
    eligible = [c for c in candidates if c['exclusion_reason'] is None]
    leaders = []
    if eligible:
        highest = max(c['priority'] for c in eligible)
        leaders = [c for c in eligible if c['priority'] == highest]
    values = {json.dumps(c['value'], sort_keys=True) for c in leaders}
    status = 'resolved' if len(values) == 1 and leaders[0]['value'] is not None else ('ambiguous' if leaders else 'not_found')
    selected = leaders[0] if status == 'resolved' else None
    for c in candidates:
        if c['exclusion_reason']:
            c['disposition'] = 'excluded'
        elif c in leaders:
            c['disposition'] = 'selected' if selected else 'competing'
        else:
            c['disposition'] = 'lower_priority'
    return dict(value=selected['value'] if selected else None, role=role, status=status,
                rule_id=selected['rule_id'] if selected else None,
                evidence_ids=list(dict.fromkeys(e for c in leaders for e in c['evidence_ids'])),
                candidates=candidates)


def document_type(pages, title, evidence):
    candidates = []
    cover = pages[0]
    patterns = (
        ('consolidated_segmental_statement', r'consolidated segmental statement', 100),
        ('unaudited_financial_statements', r'unaudited\s+(?:annual\s+)?financial statements', 100),
        ('annual_financial_statements', r'(?:annual (?:report and )?(?:financial statements|accounts)|report and financial statements)', 80),
        ('results_press_release', r'(?:results\s+press release|press release|results announcement)', 90),
        ('earnings_presentation', r'earnings presentation', 90),
        ('results_presentation', r'(?:results presentation|half[ -]year (?:results )?presentation)', 90),
    )
    for view in (cover, title):
        for value, pattern, priority in patterns:
            for m in re.finditer(pattern, view.text, re.I):
                candidates.append(candidate(value, 'document_type', 'explicit_document_title',
                                            priority if view.page else priority - 20,
                                            [evidence.add(view, *m.span())]))
    # An earnings call cover plus the document's own presentation description.
    earnings = re.search(r'earnings\s+conference call', cover.text, re.I)
    if earnings:
        for page in pages[:2]:
            own = re.search(r'this presentation', page.text, re.I)
            if own:
                candidates.append(candidate('earnings_presentation', 'document_type',
                                            'earnings_call_and_self_description', 100,
                                            [evidence.add(cover, *earnings.span()), evidence.add(page, *own.span())]))
                break
    return resolve(candidates, 'document_type')


def collect_dates(pages, evidence):
    found = []
    for page in pages:
        for match in DATE.finditer(page.text):
            value, problem = parse_date(match.group())
            prefix = page.text[max(0, match.start() - 70):match.start()]
            after = page.text[match.end():match.end() + 40]
            report = REPORT_PREFIX.search(prefix)
            stamp = bool(re.search(r'companies house\s*$', prefix, re.I) or re.match(r'\s*companies house\b', after, re.I))
            role = 'reporting_period_end' if report else ('filing_stamp' if stamp else 'other_date')
            start = match.start() - len(prefix) + report.start() if report else match.start()
            kind = None
            if report:
                label = report['kind'].lower()
                kind = 'half' if label.startswith(('half', 'six')) else ('quarter' if label in ('quarter', 'three months') else 'year')
            eid = evidence.add(page, start, match.end())
            found.append(dict(value=value, problem=problem, role=role, kind=kind,
                              page=page.page, start=match.start(), end=match.end(), evidence_id=eid))
    return found


def cover_period_authority(view, start, end):
    """Rank the original markup, before normalization erased its structure.

    Table containment takes precedence over bold/heading-like cell content.
    The returned rule ID makes the structural basis visible in each candidate.
    No year values, issuer names, or document identities enter this ranking.
    """
    left, right = view.spans[start][0], view.spans[end - 1][1]
    for table in re.finditer(r'<table\b[^>]*>.*?(?:</table\s*>|\Z)', view.raw, re.I | re.S):
        if table.start() <= left < table.end():
            first_row = re.search(r'<tr\b[^>]*>.*?</tr\s*>', table.group(), re.I | re.S)
            cells = re.finditer(r'<th\b[^>]*>.*?</th\s*>', table.group(), re.I | re.S)
            relative = left - table.start()
            header = (first_row is not None and first_row.start() <= relative < first_row.end()) or any(
                cell.start() <= relative < cell.end() for cell in cells)
            return ('cover_table_header_period' if header else 'cover_table_period'), 20
    for heading in re.finditer(r'<h([1-6])\b[^>]*>.*?</h\1\s*>', view.raw, re.I | re.S):
        if heading.start() <= left and right <= heading.end():
            return 'cover_heading_period', 120
    line_start = view.raw.rfind('\n', 0, left) + 1
    line_end = view.raw.find('\n', right)
    line = view.raw[line_start:line_end if line_end != -1 else len(view.raw)]
    if re.match(r'^\s{0,3}#{1,6}\s+', line) or re.fullmatch(r'\s*(?:\*\*.+\*\*|__.+__)\s*', line):
        return 'cover_heading_period', 120
    return 'cover_narrative_period', 100


def reference_period(pages, dates, evidence):
    candidates = []
    ordinal = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4}
    patterns = (
        (r'\b(?P<ordinal>first|second|third|fourth) quarter\s+(?P<year>20\d{2})\b', 'quarter'),
        (r'\bQ(?P<number>[1-4])\s*[- /]?\s*(?P<year>20\d{2})\b', 'quarter'),
        (r'\b(?P<year>20\d{2})\s+Q(?P<number>[1-4])\b', 'quarter'),
        (r'\bH(?P<number>[12])\s*[- /]?\s*(?P<year>20\d{2})\b', 'half'),
        (r'\b(?P<year>20\d{2})\s+H(?P<number>[12])\b', 'half'),
        (r'\bhalf[ -]year\s+(?:results\s+)?(?P<year>20\d{2})\b', 'half'),
        (r'\b(?P<year>20\d{2})\s+half[ -]year\b', 'half'),
    )
    # Keep the existing cover-only search scope. Preserve table candidates but
    # rank them below document headings and narrative on that same page.
    cover = pages[0]
    for pattern, kind in patterns:
        for match in re.finditer(pattern, cover.text, re.I):
            groups = match.groupdict()
            number = int(groups['number']) if groups.get('number') else ordinal.get((groups.get('ordinal') or '').lower())
            # "Half year results" alone does not establish a fiscal half number.
            if kind == 'half' and number is None:
                # An explicit H1/H2 label elsewhere can identify the same year's half.
                half_hits = []
                for page in pages:
                    for h in re.finditer(rf'\bH([12])\s+{groups["year"]}\b', page.text, re.I):
                        half_hits.append((int(h[1]), page, h))
                if len({h[0] for h in half_hits}) == 1:
                    number = half_hits[0][0]
                    support = [evidence.add(half_hits[0][1], *half_hits[0][2].span())]
                else:
                    support = []
            else:
                support = []
            rule, priority = cover_period_authority(cover, *match.span())
            candidates.append(candidate(dict(year=int(groups['year']), kind=kind, number=number),
                                        'reporting_period', rule, priority,
                                        [evidence.add(cover, *match.span()), *support]))
    for d in dates:
        if d['role'] == 'reporting_period_end' and d['value']:
            candidates.append(candidate(dict(year=int(d['value'][:4]), kind=d['kind'], number=None),
                                        'reporting_period', 'explicit_period_end',
                                        100 if d['page'] == 1 else 50, [d['evidence_id']]))
    return resolve(candidates, 'reporting_period')


def reference_date(dates, period):
    candidates = []
    for d in dates:
        reason = None if d['role'] == 'reporting_period_end' else 'different_date_role'
        if reason is None and period['status'] == 'resolved':
            p = period['value']
            if d['value'] and (int(d['value'][:4]) != p['year'] or d['kind'] != p['kind']):
                reason = 'different_reporting_period'
        if d['problem'] == 'invalid_date':
            reason = 'invalid_date'
        candidates.append(candidate(d['value'], d['role'], 'explicit_period_end' if d['kind'] else 'date_mention',
                                    100 if d['page'] == 1 else 50, [d['evidence_id']], reason))
    result = resolve(candidates, 'reporting_period_end')
    # Do not resolve an exact date against an already conflicting period scope.
    if period['status'] == 'ambiguous' and result['status'] == 'resolved':
        result.update(value=None, status='ambiguous', rule_id=None)
        for c in result['candidates']:
            if c['disposition'] == 'selected':
                c['disposition'] = 'competing'
    return result


def document_date(pages, dates, dtype, evidence):
    candidates = []
    kind = dtype['value']
    role = ('presentation_event' if kind in ('earnings_presentation', 'results_presentation') else
            'announcement' if kind == 'results_press_release' else 'document_date')
    for d in dates:
        if d['page'] != 1:
            continue
        reason = None
        prefix = pages[0].text[max(0, d['start'] - 45):d['start']]
        explicitly_labeled = bool(re.search(r'(?:published|publication date|issued|announcement date)\s*(?:on|:)?\s*$', prefix, re.I))
        if d['role'] != 'other_date':
            reason = 'different_date_role'
        elif re.search(r'(?:as (?:at|of)|copyright|approved|signed)\s*$', prefix, re.I):
            reason = 'as_of_or_administrative_date'
        elif not explicitly_labeled and role == 'document_date':
            reason = 'no_document_date_context'
        if d['problem'] == 'invalid_date':
            reason = 'invalid_date'
        ids = [d['evidence_id']]
        if reason is None:
            ids += dtype['evidence_ids']
        candidates.append(candidate(d['value'], d['role'] if reason else role,
                                    'labeled_cover_date' if explicitly_labeled else 'cover_date_and_document_type',
                                    100 if explicitly_labeled else (80 if d['start'] < 500 else 20),
                                    list(dict.fromkeys(ids)), reason))
    return resolve(candidates, role)


def extract_fields(pages, embedded_title):
    if not pages:
        raise ValueError('No physical pages')
    evidence = Evidence()
    dtype = document_type(pages, embedded_title, evidence)
    dates = collect_dates(pages, evidence)
    period = reference_period(pages, dates, evidence)
    ref = reference_date(dates, period)
    docdate = document_date(pages, dates, dtype, evidence)
    fields = dict(document_type=dtype, reference_period=period, reference_date=ref, document_date=docdate)
    warnings = [f'{key}:{value["status"]}' for key, value in fields.items() if value['status'] != 'resolved']
    if period['status'] == 'resolved' and ref['status'] == 'not_found':
        warnings.append('reporting_period_known_but_exact_end_not_explicit')
    if any(d['role'] == 'filing_stamp' for d in dates):
        warnings.append('filing_stamp_excluded_from_semantic_dates')
    warnings += sorted({d['problem'] for d in dates if d['problem']})
    status = 'ambiguous' if any(f['status'] == 'ambiguous' for f in fields.values()) else (
        'resolved' if all(f['status'] == 'resolved' for f in fields.values()) else 'not_found')
    return dict(**fields, status=status, evidence=evidence.items, warnings=warnings)
