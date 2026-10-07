"""Conservative rule-first resolution with explicit disagreement and rejection."""
from copy import deepcopy

from adapters import validate_evidence
from evidence_policy import date_support_errors
from schema import FIELDS, decision, equivalent, validate_fields


def resolve(doc, rule, llm):
    if validate_fields(rule) or validate_fields(llm):
        raise ValueError('Hybrid requires canonical decisions')
    if validate_evidence(doc, rule)['errors']:
        raise ValueError('Invalid rule evidence')
    fields, choices = {}, {}
    for f in FIELDS:
        r, l = rule[f], llm[f]
        invalid = (bool(validate_evidence(doc, {f: l})['errors'])
                   or 'invalid_llm_evidence' in l['diagnostics']
                   or 'invalid_llm_date_support' in l['diagnostics'])
        if not invalid:
            invalid = bool(date_support_errors(f, l, doc))
        conflict = (r['status'] == l['status'] == 'resolved' and not equivalent(f, r['value'], l['value']))
        if r['status'] == 'resolved':
            selected, reason, chosen = r, 'rule_resolved', 'rule'
        elif not invalid and l['status'] == 'resolved':
            selected, reason, chosen = l, 'validated_llm_fallback', 'llm'
        else:
            selected, reason, chosen = r, 'no_supported_fallback', 'rule'
        fields[f] = deepcopy(selected)
        fields[f]['method'] = 'hybrid'
        fields[f]['diagnostics'] += [f'hybrid:{reason}']
        if conflict:
            fields[f]['diagnostics'].append('rule_llm_disagreement:rule_retained')
        if invalid:
            fields[f]['diagnostics'].append('invalid_llm_evidence:rejected')
        choices[f] = dict(reason=reason, chosen_method=chosen, disagreement=conflict,
                          llm_evidence_rejected=invalid, rule_status=r['status'], rule_value=r['value'],
                          llm_status=l['status'], llm_value=l['value'])
    return fields, choices
