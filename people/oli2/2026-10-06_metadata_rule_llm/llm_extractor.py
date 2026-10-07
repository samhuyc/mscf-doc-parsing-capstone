"""Independent extraction, strict validation and content-addressed response cache."""
from copy import deepcopy
import json
from pathlib import Path

from adapters import digest, json_bytes, locate_evidence
from config import PROMPT_VERSION, ROOT
from evidence_policy import date_support_errors
from schema import FIELDS, LLM_SCHEMA, decision, validate_fields


def prompt():
    return (ROOT / 'prompts/metadata_extraction.txt').read_text(encoding='utf8')


def messages(doc):
    return [dict(role='system', content=prompt()),
            dict(role='user', content=json.dumps(doc.semantic_payload(), ensure_ascii=False))]


def cache_identity(doc, provider):
    return dict(provider=provider.name, model=provider.model, settings=provider.settings,
                semantic_sha256=doc.semantic_sha256, prompt_version=PROMPT_VERSION,
                prompt_sha256=digest(prompt().encode('utf8')), schema_sha256=digest(json_bytes(LLM_SCHEMA)))


def validate_response(text, doc):
    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        raw = None
    errors = ['malformed_json'] if raw is None else validate_fields(raw, wire=True)
    audit = dict(raw_schema_valid=not errors, schema_errors=errors, rejected_fields=[], policy_rejections=[],
                 proposed_resolved_fields=[], proposed_evidence_count=0, invalid_evidence_count=0)
    if errors:
        return {f: decision('llm', diagnostics=['invalid_model_contract']) for f in FIELDS}, audit
    fields = {}
    for f in FIELDS:
        d = raw[f]
        if d['status'] == 'resolved':
            audit['proposed_resolved_fields'].append(f)
        enriched, evidence_errors = [], []
        for e in d['evidence']:
            audit['proposed_evidence_count'] += 1
            try:
                enriched.append(locate_evidence(doc, e))
            except (ValueError, KeyError, TypeError) as error:
                audit['invalid_evidence_count'] += 1
                evidence_errors.append(str(error))
        if evidence_errors:
            fields[f] = decision('llm', diagnostics=['invalid_llm_evidence', *evidence_errors])
            audit['rejected_fields'].append(dict(field=f, proposed_value=d['value'], errors=evidence_errors))
        else:
            fields[f] = decision('llm', d['value'], d['status'], enriched, d['diagnostics'])
            policy_errors = date_support_errors(f, fields[f], doc)
            if policy_errors:
                audit['policy_rejections'].append(dict(field=f, proposed_value=d['value'], errors=policy_errors))
                fields[f] = decision('llm', diagnostics=['invalid_llm_date_support', *policy_errors])
    return fields, audit


def extract(doc, provider, cache_dir, *, offline=False):
    identity = cache_identity(doc, provider)
    key = digest(json_bytes(identity))
    path = Path(cache_dir) / (key + '.json')
    cache_hit = path.exists()
    if cache_hit:
        cached = json.loads(path.read_text(encoding='utf8'))
        if cached['identity'] != identity or cached['response_sha256'] != digest(cached['text'].encode('utf8')):
            raise ValueError('Cache identity/response checksum mismatch')
    else:
        if offline:
            raise FileNotFoundError(f'No cached model response: {key}')
        response = provider.generate(messages(doc), deepcopy(LLM_SCHEMA))
        cached = dict(cache_version=1, identity=identity, text=response.text, metadata=response.metadata,
                      response_sha256=digest(response.text.encode('utf8')))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('x', encoding='utf8', newline='\n') as file:
            json.dump(cached, file, ensure_ascii=False, indent=2)
            file.write('\n')
    fields, audit = validate_response(cached['text'], doc)
    metadata = dict(cached['metadata'], cache_key=key, cache_hit=cache_hit,
                    model_calls_this_run=0 if cache_hit else cached['metadata']['model_calls'],
                    prompt_version=PROMPT_VERSION, prompt_sha256=identity['prompt_sha256'],
                    schema_sha256=identity['schema_sha256'])
    return fields, audit, metadata
