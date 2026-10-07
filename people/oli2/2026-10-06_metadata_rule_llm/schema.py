"""Canonical decisions and a strict, provider-neutral model response schema."""
from datetime import date
import json
import re
import unicodedata

from jsonschema import Draft202012Validator

FIELDS = ('issuer', 'document_type', 'reporting_period', 'reporting_period_end', 'document_date')
TYPES = ('earnings_presentation', 'results_presentation', 'results_press_release',
         'annual_financial_statements', 'unaudited_financial_statements',
         'consolidated_segmental_statement')


def object_schema(properties):
    return dict(type='object', properties=properties, required=list(properties), additionalProperties=False)


PERIOD = object_schema(dict(year=dict(type='integer', minimum=1900, maximum=2199),
                            kind=dict(enum=['year', 'half', 'quarter']),
                            number=dict(type=['integer', 'null'], minimum=1, maximum=4)))
VALUES = dict(issuer=dict(type=['string', 'null'], minLength=1),
              document_type=dict(enum=[None, *TYPES]),
              reporting_period=dict(anyOf=[dict(type='null'), PERIOD]),
              reporting_period_end=dict(type=['string', 'null'], pattern=r'^\d{4}-\d{2}-\d{2}$'),
              document_date=dict(type=['string', 'null'], pattern=r'^\d{4}-\d{2}-\d{2}$'))
WIRE_EVIDENCE = object_schema(dict(source=dict(enum=['page', 'embedded_title']),
                                   page=dict(type=['integer', 'null'], minimum=1),
                                   quote=dict(type='string', minLength=1)))
EVIDENCE = object_schema({**WIRE_EVIDENCE['properties'],
                         'start': dict(type='integer', minimum=0),
                         'end': dict(type='integer', minimum=1),
                         'original_quote': dict(type='string', minLength=1),
                         'json_pointer': dict(type='string')})


def decisions_schema(wire=False):
    properties = {}
    for field in FIELDS:
        props = dict(value=VALUES[field], status=dict(enum=['resolved', 'ambiguous', 'not_found']),
                     evidence=dict(type='array', items=WIRE_EVIDENCE if wire else EVIDENCE),
                     diagnostics=dict(type='array', items=dict(type='string')))
        if not wire:
            props['method'] = dict(enum=['rule', 'llm', 'hybrid'])
        properties[field] = object_schema(props)
    return object_schema(properties)


LLM_SCHEMA = decisions_schema(wire=True)
CANONICAL_SCHEMA = decisions_schema()


def decision(method, value=None, status='not_found', evidence=None, diagnostics=None):
    return dict(value=value, status=status, method=method, evidence=evidence or [],
                diagnostics=diagnostics or [])


def validate_fields(fields, wire=False):
    errors = [f'{"/".join(map(str, e.path))}: {e.message}'
              for e in Draft202012Validator(LLM_SCHEMA if wire else CANONICAL_SCHEMA).iter_errors(fields)]
    if errors:
        return errors
    for name, d in fields.items():
        value = d['value']
        if d['status'] == 'resolved':
            if value is None or not d['evidence']:
                errors.append(f'{name}: resolved requires value and evidence')
        elif value is not None:
            errors.append(f'{name}: abstention requires null value')
        if value is not None and name in ('reporting_period_end', 'document_date'):
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError()
            except ValueError:
                errors.append(f'{name}: invalid ISO calendar date')
        if name == 'reporting_period' and value is not None:
            n, kind = value['number'], value['kind']
            if (kind == 'year' and n is not None) or (kind == 'half' and n not in (None, 1, 2)):
                errors.append(f'{name}: invalid period number')
        for e in d['evidence']:
            if (e['source'] == 'embedded_title') != (e['page'] is None):
                errors.append(f'{name}: evidence source/page mismatch')
            if not wire and e['end'] <= e['start']:
                errors.append(f'{name}: empty evidence span')
    return errors


def normalized_value(field, value):
    """Only declared taxonomy/case/space normalization; no issuer alias table."""
    if field == 'document_type' and value == 'annual_accounts':
        return 'annual_financial_statements'
    if field == 'issuer' and isinstance(value, str):
        return re.sub(r'\s+', ' ', unicodedata.normalize('NFKC', value)).strip().casefold()
    return value


def equivalent(field, a, b):
    return normalized_value(field, a) == normalized_value(field, b)


def signature(fields, field):
    d = fields[field]
    return json.dumps([d['status'], normalized_value(field, d['value'])], sort_keys=True)
