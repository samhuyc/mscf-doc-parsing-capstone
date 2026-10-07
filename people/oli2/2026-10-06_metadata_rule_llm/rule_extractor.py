"""One O6 1.1.0 wrapper for every parser; conservative generic issuer extension."""
import re

from adapters import locate_evidence
from baseline_bridge import inputs, rules
from schema import decision, normalized_value


def issuer_rule(doc):
    """Accept a standalone cover legal-entity line or an explicit Issuer: label.

    No brand dictionary, fuzzy correction, suffix removal or body-name guessing.
    Multiple names at equal priority cause abstention. Brand-only covers abstain.
    """
    candidates = []
    offset = 0
    for line in doc.pages[0].markdown.splitlines(keepends=True):
        view = inputs.text_view(line, '', '', 1)
        clean = view.text.strip()
        labeled = re.fullmatch(r'Issuer\s*:\s*(.{2,100})', clean, re.I)
        legal = re.fullmatch(r"([A-Z][A-Za-z0-9 &.,'()\-]{1,95}\s+(?:Limited|Ltd\.?|plc|Inc\.?|Corporation))", clean)
        # re.I is unnecessary for the name but legal suffix casing is variable.
        if not legal:
            legal = re.fullmatch(r"([A-Z][A-Za-z0-9 &.,'()\-]{1,95}\s+(?i:Limited|Ltd\.?|plc|Inc\.?|Corporation))", clean)
        match = labeled or legal
        if match:
            value = match[1].strip()
            if not re.search(r'\b(?:registered|auditor|accountant|prepared by|copyright)\b', value, re.I):
                start = view.text.find(value)
                item = view.evidence(start, start + len(value))
                evidence = locate_evidence(doc, dict(source='page', page=1, quote=item['quote'],
                                                      start=offset + item['start'], end=offset + item['end']))
                candidates.append(dict(value=value, priority=100 if labeled else 80, evidence=evidence))
        offset += len(line)
    if not candidates:
        return decision('rule', diagnostics=['issuer:no_explicit_label_or_standalone_cover_legal_entity'])
    top = max(c['priority'] for c in candidates)
    leaders = [c for c in candidates if c['priority'] == top]
    values = {normalized_value('issuer', c['value']) for c in leaders}
    return decision('rule', leaders[0]['value'] if len(values) == 1 else None,
                    'resolved' if len(values) == 1 else 'ambiguous',
                    [c['evidence'] for c in leaders],
                    ['issuer:explicit_label' if top == 100 else 'issuer:standalone_cover_legal_entity'])


def extract(doc):
    pages = [inputs.text_view(p.markdown, 'pages.json', f'/pages/{i}/markdown', p.page)
             for i, p in enumerate(doc.pages)]
    title = inputs.text_view(doc.embedded_title, 'metadata.json', '/source/metadata/title', None)
    old = rules.extract_fields(pages, title)
    evidence = {e['id']: locate_evidence(doc, dict(source='page' if e['page'] else 'embedded_title',
                                                **{k: e[k] for k in ('page', 'quote', 'start', 'end')}))
                for e in old['evidence']}
    mapping = dict(document_type='document_type', reporting_period='reference_period',
                   reporting_period_end='reference_date', document_date='document_date')
    fields = {'issuer': issuer_rule(doc)}
    for new, prior in mapping.items():
        d = old[prior]
        fields[new] = decision('rule', d['value'], d['status'], [evidence[e] for e in d['evidence_ids']],
                               [f"o6_rule:{d['rule_id']}", f"role:{d['role']}"])
    # Preserve excluded and competing candidates, not just the winning quote.
    audit = dict(baseline_ruleset=rules.RULESET_VERSION, warnings=old['warnings'],
                 candidates={new: old[prior]['candidates'] for new, prior in mapping.items()},
                 evidence_catalog=evidence)
    return fields, audit
