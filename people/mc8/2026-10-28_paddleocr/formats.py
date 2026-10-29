"""Deterministic output conversion; no inferred cells, labels, or numeric repairs."""
import hashlib
import json
import re
import unicodedata
from collections import Counter
from html import escape
from pathlib import Path

from bs4 import BeautifulSoup, Comment
from markdown_it import MarkdownIt

MARKDOWN = MarkdownIt('commonmark', {'html': True}).enable('table')
FACT_TAGS = ('number', 'temporal', 'monetaryunit', 'reportingentity', 'financialconcepts')
# Conservative lexical tokens: preserve signs, grouping, decimals and percentages.
NUMBER = re.compile(r'(?<![0-9A-Za-z_.])\(?\s*[$£€¥]?\s*[+\-−–]?\s*[$£€¥]?\s*\d+(?:[,，]\d{3})*(?:\.\d+)?\s*%?\)?%?(?![0-9A-Za-z_.])')


def read_jsonl(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    ids = [row['id'] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError(f'Duplicate sample IDs in {path}')
    return rows


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text)).strip()


def numbers(text):
    return [re.sub(r'\s+', '', m.group()).replace('−', '-') for m in NUMBER.finditer(text)]


def numeric_counts(text):
    return Counter(numbers(text))


def soup_for(content, fmt='markdown'):
    # SEC submission envelope is metadata, not rendered page text.
    if fmt == 'html' and re.search(r'<DOCUMENT\b', content, re.I):
        content = re.sub(r'\A.*?<TEXT\s*>', '', content, count=1, flags=re.S | re.I)
    if fmt == 'text':
        content = '<p>' + escape(content).replace('\n', '<br/>') + '</p>'
    elif fmt == 'markdown':
        # Only unwrap a fence when it encloses the entire response.
        content = re.sub(r'\A\s*```(?:markdown|md|html)\s*\n(.*?)\n```\s*\Z',
                         r'\1', content, flags=re.S)
        content = MARKDOWN.render(content)
    elif fmt != 'html':
        raise ValueError('Supported formats: markdown, html, text')
    soup = BeautifulSoup(content, 'html.parser')
    for tag in soup(['script', 'style', 'head', 'title']):
        tag.decompose()
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()
    return soup


def plain_text(content, fmt='markdown'):
    return normalize(soup_for(content, fmt).get_text(' '))


def canonical(content, fmt):
    """Keep HTML cells intact; convert pipe tables mechanically through CommonMark."""
    soup = soup_for(content, fmt)
    if fmt == 'markdown':
        # Preserve Markdown prose; replace only recognized pipe/HTML table blocks.
        tokens = MARKDOWN.parse(re.sub(r'\A\s*```(?:markdown|md|html)\s*\n(.*?)\n```\s*\Z',
                                      r'\1', content, flags=re.S))
        content = re.sub(r'\A\s*```(?:markdown|md|html)\s*\n(.*?)\n```\s*\Z',
                         r'\1', content, flags=re.S)
        lines = content.splitlines()
        replacements = []
        for i, token in enumerate(tokens):
            if token.type == 'table_open':
                end = next(j for j in range(i + 1, len(tokens)) if tokens[j].type == 'table_close')
                html = MARKDOWN.renderer.render(tokens[i:end + 1], MARKDOWN.options, {})
                replacements.append((token.map[0], token.map[1], html.strip()))
        for start, end, html in reversed(replacements):
            lines[start:end] = [html]
        return '\n'.join(lines).strip() + '\n'
    if fmt == 'text':
        # Escaped HTML prose is valid embedded HTML in the Markdown container.
        return str(soup) + '\n'
    # HTML is also permitted inside Markdown; retain it without semantic rewriting.
    return str(soup) + '\n'


def table_rows(table):
    return [normalize(row.get_text(' ')) for row in table.find_all('tr')]


def fact_groups(html):
    """Extract existing FinCriticalED annotations; never create human labels."""
    soup = soup_for(html, 'html')
    groups = {}
    for tag in soup.find_all(FACT_TAGS):
        context = tag.find_parent('tr') or tag.find_parent(['p', 'li']) or tag.parent
        key = id(context)
        group = groups.setdefault(key, {'context': normalize(context.get_text(' ')), 'facts': []})
        group['facts'].append({'type': tag.name, 'text': normalize(tag.get_text(' '))})
    return list(groups.values())
