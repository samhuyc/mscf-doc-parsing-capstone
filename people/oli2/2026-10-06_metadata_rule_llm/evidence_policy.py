"""Necessary date support checks, shared across model validation and Hybrid.

These checks verify contract constraints; they do not extract field predictions or
prove semantic correctness. Date tokenization reuses O6's generic English parser.
"""
import re

from baseline_bridge import inputs, rules


def date_support_errors(field, decision, doc):
    if field not in ('reporting_period_end', 'document_date') or decision['status'] != 'resolved':
        return []
    matches = []
    for evidence in decision['evidence']:
        if evidence['source'] != 'page':
            continue
        # Require the exact value in a quoted date token. Q2/H1 alone cannot pass.
        view = inputs.text_view(evidence['quote'], '', '', evidence['page'])
        for token in rules.DATE.finditer(view.text):
            value, error = rules.parse_date(token.group())
            if not error and value == decision['value']:
                matches.append((evidence, view, token))
    if not matches:
        return ['date_value_not_explicit_in_quoted_evidence']
    if field == 'reporting_period_end':
        return []  # Explicit token is necessary, but context still needs review.
    for evidence, view, token in matches:
        if evidence['page'] != 1:
            continue
        raw_start = evidence['start'] + view.spans[token.start()][0]
        raw_end = evidence['start'] + view.spans[token.end() - 1][1]
        page_text = doc.pages[0].markdown
        before = inputs.text_view(page_text[max(0, raw_start - 100):raw_start], '', '', 1).text
        after = inputs.text_view(page_text[raw_end:raw_end + 60], '', '', 1).text
        excluded_prefix = re.search(r'(?:as (?:at|of)|copyright|approved|signed|companies house|'
                                    r'(?:year|months|quarter)\s+(?:ended|ending|to))\s*$', before, re.I)
        stamp_suffix = re.match(r'\s*companies house\b', after, re.I)
        if not excluded_prefix and not stamp_suffix:
            return []
    return ['document_date_requires_cover_event_or_publication_not_administrative_date']
