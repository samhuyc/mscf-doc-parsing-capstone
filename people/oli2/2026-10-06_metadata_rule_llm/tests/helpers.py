import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from adapters import digest, make_document
from config import PARSERS
from providers import ProviderResponse
from schema import FIELDS


def wire():
    return {f: dict(value=None, status='not_found', evidence=[], diagnostics=[]) for f in FIELDS}


def resolved(value, quote, page=1, source='page'):
    return dict(value=value, status='resolved', evidence=[dict(source=source, page=page, quote=quote)], diagnostics=[])


class MockProvider:
    name, model, settings = 'fixture_only', 'synthetic-not-a-model', {'temperature': 0}

    def __init__(self, response=None):
        self.response = json.dumps(response if response is not None else wire())
        self.calls = 0
        self.messages = None

    def generate(self, messages, schema):
        self.calls += 1
        self.messages = messages
        return ProviderResponse(self.response, dict(provider=self.name, model=self.model, model_calls=1,
                                                    usage=None, estimated_cost_usd=None, runtime_seconds=0))


def fixture(folder, parser='pymupdf4llm', identity='opaque-id', title='Supplied Q4 2099', texts=None):
    folder.mkdir(parents=True, exist_ok=True)
    texts = texts or ['# Example Limited\nReport and financial statements\nFor the year ended 31 March 2023']
    records = [dict(page=i + 1, markdown=s, text_chars=len(s), confidence=None,
                    native=dict(metadata=dict(file_path='FakeBank-Q4-2099.pdf')) if parser == 'pymupdf4llm' else dict(page_idx=i))
               for i, s in enumerate(texts)]
    document = '\n\n'.join(f"<!-- source page {p['page']} -->\n\n{p['markdown']}" for p in records)
    source = dict(id=identity, title=title, pages=len(records), sha256='a' * 64,
                  metadata=dict(title='', creationDate='D:20991201000000'), native_text_chars=[1] * len(records))
    data = {
        'pages.json': dict(schema_version=1, source_sha256=source['sha256'], parser=parser,
                           page_numbering='1-based physical PDF pages', pages=records),
        'metadata.json': dict(parser=parser, source=source),
        'run.json': dict(parser=parser, document=identity, input_sha256=source['sha256'],
                         expected_pages=len(records), parsed_pages=len(records), nonempty_pages=len(records),
                         status='success', versions={'fixture': '1'}, document_sha256=digest(document.encode('utf8'))),
    }
    for name, value in data.items():
        (folder / name).write_text(json.dumps(value), encoding='utf8')
    (folder / 'document.md').write_bytes(document.encode('utf8'))
    return folder
