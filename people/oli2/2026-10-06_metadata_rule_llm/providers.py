"""Swappable structured-output providers; standard-library HTTPS implementation."""
from dataclasses import dataclass
import json
import os
import time
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import MODEL, SETTINGS


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    metadata: dict


class Provider(Protocol):
    name: str
    model: str
    settings: dict

    def generate(self, messages: list, schema: dict) -> ProviderResponse: ...


class ProviderError(RuntimeError):
    def __init__(self, metadata):
        super().__init__(metadata['error'])
        self.metadata = metadata


class OpenAIProvider:
    name = 'openai_responses'

    def __init__(self, model=MODEL, settings=None):
        self.model = model
        self.settings = dict(SETTINGS if settings is None else settings)

    def generate(self, messages, schema):
        key = os.environ.get('OPENAI_API_KEY')
        if not key:
            raise ProviderError(dict(error='missing_OPENAI_API_KEY', model_calls=0, runtime_seconds=0,
                                     provider=self.name, requested_model=self.model, settings=self.settings))
        payload = dict(model=self.model, input=messages, store=False, **self.settings,
                       text=dict(format=dict(type='json_schema', name='financial_metadata',
                                             strict=True, schema=schema)))
        # Fixed official endpoint: environment overrides cannot redirect the key.
        request = Request('https://api.openai.com/v1/responses',
                          data=json.dumps(payload).encode('utf8'),
                          headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json'})
        started = time.perf_counter()
        meta = dict(provider=self.name, requested_model=self.model, settings=self.settings,
                    reasoning=None, model_calls=1, estimated_cost_usd=None)
        try:
            with urlopen(request, timeout=180) as response:
                raw = json.load(response)
        except (HTTPError, URLError, TimeoutError) as error:
            # Never serialize headers, keys, arbitrary response body, or request text.
            meta.update(error=f'HTTP_{error.code}' if isinstance(error, HTTPError) else type(error).__name__,
                        runtime_seconds=time.perf_counter() - started, usage=None)
            raise ProviderError(meta) from None
        meta.update(runtime_seconds=time.perf_counter() - started, response_id=raw.get('id'),
                    model=raw.get('model'), usage=raw.get('usage'), response_status=raw.get('status'))
        if raw.get('status') != 'completed':
            meta['error'] = 'incomplete_or_failed_response'
            raise ProviderError(meta)
        chunks = [c.get('text', '') for item in raw.get('output', []) if item.get('type') == 'message'
                  for c in item.get('content', []) if c.get('type') == 'output_text']
        usage = meta['usage'] or {}
        if meta['model'] == MODEL and 'input_tokens' in usage and 'output_tokens' in usage:
            cached = (usage.get('input_tokens_details') or {}).get('cached_tokens', 0)
            meta['estimated_cost_usd'] = ((usage['input_tokens'] - cached) * 0.40 + cached * 0.10
                                          + usage['output_tokens'] * 1.60) / 1_000_000
            meta['price_basis'] = dict(date='2026-10-06', input_per_million=0.40,
                                      cached_input_per_million=0.10, output_per_million=1.60,
                                      source='https://developers.openai.com/api/docs/models/gpt-4.1-mini',
                                      note='List-price estimate, not invoice; standard text tier')
        return ProviderResponse(''.join(chunks), meta)
